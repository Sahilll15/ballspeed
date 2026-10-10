"""Thin subprocess wrappers around the ffmpeg and ffprobe binaries."""

import shutil
import subprocess
from collections.abc import Sequence


class FFmpegError(RuntimeError):
    pass


def binary(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise FFmpegError(f"{name} not found on PATH. Install it (macOS: brew install ffmpeg).")
    return path


def run(name: str, args: Sequence[str], *, stdin: bytes | None = None) -> bytes:
    proc = subprocess.run(
        [binary(name), *args],
        input=stdin,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        tail = proc.stderr.decode(errors="replace").strip().splitlines()[-5:]
        raise FFmpegError(f"{name} failed ({proc.returncode}): " + " | ".join(tail))
    return proc.stdout
