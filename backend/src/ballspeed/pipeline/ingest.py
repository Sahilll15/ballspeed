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
MAX_FRAMES = 3000
MAX_DIMENSION_PX = 4096


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


def _ffprobe(path: Path, *args: str) -> bytes:
    return ffmpeg.run("ffprobe", ["-v", "error", *ffmpeg.SAFE_INPUT, *args, str(path)])


def probe(path: Path) -> Probe:
    try:
        info = json.loads(_ffprobe(path, "-print_format", "json", "-show_streams", "-show_format"))
        stream = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), None)
        if stream is None:
            raise ProbeError("The file has no video stream.")
        w, h = int(stream.get("width", 0)), int(stream.get("height", 0))
        if not (0 < w <= MAX_DIMENSION_PX and 0 < h <= MAX_DIMENSION_PX):
            raise ProbeError(f"Unsupported resolution {w}x{h} (max {MAX_DIMENSION_PX} px a side).")
        packets = _ffprobe(
            path, "-select_streams", "v:0", "-show_entries", "packet=pts", "-of", "csv=p=0"
        )
    except ffmpeg.FFmpegError as e:
        raise ProbeError(f"Could not read the video: {e}") from e

    ticks = sorted(int(x) for x in packets.decode().split() if x.lstrip("-").isdigit())
    if len(ticks) < 2:
        raise ProbeError("The video has fewer than two frames with timestamps.")
    if len(ticks) > MAX_FRAMES:
        raise ProbeError(
            f"The video has {len(ticks)} frames; the limit is {MAX_FRAMES}. "
            "Trim it to the delivery (a few seconds) before uploading."
        )
    tb = Fraction(stream.get("time_base", "1/1"))
    pts = [float((t - ticks[0]) * tb) for t in ticks]

    tags: dict[str, str] = {**info.get("format", {}).get("tags", {}), **stream.get("tags", {})}
    tagged = next((float(tags[k]) for k in CAPTURE_FPS_TAGS if k in tags), None)

    return Probe(
        width=w,
        height=h,
        nominal_fps=_parse_rate(stream.get("r_frame_rate", "0/1")),
        pts_s=pts,
        tagged_capture_fps=tagged,
    )


def extract_frames(path: Path, out_dir: Path) -> int:
    """Write every decoded frame as frames/000000.jpg onwards, one per pts, no resampling."""
    out_dir.mkdir(parents=True, exist_ok=True)
    args = [
        "-v",
        "error",
        *ffmpeg.SAFE_INPUT,
        "-i",
        str(path),
        # Same stream ffprobe validated; ffmpeg's default "best stream" pick could differ.
        "-map",
        "0:v:0",
        "-frames:v",
        str(MAX_FRAMES),
        "-fps_mode",
        "passthrough",
        "-q:v",
        "3",
        "-start_number",
        "0",
        str(out_dir / "%06d.jpg"),
    ]
    ffmpeg.run("ffmpeg", args)
    return len(list(out_dir.glob("*.jpg")))


def capture_times(pts_s: list[float], measured_fps: float, capture_fps: float) -> list[float]:
    """Rescale playback timestamps to real capture time (slow-mo clips play slower than shot)."""
    scale = measured_fps / capture_fps
    return [t * scale for t in pts_s]
