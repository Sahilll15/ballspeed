"""Probe uploaded videos for real timing and extract frames.

Timing always comes from per-frame presentation timestamps, never from the nominal fps.
"""

import json
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

import numpy as np

from ballspeed import ffmpeg

# Android writes the sensor rate here when a slow-mo clip is stored with a 30 fps timeline.
CAPTURE_FPS_TAGS = ("com.android.capture.fps", "com.apple.quicktime.capture-fps")
VFR_SPREAD_THRESHOLD = 0.10


@dataclass(frozen=True)
class Probe:
    width: int
    height: int
    nominal_fps: float
    pts_s: list[float]
    tagged_capture_fps: float | None

    @property
    def frame_count(self) -> int:
        return len(self.pts_s)

    @property
    def measured_fps(self) -> float:
        return 1.0 / float(np.median(np.diff(self.pts_s)))

    @property
    def is_vfr(self) -> bool:
        d = np.diff(self.pts_s)
        med = float(np.median(d))
        # One timebase tick of rounding is normal for CFR; ignore it.
        spread = (float(np.percentile(d, 95)) - float(np.percentile(d, 5))) / med
        return spread > VFR_SPREAD_THRESHOLD


class ProbeError(ValueError):
    pass


def _parse_rate(rate: str) -> float:
    num, _, den = rate.partition("/")
    return float(num) / float(den or 1) if float(den or 1) else 0.0


def probe(path: Path) -> Probe:
    try:
        raw = ffmpeg.run(
            "ffprobe",
            ["-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(path)],
        )
    except ffmpeg.FFmpegError as e:
        raise ProbeError(f"Could not read the video: {e}") from e
    info = json.loads(raw)
    stream = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), None)
    if stream is None:
        raise ProbeError("The file has no video stream.")

    tb = Fraction(stream.get("time_base", "1/1"))
    packets = ffmpeg.run(
        "ffprobe",
        [
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "packet=pts",
            "-of",
            "csv=p=0",
            str(path),
        ],
    )
    ticks = sorted(int(x) for x in packets.decode().split() if x.lstrip("-").isdigit())
    if len(ticks) < 2:
        raise ProbeError("The video has fewer than two frames with timestamps.")
    pts = [float((t - ticks[0]) * tb) for t in ticks]

    tags: dict[str, str] = {**info.get("format", {}).get("tags", {}), **stream.get("tags", {})}
    tagged = next((float(tags[k]) for k in CAPTURE_FPS_TAGS if k in tags), None)

    return Probe(
        width=int(stream["width"]),
        height=int(stream["height"]),
        nominal_fps=_parse_rate(stream.get("r_frame_rate", "0/1")),
        pts_s=pts,
        tagged_capture_fps=tagged,
    )


def extract_frames(path: Path, out_dir: Path) -> int:
    """Write every decoded frame as frames/000000.jpg onwards, one per pts, no resampling."""
    out_dir.mkdir(parents=True, exist_ok=True)
    ffmpeg.run(
        "ffmpeg",
        [
            "-v",
            "error",
            "-i",
            str(path),
            "-fps_mode",
            "passthrough",
            "-q:v",
            "3",
            "-start_number",
            "0",
            str(out_dir / "%06d.jpg"),
        ],
    )
    return len(list(out_dir.glob("*.jpg")))


def capture_times(pts_s: list[float], measured_fps: float, capture_fps: float) -> list[float]:
    """Rescale playback timestamps to real capture time (slow-mo clips play slower than shot)."""
    scale = measured_fps / capture_fps
    return [t * scale for t in pts_s]
