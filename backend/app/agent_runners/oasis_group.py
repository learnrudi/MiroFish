"""Reviewed file exchanges for three isolated decisions in one OASIS round."""

from .exchange import FileExchange, ReviewRequired, canonical_json, read_json
from .oasis_model import ReviewedActionModel, validate_decision
from .oasis_smoke import GROUP_PERSONAS, run_group

NAMES = tuple(name.lower() for name, _ in GROUP_PERSONAS)


async def prepare_group(directory, settings):
    directory.mkdir(parents=True, exist_ok=False)
    models = []
    for name in NAMES:
        (directory / name).mkdir()
        models.append(ReviewedActionModel(FileExchange(directory / name), **settings))
    await _capture_requests(models, directory / "prepare.db")
    return {"status": "awaiting_review", "requests": [
        {"user_name": name, "request": str(directory / name / "request.json"),
         "request_sha256": read_json(directory / name / "request.json", limit=131072)["request_sha256"]}
        for name in NAMES]}


async def _capture_requests(models, database):
    try:
        await run_group(models, database)
    except ReviewRequired:
        # OASIS swallows exceptions. All three must have reached capture, and
        # none may hide a different failure behind the first missing response.
        for model in models:
            if not isinstance(model.last_error, ReviewRequired):
                if model.last_error is not None:
                    raise model.last_error
                raise RuntimeError("Not all three agents captured a reviewable request")
    else:
        raise RuntimeError("Capture unexpectedly executed an action")


def _snapshot_exchange(request, response=None):
    """Freeze validated inputs; do not re-read mutable files during application."""
    expected = canonical_json(request)

    def exchange(actual):
        if canonical_json(actual) != expected:
            raise ValueError("Request changed; prepare a separate reviewed exchange")
        if response is None:
            raise ReviewRequired("Request matches; verification must not post")
        return response

    return exchange


async def apply_group(directory, responses):
    models = []
    verification_models = []
    digests = {}
    for name in NAMES:
        request = read_json(directory / name / "request.json", limit=131072)
        response = read_json(responses / f"{name}.json")
        validate_decision(response, request["request_sha256"])
        runner = request["runner"]
        settings = dict(identity=runner["identity"], model=runner["model"], effort=runner["effort"])
        models.append(ReviewedActionModel(_snapshot_exchange(request, response), **settings))
        verification_models.append(ReviewedActionModel(_snapshot_exchange(request), **settings))
        digests[name] = request["request_sha256"]
    # Verify every regenerated context before allowing any agent to post. This
    # avoids a partial application when a later agent's packet has drifted.
    await _capture_requests(verification_models, directory / "verify.db")
    result = await run_group(models, directory / "apply.db")
    result.update(status="applied", request_sha256=digests, database=str(directory / "apply.db"))
    return result
