"""Standard-library-only helper sent over SSH; no shell data interpolation.

Controls and receipts share the owner's trusted host. Hash checks detect drift;
this is not an isolation boundary against a malicious trusted host or agent.
"""
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess


def require(condition, message):
    if not condition:
        raise ValueError(message)


def encode(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n").encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read_regular(path, limit=524288, root=None):
    path = Path(path)
    if root is not None:
        require(path.is_relative_to(root), "Receipt escaped runtime root")
    # Refuse symlinks in every component, including an intermediate directory.
    require(not any(part.is_symlink() for part in (path, *path.parents)), "Symlink rejected")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode), "Regular file required")
        raw = stream.read(limit + 1)
    require(len(raw) <= limit, "File exceeds limit")
    return raw


def decode(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "Duplicate JSON key")
            result[key] = value
        return result
    def invalid(_):
        raise ValueError("Non-finite JSON")
    return json.loads(raw.decode("utf-8"), object_pairs_hook=unique, parse_constant=invalid)


def write_once(path, raw):
    if path.exists() or path.is_symlink():
        require(read_regular(path) == raw, "Prepared file drift")
    else:
        with path.open("xb") as stream:
            stream.write(raw)


def verified_completion(record, run, completion, launch, output):
    """Validate every provenance binding before releasing a model decision."""
    task = record["task"]
    profile = record["profile"]
    expected_task = {"id": record["task_id"], "revision": 1, "definition_sha256": record["definition_sha256"]}
    require(run["status"] == "succeeded" and run["attempt"] == 1 and run["task"] == expected_task, "Unexpected task run")
    require(completion["status"] == "completed" and completion["outcome"] == "complete", "Incomplete receipt")
    require(completion["compute"] == {"job_id": run["job_id"], "attempt": 1, "spec_sha256": run["spec_sha256"]}, "Compute binding mismatch")
    require(completion["task"] == expected_task and completion["request"] == run["request"], "Request binding mismatch")
    for field in ("instructions", "execution_profile"):
        require(completion[field] == task[field], "Reviewed control binding mismatch")
    require(completion["account"] == profile["account"], "Account mismatch")
    observed = completion["observed_account"]
    require(all(observed.get(key) == value for key, value in profile["account"].items()) and observed.get("auth_method") == "chatgpt", "Observed account mismatch")
    require(completion["access_mode"] == profile["access_mode"] and completion["reasoning_effort"] == profile["reasoning_effort"], "Permissions or effort mismatch")
    for field in ("task", "request", "compute", "instructions", "execution_profile", "account", "observed_account", "access_mode", "reasoning_effort"):
        require(launch[field] == completion[field], "Launch/completion binding mismatch")
    require(launch["launch_id"] == completion["launch"]["id"] and bool(completion["launch"]["native_session_id"]), "Native session missing")
    require(launch["provider"] == profile["provider"] and launch["model"] == profile["model"], "Native model mismatch")
    require(launch["working_directory"] == profile["working_directory"] and launch["workspace_mode"] == profile["workspace_mode"], "Native workspace mismatch")
    expected_output = str(Path(task["outputs"]["deliverables"][0]) / "response.json")
    require(completion["outputs"] == [{"path": expected_output, "sha256": sha(output), "bytes": len(output)}], "Output hash or path mismatch")
    return decode(output)


