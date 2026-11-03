from concurrent.futures import ThreadPoolExecutor

from app.agent_runners.native_coordinator import NativeCoordinator
import pytest
from app.agent_runners.native_errors import TransportUnavailable


class Engine:
    def prepare(self, directory, number, previous):
        return {name: {"request_sha256": str(number) * 64} for name in ("alice", "bob", "casey")}

    def apply(self, directory, number, previous, responses):
        return {"result": str(directory / "result.json"), "display": {"posts": list(responses)}}


class Compute:
    identity = {"identity": "test-transport", "model": "fixture", "effort": "low"}

    def __init__(self):
        self.admissions = []
        self.source = "v1"

    def fingerprint(self):
        return self.source

    def prepare(self, task_id, name, packet, source):
        return {"task_id": task_id, "name": name, "packet": packet}

    def verify(self, records):
        pass

    def inspect(self, record):
        if record["task_id"] not in self.admissions:
            return {"status": "prepared"}
        return {"status": "succeeded", "job_id": record["task_id"], "response": {"content": record["name"]}}

    def admit(self, record):
        self.admissions.append(record["task_id"])


def advance_until(coordinator, run_id, status):
    for _ in range(40):
        run = coordinator.advance(run_id)
        if run["status"] == status:
            return run
    pytest.fail(f"Run stayed {run['status']}: {run.get('error')}")


def test_repeated_start_creates_one_durable_run_without_admitting_jobs(tmp_path):
    coordinator = NativeCoordinator(tmp_path, engine=None, compute=None)
    request_id = "a" * 32
    with ThreadPoolExecutor(max_workers=4) as pool:
        runs = list(pool.map(coordinator.start, [request_id] * 4))
    assert len({run["id"] for run in runs}) == 1
    assert all(run["status"] == "preparing" for run in runs)
    resumed = NativeCoordinator(tmp_path, engine=None, compute=None)
    assert resumed.start(request_id)["id"] == runs[0]["id"]


def test_exact_approval_required_for_each_round_and_duplicate_approval_is_safe(tmp_path):
    compute = Compute()
    c = NativeCoordinator(tmp_path, Engine(), compute)
    run = c.start("b" * 32)
    run = advance_until(c, run["id"], "awaiting_approval")
    assert compute.admissions == []
    with pytest.raises(ValueError, match="review"):
        c.approve(run["id"], "wrong")
    c.approve(run["id"], run["review_hash"])
    c.approve(run["id"], run["review_hash"])
    run = advance_until(c, run["id"], "awaiting_approval")
    assert run["round"] == 2
    assert len(compute.admissions) == 3
    c.approve(run["id"], run["review_hash"])
    run = advance_until(c, run["id"], "completed")
    assert len(set(compute.admissions)) == len(compute.admissions) == 6
    assert run["display"]["posts"] == ["alice", "bob", "casey"]


def test_failed_agent_retry_preserves_successes_and_requires_fresh_approval(tmp_path):
    class FailBob(Compute):
        def inspect(self, record):
            observed = super().inspect(record)
            if record["task_id"].endswith("bob-a1") and observed["status"] == "succeeded":
                return {"status": "failed", "job_id": record["task_id"]}
            return observed

    compute = FailBob()
    c = NativeCoordinator(tmp_path, Engine(), compute)
    run = c.start("c" * 32)
    run = advance_until(c, run["id"], "awaiting_approval")
    old_hash = run["review_hash"]
    c.approve(run["id"], old_hash)
    failed = advance_until(c, run["id"], "failed")
    with ThreadPoolExecutor(max_workers=4) as pool:
        retries = list(pool.map(lambda _: c.retry(run["id"], failed["version"]), range(4)))
    assert len({item['version'] for item in retries}) == 1
    run = retries[0]
    assert c.retry(run["id"], failed["version"])["version"] == run["version"]
    run = advance_until(c, run["id"], "awaiting_approval")
    assert len(compute.admissions) == 3
    with pytest.raises(ValueError, match="review"):
        c.approve(run["id"], old_hash)
    c.approve(run["id"], run["review_hash"])
    run = advance_until(c, run["id"], "awaiting_approval")
    assert run["round"] == 2
    assert len(compute.admissions) == 4
    assert compute.admissions[-1].endswith("bob-a2")


def test_lost_admission_reply_reconciles_without_duplicate_and_survives_restart(tmp_path):
    class LostReply(Compute):
        def admit(self, record):
            super().admit(record)
            if len(self.admissions) == 1:
                raise TransportUnavailable("Lost SSH reply after admission")

    compute = LostReply()
    c = NativeCoordinator(tmp_path, Engine(), compute)
    run = c.start("d" * 32)
    run = advance_until(c, run["id"], "awaiting_approval")
    c.approve(run["id"], run["review_hash"])
    run = advance_until(c, run["id"], "failed")
    c = NativeCoordinator(tmp_path, Engine(), compute)
    c.retry(run["id"], run["version"])
    run = advance_until(c, run["id"], "awaiting_approval")
    assert run["round"] == 2
    assert len(set(compute.admissions)) == len(compute.admissions) == 3


def test_source_drift_after_review_blocks_native_admission(tmp_path):
    compute = Compute()
    c = NativeCoordinator(tmp_path, Engine(), compute)
    run = c.start("e" * 32)
    run = advance_until(c, run["id"], "awaiting_approval")
    c.approve(run["id"], run["review_hash"])
    compute.source = "v2"
    run = c.advance(run["id"])
    assert run["status"] == "failed"
    assert run["error"]["retryable"] is False
    assert compute.admissions == []
