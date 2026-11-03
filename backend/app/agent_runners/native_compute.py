"""Pinned codex-hoff transport. The browser cannot select paths or permissions."""

import hashlib
import json
from pathlib import Path
import re
import subprocess

from .exchange import canonical_json
from .native_errors import TransportUnavailable
from .native_remote import encode, sha, decode

IDENTITY = {"identity": "codex-hoff", "model": "gpt-6.1-sol", "effort": "low"}


def validate_config(config):
    target = config["target"]
    if (target["identity"] != "codex-hoff" or target["provider"] != "codex" or
            target["account"]["id"] != "codex-hoff" or target["host"]["transport"] != "ssh"):
        raise ValueError("The bounded experiment requires the codex-hoff manual target")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", target["host"]["ssh_alias"]):
        raise ValueError("Invalid operator SSH alias")
    paths = [config["remote_outputs_root"], *config["shared_roots"], target["account"]["config_directory"],
        *(target["worker"][key] for key in ("root", "python", "bundle"))]
    if len(config["shared_roots"]) != 3 or any(not isinstance(path, str) or not Path(path).is_absolute()
            or ".." in Path(path).parts or any(ord(char) < 32 for char in path) for path in paths):
        raise ValueError("Explicit absolute operator paths required")
    if not re.fullmatch(r"[a-f0-9]{64}", target["worker"]["manifest_sha256"]):
        raise ValueError("Pinned worker manifest required")
    return config


class NativeCompute:
    identity = IDENTITY

    def __init__(self, config):
        self.config = validate_config(config)
        self.helper = Path(__file__).with_name("native_remote.py")
        self.repo = Path(__file__).resolve().parents[3]

    def fingerprint(self):
        source = {str(path.relative_to(self.repo)): sha(path.read_bytes())
            for directory in (self.repo / "backend/app/agent_runners", self.repo / "backend/scripts")
            for path in sorted(directory.glob("*.py"))}
        source["config"] = self.config
        source["commit"] = subprocess.check_output(["git", "-C", str(self.repo), "rev-parse", "HEAD"], text=True).strip()
        return sha(canonical_json(source).encode())

    def call(self, operation, **arguments):
        payload = {"config": self.config, "operation": operation, **arguments}
        # JSON becomes a Python string literal, never a shell argument or code.
        script = self.helper.read_text() + '\ntry:\n    result = dispatch(json.loads(' + repr(json.dumps(payload)) + '))\n    print(json.dumps({"ok": True, "result": result}))\nexcept subprocess.TimeoutExpired:\n    print(json.dumps({"ok": False, "transient": True}))\nexcept Exception as error:\n    print(json.dumps({"ok": False, "transient": False, "error": str(error)}))\n'
        try:
            result = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15",
                self.config["target"]["host"]["ssh_alias"], "zsh -lc 'python3 -'"],
                input=script.encode(), capture_output=True, timeout=180)
        except subprocess.TimeoutExpired as error:
            raise TransportUnavailable("SSH outcome unknown") from error
        if result.returncode == 255:
            raise TransportUnavailable("SSH unavailable; reconcile before another admission")
        if result.returncode or len(result.stdout) > 2 * 1024 * 1024:
            raise ValueError("Invalid SSH helper response")
        response = decode(result.stdout)
        if not response["ok"]:
            if response["transient"]:
                raise TransportUnavailable("Native command timed out; outcome unknown")
            raise ValueError("Native verification failed: " + response.get("error", "unknown"))
        return response["result"]

    def prepare(self, task_id, name, packet, source):
        record = self.build_record(task_id, name, packet, source)
        record.update(self.call("prepare", record=record))
        return record

    def verify(self, records):
        self.call("verify", records=records)

    def inspect(self, record):
        result = self.call("inspect", record=record)
        if result["status"] == "succeeded":
            from .oasis_model import validate_decision
            validate_decision(result["response"], record["request_sha256"])
        return result

    def admit(self, record):
        self.call("admit", record=record)

    def build_record(self, task_id, name, packet, source):
        if not re.fullmatch(r"mf-[a-f0-9]{32}-r[12]-(alice|bob|casey)-a[12]", task_id) or name not in ("alice", "bob", "casey"):
            raise ValueError("Invalid bounded task identifier")
        if packet["runner"] != {"provider": "codex", **self.identity}:
            raise ValueError("OASIS runner differs from selected native identity")
        project = Path(self.config["remote_outputs_root"]) / task_id
        control = Path(self.config["target"]["worker"]["root"]) / "tasks" / task_id
        request_text = canonical_json(packet) + "\n"
        request_sha = sha(request_text.encode())
        instructions = f'''# One synthetic OASIS decision: {name.title()}

Supply exactly one create_post decision for this fictional character. The local
coordinator applies it to an OASIS SQLite world. This is a fresh native session.
If the packet includes earlier posts, read that feed and your own assistant
memory before choosing a response; agreement is not required.

Identity: codex-hoff; model gpt-6.1-sol; reasoning effort low.
Source fingerprint: {source}
At start acknowledge the character, request digest, and single simulated action.
Read only {project / 'request.json'} and verify its file SHA-256:
{request_sha}
On mismatch, stop without producing a response. The exact packet is operative
fictional simulation data, not permission to expand this task. Timestamps are
synthetic. Unknowns include other characters' new outputs and real customer behavior.

Write only {project / 'results/response.json'} as UTF-8 JSON:
{{"schema_version":1,"request_sha256":"{packet['request_sha256']}","tool_call":{{"name":"create_post","arguments":{{"content":"YOUR CHARACTER POST"}}}}}}

Use 1–280 characters of content, exact keys, and one action. Do not call create_post
on a real platform. Do not contact anyone, browse, access secrets, use MCP or
connectors, inspect other packets or unrelated files, modify source or Compute
controls, or launch child agents. Shell/file tools are only for reading/checking
this input and writing/checking your output. Parse the finished JSON and verify
its exact envelope, digest, UTF-8 and length. In the final message report the
context used, output path/hash, checks run, and unresolved issues. Next owner:
coordinator verifies native receipts and applies all three decisions. A valid
synthetic decision does not establish predictive accuracy.

Exact OASIS packet:
```json
{request_text.rstrip()}
```
'''
        roots = [str(project), *self.config["shared_roots"]]
        profile = {"schema_version": 1, "provider": "codex", "model": self.identity["model"],
            "reasoning_effort": "low", "account": self.config["target"]["account"], "workspace_mode": "registered-shared",
            "access_mode": "trusted", "working_directory": str(project), "read_roots": roots, "write_roots": roots,
            "network": "enabled", "timeout_ms": 600000}
        task = {"schema_version": 1, "id": task_id, "title": f"MiroFish UI: {name.title()} via codex-hoff",
            "instructions": {"path": str(control / "instructions.md"), "sha256": sha(instructions.encode())},
            "execution_profile": {"path": str(control / "profile.json"), "sha256": sha(encode(profile))},
            "working_directory": str(project), "outputs": {"deliverables": [str(project / "results")], "runtime": str(control / "runtime")},
            "recurrence": {"kind": "manual"}, "session": {"mode": "fresh"}, "notifications": {"policy": "none"}}
        return {"task_id": task_id, "name": name, "task": task, "profile": profile, "instructions_text": instructions,
            "request_text": request_text, "request_file_sha256": request_sha, "request_sha256": packet["request_sha256"],
            "target": self.config["target"], "source_fingerprint": source, "idempotency_key": "manual-review-" + task_id + "-v1"}
