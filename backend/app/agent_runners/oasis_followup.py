"""One reviewed follow-up round, reconstructed from a verified group result."""

import json
import re

from .exchange import read_json
from .oasis_group import NAMES, apply_group, prepare_group
from .oasis_smoke import validate_prior_posts


def _digest(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value)


def _validate_previous(result):
    if not isinstance(result, dict) or set(result) != {
        "status", "posts", "create_post_count", "request_sha256", "database"
    }:
        raise ValueError("Expected an applied first-round group result")
    if (result["status"] != "applied" or type(result["create_post_count"]) is not int
            or result["create_post_count"] != 3 or not isinstance(result["database"], str)):
        raise ValueError("Expected three successful first-round actions")
    digests = result["request_sha256"]
    if not isinstance(digests, dict) or set(digests) != set(NAMES) or not all(
        _digest(value) for value in digests.values()
    ):
        raise ValueError("Expected three first-round request digests")
    validate_prior_posts(result["posts"])
    return result["posts"]


async def prepare_followup(directory, settings, previous_result, previous_sha256):
    if not _digest(previous_sha256):
        raise ValueError("An explicit first-round result SHA-256 is required")
    previous = read_json(previous_result, limit=131072, expected_sha256=previous_sha256)
    posts = _validate_previous(previous)
    status = await prepare_group(directory, settings, prior_posts=posts)
    with (directory / "history.json").open("x") as stream:
        json.dump({"source_sha256": previous_sha256, "result": previous}, stream, indent=2)
        stream.write("\n")
    status.update(round=2, previous_result_sha256=previous_sha256)
    return status


async def apply_followup(directory, responses):
    history = read_json(directory / "history.json", limit=131072)
    if (not isinstance(history, dict) or set(history) != {"source_sha256", "result"}
            or not _digest(history["source_sha256"])):
        raise ValueError("Invalid first-round history snapshot")
    posts = _validate_previous(history["result"])
    result = await apply_group(directory, responses, prior_posts=posts)
    result.update(round=2)
    return result
