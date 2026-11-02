"""File exchange for an explicitly reviewed native runner decision."""

import json
import os
import stat
from pathlib import Path


class ReviewRequired(FileNotFoundError):
    """The request was captured, but no reviewed response was supplied."""


def read_json(path, limit=16384):
    """Read bounded regular JSON files; never follow the final symlink."""
    path = Path(path)
    if path.is_symlink():
        raise ValueError("Exchange files must not be symlinks")
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError("Exchange file must be a regular file")
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("Exchange file exceeds size limit")

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result

    def invalid_constant(value):
        raise ValueError("Non-finite JSON number")

    return json.loads(raw.decode("utf-8"), object_pairs_hook=unique, parse_constant=invalid_constant)


class FileExchange:
    def __init__(self, directory, response_path=None):
        self.directory = Path(directory)
        self.response_path = Path(response_path) if response_path else None

    def __call__(self, request):
        path = self.directory / "request.json"
        if path.exists() or path.is_symlink():
            if read_json(path, limit=131072) != request:
                raise ValueError("Request changed; prepare a separate reviewed exchange")
        else:
            with path.open("x") as stream:
                json.dump(request, stream, indent=2, ensure_ascii=False, allow_nan=False)
                stream.write("\n")
        if self.response_path is None:
            raise ReviewRequired(f"Review {path} and provide a runner response")
        return read_json(self.response_path)
