import json
import hashlib
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from app.agent_runners.oasis_model import ReviewedActionModel
from app.agent_runners.oasis_smoke import run_group
from app.agent_runners.oasis_followup import prepare_followup, apply_followup

PRIOR = [{"user_name": name, "content": f"{name}'s first position."}
         for name in ("alice", "bob", "casey")]


@pytest.mark.asyncio
async def test_second_round_has_real_feed_own_memory_and_six_attributed_posts(tmp_path):
    requests = {}

    def exchange_for(name):
        def exchange(packet):
            requests[name] = packet
            return {"schema_version": 1, "request_sha256": packet["request_sha256"],
                    "tool_call": {"name": "create_post", "arguments": {"content": f"{name}'s follow-up."}}}
        return exchange

    models = [ReviewedActionModel(exchange_for(row["user_name"]), identity="test-codex",
              model="gpt-6.1-sol", effort="low") for row in PRIOR]
    database = tmp_path / "rounds.db"
    await run_group(models, database, prior_posts=PRIOR)
    for name, packet in requests.items():
        memory = [m["content"] for m in packet["messages"] if m["role"] == "assistant"]
        assert memory == [f"{name}'s first position."]
        feed = packet["messages"][-1]["content"]
        assert all(row["content"] in feed for row in PRIOR)
        assert "follow-up" in packet["messages"][0]["content"]
    with sqlite3.connect(database) as conn:
        posts = conn.execute("SELECT u.user_name,p.content FROM post p JOIN user u ON u.user_id=p.user_id ORDER BY p.post_id").fetchall()
        traces = conn.execute("SELECT user_id,COUNT(*) FROM trace WHERE action='create_post' GROUP BY user_id").fetchall()
    assert posts[:3] == [(row["user_name"], row["content"]) for row in PRIOR]
    assert posts[3:] == [(row["user_name"], f"{row['user_name']}'s follow-up.") for row in PRIOR]
    assert traces == [(0, 2), (1, 2), (2, 2)]


def test_followup_cli_regenerates_identical_feed_and_preserves_round_one(tmp_path):
    previous = tmp_path / "previous.json"
    previous.write_text(json.dumps({"status": "applied", "posts": PRIOR, "create_post_count": 3,
        "request_sha256": {row["user_name"]: str(i) * 64 for i, row in enumerate(PRIOR)},
        "database": "test-fixture.db"}))
    original = previous.read_bytes()
    script = Path(__file__).resolve().parents[1] / "scripts" / "run_oasis_runner.py"
    directory = tmp_path / "followup"
    prepare = subprocess.run([sys.executable, str(script), "prepare-followup", "--directory", str(directory),
        "--previous-result", str(previous), "--previous-sha256", hashlib.sha256(original).hexdigest(),
        "--identity", "test-codex", "--model", "gpt-6.1-sol", "--effort", "low"],
        capture_output=True, text=True, timeout=60)
    assert prepare.returncode == 0, prepare.stderr
    status = json.loads(prepare.stdout)
    assert status["status"] == "awaiting_review"
    responses = tmp_path / "responses"
    responses.mkdir()
    for item in status["requests"]:
        (responses / f"{item['user_name']}.json").write_text(json.dumps({
            "schema_version": 1, "request_sha256": item["request_sha256"],
            "tool_call": {"name": "create_post", "arguments": {"content": "A follow-up."}}}))
    apply = subprocess.run([sys.executable, str(script), "apply-followup", "--directory", str(directory),
        "--responses", str(responses)], capture_output=True, text=True, timeout=60)
    assert apply.returncode == 0, apply.stderr
    result = json.loads(apply.stdout)
    assert result["create_post_count"] == 6
    assert result["posts"][:3] == PRIOR
    assert previous.read_bytes() == original
    for filename, count in (("prepare.db", 3), ("verify.db", 3), ("apply.db", 6)):
        with sqlite3.connect(directory / filename) as conn:
            assert conn.execute("SELECT COUNT(*) FROM post").fetchone() == (count,)


@pytest.fixture
def previous_result(tmp_path):
    path = tmp_path / "previous.json"
    path.write_text(json.dumps({"status": "applied", "posts": PRIOR, "create_post_count": 3,
        "request_sha256": {row["user_name"]: str(i) * 64 for i, row in enumerate(PRIOR)},
        "database": "test-fixture.db"}))
    return path


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid", ["hash", "attribution", "count", "non_utf8"])
async def test_invalid_previous_result_cannot_create_a_followup_world(tmp_path, previous_result, invalid):
    data = json.loads(previous_result.read_text())
    if invalid == "attribution":
        data["posts"][2]["user_name"] = "bob"
    elif invalid == "count":
        data["create_post_count"] = True
    elif invalid == "non_utf8":
        data["posts"][2]["content"] = "\ud800"
    previous_result.write_text(json.dumps(data))
    digest = "0" * 64 if invalid == "hash" else hashlib.sha256(previous_result.read_bytes()).hexdigest()
    directory = tmp_path / "followup"
    with pytest.raises(ValueError):
        await prepare_followup(directory, dict(identity="test-codex", model="gpt-6.1-sol", effort="low"),
                               previous_result, digest)
    assert not directory.exists()


@pytest.mark.asyncio
async def test_changed_history_is_rejected_before_followup_posts(tmp_path, previous_result):
    directory = tmp_path / "followup"
    digest = hashlib.sha256(previous_result.read_bytes()).hexdigest()
    status = await prepare_followup(directory, dict(identity="test-codex", model="gpt-6.1-sol", effort="low"),
                                    previous_result, digest)
    responses = tmp_path / "responses"
    responses.mkdir()
    for item in status["requests"]:
        (responses / f"{item['user_name']}.json").write_text(json.dumps({
            "schema_version": 1, "request_sha256": item["request_sha256"],
            "tool_call": {"name": "create_post", "arguments": {"content": "Must not appear."}}}))
    history = directory / "history.json"
    data = json.loads(history.read_text())
    data["result"]["posts"][2]["content"] = "Changed earlier position."
    history.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="Request changed"):
        await apply_followup(directory, responses)
    assert not (directory / "apply.db").exists()
    with sqlite3.connect(directory / "verify.db") as conn:
        assert conn.execute("SELECT COUNT(*) FROM post").fetchone() == (3,)
    assert hashlib.sha256(previous_result.read_bytes()).hexdigest() == digest
