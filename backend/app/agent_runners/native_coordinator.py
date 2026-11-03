"""Durable, bounded coordination: three agents, two separately reviewed rounds."""

import hashlib
import json
import re
import sqlite3
import threading
import traceback
from datetime import datetime, timezone
from pathlib import Path

from .exchange import canonical_json
from .native_errors import TransportUnavailable

NAMES = ("alice", "bob", "casey")


def digest(value):
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def new_round(number):
    return {"number": number, "packets": None, "agents": {
        name: {"attempt": 1, "status": "unprepared", "record": None}
        for name in NAMES}}


class NativeCoordinator:
    def __init__(self, root, engine, compute):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.engine = engine
        self.compute = compute
        self.database = self.root / "runs.sqlite3"
        self.worker_lock = threading.Lock()
        self.retry_lock = threading.Lock()
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, body TEXT NOT NULL)")

    def connect(self):
        return sqlite3.connect(self.database, timeout=10)

    def get(self, run_id):
        with self.connect() as db:
            row = db.execute("SELECT body FROM runs WHERE id = ?", (run_id,)).fetchone()
        if not row:
            raise KeyError("Run not found")
        return json.loads(row[0])

    def active(self):
        with self.connect() as db:
            runs = [json.loads(row[0]) for row in db.execute("SELECT body FROM runs ORDER BY rowid DESC")]
        return next((run for run in runs if run["status"] != "completed"), runs[0] if runs else None)

    def save(self, run, event):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            stored = json.loads(db.execute("SELECT body FROM runs WHERE id = ?", (run["id"],)).fetchone()[0])
            if stored["version"] != run["version"]:
                raise ValueError("Run changed; reload its current review")
            run["version"] += 1
            run["events"].append({"at": now(), "round": run["round"], "message": event})
            db.execute("UPDATE runs SET body = ? WHERE id = ?", (canonical_json(run), run["id"]))
        return run

    def start(self, request_id):
        if not isinstance(request_id, str) or not re.fullmatch(r"[a-f0-9]{32}", request_id):
            raise ValueError("Start requires a lowercase UUID without hyphens")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT body FROM runs WHERE id = ?", (request_id,)).fetchone()
            if existing:
                return json.loads(existing[0])
            if any(json.loads(row[0])["status"] != "completed" for row in db.execute("SELECT body FROM runs")):
                raise ValueError("An unfinished run already exists")
            run = {"id": request_id, "status": "preparing", "round": 1, "version": 1,
                   "source_fingerprint": self.compute.fingerprint() if self.compute else None,
                   "rounds": [new_round(1)], "review_hash": None, "display": None,
                   "error": None, "events": [{"at": now(), "round": 1, "message": "Preparing inactive tasks"}]}
            db.execute("INSERT INTO runs VALUES (?, ?)", (request_id, canonical_json(run)))
            return run

    def review(self, run_id):
        run = self.get(run_id)
        current = run["rounds"][-1]
        if not run["review_hash"]:
            raise ValueError("No review is ready")
        return {"sha256": run["review_hash"], "review": current["review"]}

    def retry(self, run_id, version):
        with self.retry_lock:
            return self._retry(run_id, version)

    def _retry(self, run_id, version):
        run = self.get(run_id)
        if type(version) is not int:
            raise ValueError("Retry requires the failed run version")
        if version in run.get("retried_versions", []):
            return run
        if run["version"] != version or run["status"] != "failed" or not run["error"].get("retryable"):
            raise ValueError("This failure cannot be retried; reload the run")
        current = run["rounds"][-1]
        if run["error"]["code"] == "transport_unavailable":
            run["status"] = run["error"]["resume_status"]
            run["error"] = None
            current.pop("preflight_done", None)
            run.setdefault("retried_versions", []).append(version)
            return self.save(run, "Reconciling existing tasks with the same admission keys")
        for agent in current["agents"].values():
            if agent["status"] == "failed":
                agent.update(attempt=agent["attempt"] + 1, status="unprepared", record=None)
                agent.pop("job_id", None)
        current.pop("approved_hash", None)
        current.pop("preflight_done", None)
        run.update(status="preparing", error=None, review_hash=None)
        run.setdefault("retried_versions", []).append(version)
        return self.save(run, "Preparing a fresh review for failed agents only")

    def approve(self, run_id, review_hash):
        run = self.get(run_id)
        if not review_hash or review_hash != run["review_hash"]:
            raise ValueError("The exact current review must be approved")
        current = run["rounds"][-1]
        if current.get("approved_hash") == review_hash:
            return run
        if run["status"] != "awaiting_approval":
            raise ValueError("Run is not awaiting review approval")
        if self.compute.fingerprint() != run["source_fingerprint"]:
            raise ValueError("Source changed since review; operator inspection required")
        current["approved_hash"] = review_hash
        current["approved_at"] = now()
        run["status"] = "queued"
        try:
            return self.save(run, "Exact round review approved")
        except ValueError:
            latest = self.get(run_id)
            if latest["rounds"][-1].get("approved_hash") == review_hash:
                return latest
            raise

    def advance(self, run_id):
        # Only the owning worker calls advance; the process also holds an OS lock.
        with self.worker_lock:
            try:
                return self._advance(run_id)
            except (OSError, ValueError, RuntimeError, KeyError, TypeError) as error:
                run = self.get(run_id)
                directory = self.root / run_id
                directory.mkdir(exist_ok=True)
                with (directory / "diagnostics.log").open("a") as log:
                    log.write(f"{now()} round={run['round']} state={run['status']}\n{traceback.format_exc()}\n")
                transport = isinstance(error, TransportUnavailable)
                run["error"] = {"code": "transport_unavailable" if transport else "integrity_or_local_failure",
                    "message": "Connection interrupted. Reconcile existing tasks." if transport else
                    "Verification or local application failed. Evidence is preserved for operator inspection.",
                    "retryable": transport, "resume_status": run["status"]}
                run["status"] = "failed"
                return self.save(run, run["error"]["message"])

    def _advance(self, run_id):
        run = self.get(run_id)
        if run["status"] in ("completed", "failed", "awaiting_approval"):
            return run
        if self.compute.fingerprint() != run["source_fingerprint"]:
            raise ValueError("Source or operator target drift")
        current = run["rounds"][-1]
        directory = self.root / run_id / f"round-{run['round']}"
        previous = run["rounds"][0].get("result") if run["round"] == 2 else None
        if run["status"] == "preparing":
            return self.prepare(run, current, directory, previous)
        if run["status"] in ("queued", "running"):
            if self.engine.prepare(directory, run["round"], previous) != current["packets"]:
                raise ValueError("Local OASIS input drift")
            return self.execute(run, current)
        if run["status"] == "applying":
            result = self.engine.apply(directory, run["round"], previous,
                {name: agent["response"] for name, agent in current["agents"].items()})
            current["result"] = result
            run["display"] = result["display"]
            if run["round"] == 1:
                run.update(round=2, status="preparing", review_hash=None)
                run["rounds"].append(new_round(2))
            else:
                run["status"] = "completed"
            return self.save(run, "Verified round applied to OASIS")
        return run

    def prepare(self, run, current, directory, previous):
        if current["packets"] is None:
            current["packets"] = self.engine.prepare(directory, run["round"], previous)
            return self.save(run, "Actual OASIS contexts captured")
        for name, agent in current["agents"].items():
            if agent["status"] == "unprepared":
                task_id = f"mf-{run['id']}-r{run['round']}-{name}-a{agent['attempt']}"
                agent["record"] = self.compute.prepare(task_id, name, current["packets"][name], run["source_fingerprint"])
                agent["status"] = "prepared"
                return self.save(run, f"{name}: inactive attempt {agent['attempt']} prepared")
        current["review"] = {"run_id": run["id"], "round": run["round"],
            "runner": self.compute.identity, "source_fingerprint": run["source_fingerprint"],
            "preserved_successes": [name for name, agent in current["agents"].items() if agent["status"] == "succeeded"],
            "tasks": [agent["record"] for agent in current["agents"].values()]}
        run["review_hash"] = digest(current["review"])
        run["status"] = "awaiting_approval"
        return self.save(run, "Exact round review ready; no jobs admitted")

    def execute(self, run, current):
        if current.get("approved_hash") != run["review_hash"]:
            raise ValueError("Missing exact review approval")
        if not current.get("preflight_done"):
            self.compute.verify([a["record"] for a in current["agents"].values()])
            current["preflight_done"] = True
            return self.save(run, "Reviewed native controls verified")
        # Admit every agent before polling; an ambiguous admission is reconciled
        # using the same task and idempotency key on the next attempt.
        for name, agent in current["agents"].items():
            if agent["status"] == "prepared":
                observed = self.compute.inspect(agent["record"])
                if observed["status"] == "prepared":
                    self.compute.admit(agent["record"])
                    agent["status"] = "queued"
                else:
                    agent.update(observed)
                run["status"] = "running"
                return self.save(run, f"{name}: {agent['status']}")
        changed = []
        for name, agent in current["agents"].items():
            if agent["status"] in ("queued", "running"):
                observed = self.compute.inspect(agent["record"])
                if observed["status"] == "prepared":
                    raise ValueError("Admitted job disappeared; operator inspection required")
                if any(agent.get(key) != value for key, value in observed.items()):
                    agent.update(observed)
                    changed.append(f"{name}: {agent['status']}")
        if all(a["status"] == "succeeded" for a in current["agents"].values()):
            run["status"] = "applying"
            changed.append("All native receipts and responses verified")
        elif all(a["status"] in ("succeeded", "failed") for a in current["agents"].values()):
            run["status"] = "failed"
            run["error"] = {"code": "native_job_failed", "message": "A native job failed; successful agents are preserved.",
                "retryable": all(a["attempt"] < 2 for a in current["agents"].values() if a["status"] == "failed")}
            changed.append("Native round failed; no posts applied")
        return self.save(run, "; ".join(changed)) if changed else run