class RemoteWorker:
    def __init__(self, config):
        self.config = config
        self.worker = config["target"]["worker"]
        w = self.worker
        self.cli = [w["python"], "-I", "-m", "rudi_compute.cli", "--services-dir", w["root"] + "/services",
            "--schedules-dir", w["root"] + "/schedules", "--state-dir", w["root"] + "/state", "--logs-dir", w["root"] + "/logs"]

    def command(self, args, missing_ok=False):
        result = subprocess.run(args, capture_output=True, timeout=50)
        require(len(result.stdout) <= 2 * 1024 * 1024, "CLI output exceeds limit")
        if result.returncode and missing_ok:
            return None
        require(result.returncode == 0, "Native CLI failed; inspect worker diagnostics")
        return decode(result.stdout)

    def release(self):
        w = self.worker
        self.command([w["python"], "-I", "-m", "rudi_compute.bridge_release", "verify", w["bundle"],
            "--deployment", "--manifest-sha256", w["manifest_sha256"]])

    def prepare(self, record):
        self.release()
        task = record["task"]
        control = Path(task["instructions"]["path"]).parent
        project = Path(task["working_directory"])
        for path in (control, project, control / "runtime", project / "results"):
            path.mkdir(parents=True, exist_ok=True)
            require(not any(part.is_symlink() for part in (path, *path.parents)), "Symlink directory rejected")
        write_once(project / "request.json", record["request_text"].encode())
        write_once(control / "instructions.md", record["instructions_text"].encode())
        write_once(control / "profile.json", encode(record["profile"]))
        write_once(control / "task.json", encode(task))
        validated = self.command(self.cli + ["task", "validate", str(control / "task.json")])
        shown = self.command(self.cli + ["task", "show", record["task_id"]], missing_ok=True)
        if shown is None:
            self.command(self.cli + ["task", "create", str(control / "task.json")])
            shown = self.command(self.cli + ["task", "show", record["task_id"]])
        require(shown["revision"] == 1 and shown["state"] == "inactive" and
            shown["definition_sha256"] == validated["definition_sha256"], "Stored task differs")
        return {"definition_sha256": shown["definition_sha256"], "revision": 1}

    def verify(self, record):
        task = record["task"]
        require(record["profile"]["account"] == self.config["target"]["account"], "Target account drift")
        for field in ("instructions", "execution_profile"):
            require(sha(read_regular(task[field]["path"])) == task[field]["sha256"], "Reviewed file drift")
        control = Path(task["instructions"]["path"]).parent
        require(read_regular(control / "task.json") == encode(task), "Task file drift")
        require(read_regular(Path(task["working_directory"]) / "request.json") == record["request_text"].encode(), "Input drift")
        shown = self.command(self.cli + ["task", "show", record["task_id"]])
        require(shown["revision"] == 1 and shown["state"] == "inactive" and
            shown["definition_sha256"] == record["definition_sha256"], "Stored task drift")
        return shown

    def inspect(self, record):
        self.verify(record)
        runs = self.command(self.cli + ["task", "runs", record["task_id"]])["runs"]
        require(len(runs) <= 1, "Unexpected additional native runs")
        if not runs:
            return {"status": "prepared"}
        run = runs[0]
        require(run["task"] == {"id": record["task_id"], "revision": 1, "definition_sha256": record["definition_sha256"]}
            and type(run["attempt"]) is int and run["attempt"] == (0 if run["status"] == "queued" else 1), "Task run drift")
        job = self.command(self.cli + ["job", run["job_id"]])["job"]
        require(job["id"] == run["job_id"], "Job binding mismatch")
        require(run["status"] in ("queued", "running", "succeeded", "dead") and
            job["status"] in ("queued", "running", "succeeded", "dead"), "Unknown native status")
        if run["status"] == "dead" and job["status"] == "dead":
            return {"status": "failed", "job_id": run["job_id"]}
        if run["status"] != "succeeded" or job["status"] != "succeeded":
            # The two CLI reads are not atomic. Reconcile again when a job
            # transitions between them; never infer failure from a stale read.
            return {"status": "running" if job["status"] != "queued" else "queued", "job_id": run["job_id"]}
        runtime = Path(record["task"]["outputs"]["runtime"])
        reference = run["completion_receipt"]
        raw = read_regular(reference["path"], root=runtime)
        require(sha(raw) == reference["sha256"], "Completion hash mismatch")
        completion = decode(raw)
        launch_raw = read_regular(completion["launch_receipt"]["path"], root=runtime)
        require(sha(launch_raw) == completion["launch_receipt"]["sha256"], "Launch hash mismatch")
        launch = decode(launch_raw)
        output = read_regular(Path(record["task"]["outputs"]["deliverables"][0]) / "response.json", limit=16384)
        response = verified_completion(record, run, completion, launch, output)
        return {"status": "succeeded", "job_id": run["job_id"], "response": response,
            "evidence": {"run": run, "completion": completion, "launch": launch, "response_sha256": sha(output)}}

    def admit(self, record):
        self.release()
        self.verify(record)
        return self.command(self.cli + ["task", "run-now", record["task_id"], "--expected-revision", "1",
            "--agent-cli", self.worker["bundle"] + "/agent-runner", "--timeout-seconds", "620",
            "--idempotency-key", record["idempotency_key"]])


def dispatch(payload):
    worker = RemoteWorker(payload["config"])
    operation = payload["operation"]
    if operation == "verify":
        worker.release()
        for record in payload["records"]:
            worker.verify(record)
        return {"verified": True}
    require(operation in ("prepare", "inspect", "admit"), "Unknown operation")
    return getattr(worker, operation)(payload["record"])
