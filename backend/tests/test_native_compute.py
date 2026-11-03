"""Contract checks use synthetic receipts, never user credential files."""
import copy
from pathlib import Path

import pytest

from app.agent_runners.native_compute import NativeCompute, IDENTITY
from app.agent_runners.native_remote import verified_completion, sha, encode, RemoteWorker


def config(root):
    return {"target": {"identity": "codex-hoff", "provider": "codex", "account": {
        "id": "codex-hoff", "email": "owner@example.test", "config_directory": str(root / "account")},
        "host": {"transport": "ssh", "ssh_alias": "fixture-host"}, "worker": {
            "root": str(root / "worker"), "python": str(root / "python"), "bundle": str(root / "bundle"),
            "manifest_sha256": "a" * 64}}, "remote_outputs_root": str(root / "outputs"),
        "shared_roots": [str(root / name) for name in ("clients", "source", "runtime")]}


def receipt_fixture(root):
    compute = NativeCompute(config(root))
    packet = {"runner": {"provider": "codex", **IDENTITY}, "request_sha256": "b" * 64}
    record = compute.build_record("mf-" + "a" * 32 + "-r1-alice-a1", "alice", packet, "c" * 64)
    record["definition_sha256"] = "d" * 64
    binding = {"id": record["task_id"], "revision": 1, "definition_sha256": "d" * 64}
    run = {"status": "succeeded", "attempt": 1, "task": binding, "job_id": "job_123", "spec_sha256": "e" * 64,
        "request": {"path": "/request", "sha256": "f" * 64}}
    output = encode({"schema_version": 1, "request_sha256": "b" * 64, "tool_call": {"name": "create_post", "arguments": {"content": "A synthetic decision."}}})
    completion = {"status": "completed", "outcome": "complete", "compute": {"job_id": run["job_id"], "attempt": 1, "spec_sha256": run["spec_sha256"]},
        "task": binding, "request": run["request"], "instructions": record["task"]["instructions"], "execution_profile": record["task"]["execution_profile"],
        "account": record["profile"]["account"], "observed_account": {**record["profile"]["account"], "auth_method": "chatgpt"},
        "access_mode": "trusted", "reasoning_effort": "low", "launch": {"id": "launch_123", "native_session_id": "session_123"},
        "outputs": [{"path": record["task"]["outputs"]["deliverables"][0] + "/response.json", "sha256": sha(output), "bytes": len(output)}]}
    launch = {**completion, "launch_id": "launch_123", "provider": "codex", "model": IDENTITY["model"],
        "working_directory": record["profile"]["working_directory"], "workspace_mode": "registered-shared"}
    return record, run, completion, launch, output


@pytest.mark.parametrize("mutation", ["account", "model", "effort", "request", "job", "output", "task", "session"])
def test_receipt_drift_rejected(tmp_path, mutation):
    values = receipt_fixture(tmp_path)
    record, run, completion, launch, output = copy.deepcopy(values)
    assert verified_completion(*values)["tool_call"]["arguments"]["content"] == "A synthetic decision."
    if mutation == "account": completion["observed_account"]["id"] = "another"
    if mutation == "model": launch["model"] = "another"
    if mutation == "effort": launch["reasoning_effort"] = "high"
    if mutation == "request": completion["request"] = {"sha256": "wrong"}
    if mutation == "job": completion["compute"]["job_id"] = "other_job"
    if mutation == "output": output += b" "
    if mutation == "task": run["task"]["revision"] = 2
    if mutation == "session": completion["launch"]["native_session_id"] = ""
    with pytest.raises(ValueError):
        verified_completion(record, run, completion, launch, output)


def test_preparation_recovers_ambiguous_create_and_refuses_input_drift(tmp_path):
    settings = config(tmp_path)
    compute = NativeCompute(settings)
    record = receipt_fixture(tmp_path)[0]
    calls = []

    class Worker(RemoteWorker):
        def release(self):
            pass

        def command(self, arguments, missing_ok=False):
            operation = arguments[len(self.cli) + 1]
            calls.append(operation)
            return {"revision": 1, "state": "inactive", "definition_sha256": record["definition_sha256"]}

    worker = Worker(settings)
    assert worker.prepare(record) == worker.prepare(record)
    assert "create" not in calls and "run-now" not in calls
    Path(record["task"]["working_directory"], "request.json").write_text("changed")
    with pytest.raises(ValueError, match="drift"):
        worker.prepare(record)


@pytest.mark.parametrize(('native_status', 'attempt', 'expected'), [('queued', 0, 'queued'), ('running', 1, 'running'), ('dead', 1, 'failed')])
def test_real_compute_status_contract_reaches_ui_states(tmp_path, native_status, attempt, expected):
    record, run, _, _, _ = receipt_fixture(tmp_path)
    run.update(status=native_status, attempt=attempt, completion_receipt=None)

    class Worker(RemoteWorker):
        def verify(self, record):
            pass

        def command(self, arguments, missing_ok=False):
            if arguments[len(self.cli)] == 'task':
                return {'runs': [run]}
            return {'job': {'id': run['job_id'], 'status': native_status, 'attempt': attempt}}

    assert Worker(config(tmp_path)).inspect(record)['status'] == expected
