"""Capture a real OASIS request, or apply its reviewed runner response.

No Compute admission, authentication changes, model API calls, or Zep calls.
"""

import argparse
import asyncio
import contextlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Upstream libraries attach console handlers at import time. Keep stdout JSON-only.
with contextlib.redirect_stdout(sys.stderr):
    from app.agent_runners.exchange import FileExchange, ReviewRequired, read_json
    from app.agent_runners.oasis_model import ReviewedActionModel
    from app.agent_runners.oasis_smoke import run_one_agent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--directory", type=Path, required=True)
    prepare.add_argument("--identity", required=True)
    prepare.add_argument("--model", required=True)
    prepare.add_argument("--effort", required=True)
    apply = commands.add_parser("apply")
    apply.add_argument("--directory", type=Path, required=True)
    apply.add_argument("--response", type=Path, required=True)
    args = parser.parse_args()
    directory = args.directory.resolve()
    try:
        if args.command == "prepare":
            settings = dict(identity=args.identity, model=args.model, effort=args.effort)
            model = ReviewedActionModel(FileExchange(directory), **settings)
            directory.mkdir(parents=True, exist_ok=False)
            with contextlib.redirect_stdout(sys.stderr):
                try:
                    asyncio.run(run_one_agent(model, directory / "prepare.db"))
                except ReviewRequired:
                    pass
                else:
                    raise RuntimeError("Capture unexpectedly executed an action")
            request = read_json(directory / "request.json", limit=131072)
            result = {"status": "awaiting_review", "request": str(directory / "request.json"),
                      "request_sha256": request["request_sha256"]}
        else:
            request = read_json(directory / "request.json", limit=131072)
            runner = request["runner"]
            model = ReviewedActionModel(FileExchange(directory, args.response),
                identity=runner["identity"], model=runner["model"], effort=runner["effort"])
            with contextlib.redirect_stdout(sys.stderr):
                result = asyncio.run(run_one_agent(model, directory / "apply.db"))
            result.update(status="applied", request_sha256=request["request_sha256"],
                          database=str(directory / "apply.db"))
            with (directory / "result.json").open("x") as stream:
                json.dump(result, stream, indent=2)
                stream.write("\n")
        print(json.dumps(result))
        return 0
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
