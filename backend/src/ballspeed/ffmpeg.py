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


DEFAULT_TIMEOUT_S = 300.0

# Uploaded files are untrusted: only the QuickTime/MP4 demuxer reading a local file, so a
# playlist disguised as .mp4 cannot pull in other files or URLs.
SAFE_INPUT = ("-protocol_whitelist", "file", "-f", "mov")


def run(
    name: str,
    args: Sequence[str],
    *,
    stdin: bytes | None = None,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> bytes:
    try:
        proc = subprocess.run(
            [binary(name), *args],
            input=stdin,
            capture_output=True,
            check=False,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired as e:
        raise FFmpegError(f"{name} timed out after {timeout_s:.0f} s") from e
    if proc.returncode != 0:
        tail = proc.stderr.decode(errors="replace").strip().splitlines()[-5:]
        raise FFmpegError(f"{name} failed ({proc.returncode}): " + " | ".join(tail))
    return proc.stdout
