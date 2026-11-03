"""Reuse the real OASIS harness in a subprocess; runtime artifacts stay off Git."""

import hashlib
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

from .exchange import canonical_json, read_json
from .native_coordinator import NAMES, now


class OasisEngine:
    def __init__(self, identity):
        self.identity = identity
        self.script = Path(__file__).resolve().parents[2] / "scripts" / "run_oasis_runner.py"

    def command(self, arguments, directory):
        directory.parent.mkdir(parents=True, exist_ok=True)
        with (directory.parent / "oasis.log").open("ab") as log:
            result = subprocess.run([sys.executable, str(self.script), *arguments],
                stdout=subprocess.PIPE, stderr=log, timeout=180, check=False)
        if result.returncode:
            raise RuntimeError("OASIS failed; inspect the private oasis.log")
        return json.loads(result.stdout)

    def prepare(self, directory, number, previous):
        marker = directory / "prepared.json"
        if directory.exists():
            saved = read_json(marker, limit=524288)
            if saved["previous_sha256"] != (previous["sha256"] if previous else None):
                raise ValueError("Previous result drift")
            packets = {name: read_json(directory / name / "request.json", limit=131072) for name in NAMES}
            if saved["packets"] != packets:
                raise ValueError("Prepared context drift")
            return packets
        arguments = ["prepare-group" if number == 1 else "prepare-followup", "--directory", str(directory)]
        for key in ("identity", "model", "effort"):
            arguments.extend([f"--{key}", self.identity[key]])
        if previous:
            arguments.extend(["--previous-result", previous["result"], "--previous-sha256", previous["sha256"]])
        self.command(arguments, directory)
        packets = {name: read_json(directory / name / "request.json", limit=131072) for name in NAMES}
        with marker.open("x") as stream:
            stream.write(canonical_json({"previous_sha256": previous["sha256"] if previous else None, "packets": packets}))
        return packets

    def apply(self, directory, number, previous, responses):
        response_dir = directory / "responses"
        response_dir.mkdir(exist_ok=True)
        for name, response in responses.items():
            path = response_dir / f"{name}.json"
            if path.exists():
                if read_json(path) != response:
                    raise ValueError("Response drift")
            else:
                path.write_text(canonical_json(response), encoding="utf-8")
        path = directory / "result.json"
        if not path.exists():
            if any((directory / name).exists() for name in ("verify.db", "apply.db")):
                raise ValueError("Partial OASIS application preserved; automatic replay is forbidden")
            self.command(["apply-group" if number == 1 else "apply-followup", "--directory", str(directory),
                "--responses", str(response_dir)], directory)
        result = read_json(path, limit=131072)
        self.verify_result(directory, number, previous, responses, result)
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        return {"result": str(path), "sha256": sha, "display": {
            "schema_version": 1, "title": "A price increase, three perspectives",
            "scenario": "A note-taking service raises its monthly price from $20 to $30 next month, without explaining the change or adding features.",
            "recorded_at": now(), "source_sha256": sha, "runner": self.identity, "posts": result["posts"]}}

    def verify_result(self, directory, number, previous, responses, result):
        from .oasis_model import validate_decision

        packets = self.prepare(directory, number, previous)
        expected = []
        if previous:
            prior = read_json(previous["result"], limit=131072, expected_sha256=previous["sha256"])
            expected.extend(prior["posts"])
        for name in NAMES:
            content = validate_decision(responses[name], packets[name]["request_sha256"])["arguments"]["content"]
            expected.append({"user_name": name, "content": content})
        if (result["status"] != "applied" or result["create_post_count"] != number * 3 or result["posts"] != expected
                or result["request_sha256"] != {name: packets[name]["request_sha256"] for name in NAMES}
                or result["database"] != str(directory / "apply.db")):
            raise ValueError("OASIS result does not match verified responses")
        with sqlite3.connect((directory / "apply.db").as_uri() + "?mode=ro", uri=True) as db:
            rows = db.execute("SELECT u.user_name,p.content FROM post p JOIN user u ON p.user_id=u.user_id ORDER BY p.post_id").fetchall()
            traces = db.execute("SELECT u.user_name,COUNT(*) FROM trace t JOIN user u ON t.user_id=u.user_id WHERE action='create_post' GROUP BY u.user_name ORDER BY u.user_name").fetchall()
            if (rows != [(p["user_name"], p["content"]) for p in expected] or traces != [(name, number) for name in NAMES]
                    or db.execute("PRAGMA integrity_check").fetchone() != ("ok",)):
                raise ValueError("OASIS database verification failed")
