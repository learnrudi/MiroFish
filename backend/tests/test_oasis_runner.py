import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from app.agent_runners.oasis_model import ReviewedActionModel
from app.agent_runners.exchange import FileExchange, ReviewRequired
from app.agent_runners.oasis_smoke import run_one_agent


@pytest.mark.asyncio
async def test_runner_decision_is_executed_once_by_real_oasis(tmp_path):
    calls = []

    def exchange(request):
        calls.append(request)
        return {"schema_version": 1, "request_sha256": request["request_sha256"],
                "tool_call": {"name": "create_post", "arguments": {"content": "My budget is $25."}}}

    model = ReviewedActionModel(exchange, identity="test-codex", model="gpt-6.1-sol", effort="low")
    db = tmp_path / "simulation.db"
    result = await run_one_agent(model, db)
    assert result["create_post_count"] == 1
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT content FROM post").fetchall() == [("My budget is $25.",)]
    assert len(calls) == 1
    assert calls[0]["tools"][0]["function"]["name"] == "create_post"
    assert any("Budget $25" in message.get("content", "") for message in calls[0]["messages"])


@pytest.mark.parametrize("invalid", ["stale", "unoffered", "extra_argument", "empty_content"])
def test_invalid_runner_decision_never_becomes_a_tool_call(invalid):
    def exchange(request):
        response = {"schema_version": 1, "request_sha256": request["request_sha256"],
                    "tool_call": {"name": "create_post", "arguments": {"content": "Hello."}}}
        if invalid == "stale":
            response["request_sha256"] = "0" * 64
        elif invalid == "unoffered":
            response["tool_call"]["name"] = "delete_post"
        elif invalid == "extra_argument":
            response["tool_call"]["arguments"]["user_id"] = 99
        else:
            response["tool_call"]["arguments"]["content"] = " "
        return response

    model = ReviewedActionModel(exchange, identity="test-codex", model="gpt-6.1-sol", effort="low")
    with pytest.raises(ValueError):
        model.run([{"role": "user", "content": "React."}], tools=[
            {"type": "function", "function": {"name": "create_post"}}])


def test_missing_response_exports_actual_model_request_before_stopping(tmp_path):
    model = ReviewedActionModel(FileExchange(tmp_path), identity="test-codex", model="gpt-6.1-sol", effort="low")
    messages = [{"role": "user", "content": "React to a $30 subscription."}]
    with pytest.raises(FileNotFoundError):
        model.run(messages, tools=[{"type": "function", "function": {"name": "create_post"}}])
    assert (tmp_path / "request.json").exists()
    packet = json.loads((tmp_path / "request.json").read_text())
    assert packet["messages"] == messages
    assert packet["runner"]["identity"] == "test-codex"


@pytest.mark.parametrize("invalid_file", ["duplicate", "oversized", "symlink"])
def test_response_file_boundary_rejects_unsafe_input(tmp_path, invalid_file):
    response = tmp_path / "response.json"
    if invalid_file == "duplicate":
        response.write_text('{"tool_call": 1, "tool_call": 2}')
    elif invalid_file == "oversized":
        response.write_text(json.dumps({"content": "a" * 20000}))
    else:
        target = tmp_path / "target.json"
        target.write_text('{}')
        response.symlink_to(target)
    with pytest.raises(ValueError):
        FileExchange(tmp_path, response)({"request_sha256": "fixture"})


@pytest.mark.asyncio
async def test_real_oasis_capture_surfaces_review_required_without_posting(tmp_path):
    model = ReviewedActionModel(FileExchange(tmp_path), identity="test-codex", model="gpt-6.1-sol", effort="low")
    with pytest.raises(ReviewRequired):
        await run_one_agent(model, tmp_path / "prepare.db")
    with sqlite3.connect(tmp_path / "prepare.db") as conn:
        assert conn.execute("SELECT COUNT(*) FROM post").fetchone() == (0,)


@pytest.mark.asyncio
async def test_file_roundtrip_applies_once_and_refuses_database_reuse(tmp_path):
    settings = dict(identity="test-codex", model="gpt-6.1-sol", effort="low")
    with pytest.raises(ReviewRequired):
        await run_one_agent(ReviewedActionModel(FileExchange(tmp_path), **settings), tmp_path / "prepare.db")
    packet = json.loads((tmp_path / "request.json").read_text())
    response = tmp_path / "response.json"
    response.write_text(json.dumps({"schema_version": 1, "request_sha256": packet["request_sha256"],
        "tool_call": {"name": "create_post", "arguments": {"content": "The price exceeds my budget."}}}))
    model = ReviewedActionModel(FileExchange(tmp_path, response), **settings)
    result = await run_one_agent(model, tmp_path / "apply.db")
    assert result == {"posts": ["The price exceeds my budget."], "create_post_count": 1}
    with pytest.raises(FileExistsError):
        await run_one_agent(model, tmp_path / "apply.db")
    with sqlite3.connect(tmp_path / "apply.db") as conn:
        assert conn.execute("SELECT COUNT(*) FROM post").fetchone() == (1,)


@pytest.mark.asyncio
async def test_runner_failure_is_visible_and_never_creates_a_post(tmp_path):
    def failed(request):
        raise TimeoutError("Runner deadline expired")

    model = ReviewedActionModel(failed, identity="test-codex", model="gpt-6.1-sol", effort="low")
    with pytest.raises(TimeoutError, match="deadline"):
        await run_one_agent(model, tmp_path / "failed.db")
    with sqlite3.connect(tmp_path / "failed.db") as conn:
        assert conn.execute("SELECT COUNT(*) FROM post").fetchone() == (0,)


def test_prepare_cli_has_one_machine_readable_status(tmp_path):
    script = Path(__file__).resolve().parents[1] / "scripts" / "run_oasis_runner.py"
    run = subprocess.run([sys.executable, str(script), "prepare", "--directory", str(tmp_path / "exchange"),
        "--identity", "test-codex", "--model", "gpt-6.1-sol", "--effort", "low"],
        text=True, capture_output=True, timeout=60)
    assert run.returncode == 0, run.stderr
    status = json.loads(run.stdout)
    assert status["status"] == "awaiting_review"
    assert Path(status["request"]).is_file()


@pytest.mark.asyncio
async def test_changed_request_json_type_is_rejected_before_oasis_posts(tmp_path):
    settings = dict(identity="test-codex", model="gpt-6.1-sol", effort="low")
    with pytest.raises(ReviewRequired):
        await run_one_agent(ReviewedActionModel(FileExchange(tmp_path), **settings), tmp_path / "prepare.db")
    path = tmp_path / "request.json"
    packet = json.loads(path.read_text())
    packet["schema_version"] = True  # Python equality conflates True and 1.
    path.write_text(json.dumps(packet))
    response = tmp_path / "response.json"
    response.write_text(json.dumps({"schema_version": 1, "request_sha256": packet["request_sha256"],
        "tool_call": {"name": "create_post", "arguments": {"content": "Must never be posted."}}}))
    model = ReviewedActionModel(FileExchange(tmp_path, response), **settings)
    with pytest.raises(ValueError, match="Request changed"):
        await run_one_agent(model, tmp_path / "apply.db")
    with sqlite3.connect(tmp_path / "apply.db") as conn:
        assert conn.execute("SELECT COUNT(*) FROM post").fetchone() == (0,)
