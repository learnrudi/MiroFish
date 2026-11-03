from app.agent_runners.native_engine import OasisEngine


def test_real_oasis_rounds_recover_completed_application_without_duplicate_posts(tmp_path):
    engine = OasisEngine({"identity": "codex-hoff", "model": "gpt-6.1-sol", "effort": "low"})
    previous = None
    for number in (1, 2):
        directory = tmp_path / f"round-{number}"
        packets = engine.prepare(directory, number, previous)
        responses = {name: {"schema_version": 1, "request_sha256": packet["request_sha256"],
            "tool_call": {"name": "create_post", "arguments": {"content": f"{name} round {number}."}}}
            for name, packet in packets.items()}
        result = engine.apply(directory, number, previous, responses)
        recovered = engine.apply(directory, number, previous, responses)
        assert recovered["sha256"] == result["sha256"]
        assert len(recovered["display"]["posts"]) == number * 3
        previous = result


def test_partial_application_is_preserved_and_not_replayed(tmp_path):
    import pytest
    engine = OasisEngine({"identity": "codex-hoff", "model": "gpt-6.1-sol", "effort": "low"})
    directory = tmp_path / 'partial'
    directory.mkdir()
    partial = directory / 'apply.db'
    partial.write_bytes(b'preserved partial database')
    with pytest.raises(ValueError, match='Partial OASIS'):
        engine.apply(directory, 1, None, {})
    assert partial.read_bytes() == b'preserved partial database'
    assert not (directory / 'result.json').exists()
