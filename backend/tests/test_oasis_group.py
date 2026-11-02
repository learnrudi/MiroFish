import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from app.agent_runners.oasis_model import ReviewedActionModel
from app.agent_runners.oasis_smoke import run_group
from app.agent_runners.oasis_group import prepare_group, apply_group


@pytest.mark.asyncio
async def test_three_agents_share_one_world_and_keep_their_contexts(tmp_path):
    calls = {}
    names = ("Alice", "Bob", "Casey")

    def exchange_for(name):
        def exchange(request):
            calls[name] = request
            return {"schema_version": 1, "request_sha256": request["request_sha256"],
                    "tool_call": {"name": "create_post", "arguments": {"content": f"{name}'s perspective."}}}
        return exchange

    models = [ReviewedActionModel(exchange_for(name), identity="test-codex", model="gpt-6.1-sol", effort="low")
              for name in names]
    database = tmp_path / "group.db"
    result = await run_group(models, database)
    with sqlite3.connect(database) as conn:
        posts = conn.execute("SELECT u.user_name, p.content FROM post p JOIN user u ON u.user_id=p.user_id ORDER BY u.user_name").fetchall()
    assert posts == [(name.lower(), f"{name}'s perspective.") for name in names]
    assert result["create_post_count"] == 3
    assert len({packet["request_sha256"] for packet in calls.values()}) == 3
    for name, packet in calls.items():
        context = "\n".join(message["content"] for message in packet["messages"])
        assert f"You are {name}" in context
        assert all(f"You are {other}" not in context for other in names if other != name)


def test_group_cli_captures_three_requests_and_applies_each_response_once(tmp_path):
    script = Path(__file__).resolve().parents[1] / "scripts" / "run_oasis_runner.py"
    directory = tmp_path / "exchange"
    prepared = subprocess.run([sys.executable, str(script), "prepare-group", "--directory", str(directory),
        "--identity", "test-codex", "--model", "gpt-6.1-sol", "--effort", "low"],
        text=True, capture_output=True, timeout=60)
    assert prepared.returncode == 0, prepared.stderr
    status = json.loads(prepared.stdout)
    assert status["status"] == "awaiting_review"
    assert [item["user_name"] for item in status["requests"]] == ["alice", "bob", "casey"]
    with sqlite3.connect(directory / "prepare.db") as conn:
        assert conn.execute("SELECT COUNT(*) FROM post").fetchone() == (0,)
    responses = tmp_path / "responses"
    responses.mkdir()
    for item in status["requests"]:
        (responses / f"{item['user_name']}.json").write_text(json.dumps({
            "schema_version": 1, "request_sha256": item["request_sha256"],
            "tool_call": {"name": "create_post", "arguments": {"content": item["user_name"]}}}))
    command = [sys.executable, str(script), "apply-group", "--directory", str(directory),
               "--responses", str(responses)]
    applied = subprocess.run(command, text=True, capture_output=True, timeout=60)
    assert applied.returncode == 0, applied.stderr
    result = json.loads(applied.stdout)
    assert result["status"] == "applied"
    assert result["posts"] == [{"user_name": name, "content": name} for name in ("alice", "bob", "casey")]
    assert result["create_post_count"] == 3
    repeated = subprocess.run(command, text=True, capture_output=True, timeout=60)
    assert repeated.returncode == 1
    with sqlite3.connect(directory / "apply.db") as conn:
        assert conn.execute("SELECT COUNT(*) FROM post").fetchone() == (3,)


@pytest.mark.asyncio
async def test_changed_third_request_cannot_partially_apply_the_group(tmp_path):
    directory = tmp_path / "exchange"
    status = await prepare_group(directory, dict(identity="test-codex", model="gpt-6.1-sol", effort="low"))
    responses = tmp_path / "responses"
    responses.mkdir()
    for item in status["requests"]:
        (responses / f"{item['user_name']}.json").write_text(json.dumps({
            "schema_version": 1, "request_sha256": item["request_sha256"],
            "tool_call": {"name": "create_post", "arguments": {"content": item["user_name"]}}}))
    path = directory / "casey" / "request.json"
    request = json.loads(path.read_text())
    request["schema_version"] = True
    path.write_text(json.dumps(request))
    with pytest.raises(ValueError, match="Request changed"):
        await apply_group(directory, responses)
    if (directory / "apply.db").exists():
        with sqlite3.connect(directory / "apply.db") as conn:
            assert conn.execute("SELECT COUNT(*) FROM post").fetchone() == (0,)


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid", ["swapped", "unsupported", "missing", "non_utf8"])
async def test_invalid_group_response_is_rejected_before_any_application(tmp_path, invalid):
    directory = tmp_path / "exchange"
    status = await prepare_group(directory, dict(identity="test-codex", model="gpt-6.1-sol", effort="low"))
    responses = tmp_path / "responses"
    responses.mkdir()
    for item in status["requests"]:
        (responses / f"{item['user_name']}.json").write_text(json.dumps({
            "schema_version": 1, "request_sha256": item["request_sha256"],
            "tool_call": {"name": "create_post", "arguments": {"content": item["user_name"]}}}))
    path = responses / "casey.json"
    if invalid == "missing":
        path.unlink()
    elif invalid == "swapped":
        path.write_bytes((responses / "alice.json").read_bytes())
    else:
        response = json.loads(path.read_text())
        if invalid == "non_utf8":
            response["tool_call"]["arguments"]["content"] = "\ud800"
        else:
            response["tool_call"]["name"] = "delete_post"
        path.write_text(json.dumps(response))
    with pytest.raises((ValueError, FileNotFoundError)):
        await apply_group(directory, responses)
    assert not (directory / "apply.db").exists()


@pytest.mark.asyncio
async def test_group_runtime_failure_is_visible_and_preserves_partial_evidence(tmp_path):
    def exchange(request):
        if any("You are Bob" in message["content"] for message in request["messages"]):
            raise TimeoutError("Bob's runner timed out")
        return {"schema_version": 1, "request_sha256": request["request_sha256"],
                "tool_call": {"name": "create_post", "arguments": {"content": "A successful action."}}}

    models = [ReviewedActionModel(exchange, identity="test-codex", model="gpt-6.1-sol", effort="low")
              for _ in range(3)]
    database = tmp_path / "partial.db"
    with pytest.raises(TimeoutError, match="Bob"):
        await run_group(models, database)
    with sqlite3.connect(database) as conn:
        assert conn.execute("SELECT COUNT(*) FROM post").fetchone() == (2,)
    with pytest.raises(FileExistsError):
        await run_group(models, database)
