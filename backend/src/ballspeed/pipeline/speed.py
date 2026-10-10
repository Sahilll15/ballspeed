"""Speed from marked frames, clicked ball positions, or a fitted track."""

import math

import numpy as np

from ballspeed.models import Calibration, ManualSpeedRequest, SpeedResult, TrackPoint
from ballspeed.pipeline import calibration as calib
from ballspeed.pipeline.pitch import MS_TO_KMH

FRAME_COUNT_WARNING = (
    "Frame-count mode averages the whole flight, including the slowdown after the bounce. "
    "A radar gun reads release speed, typically 10 to 15% higher."
)


def _frame_interval(times: list[float], i: int) -> float:
    lo, hi = max(i - 2, 0), min(i + 2, len(times) - 1)
    return (times[hi] - times[lo]) / (hi - lo)


def _timing_sigma(times: list[float], start: int, end: int) -> float:
    # Each marked frame can be off by one frame; the two ends are independent.
    return math.hypot(_frame_interval(times, start), _frame_interval(times, end))


def manual(
    req: ManualSpeedRequest, times: list[float], cal: Calibration | None, fps: float
) -> SpeedResult:
    dt = times[req.end_frame] - times[req.release_frame]
    sigma_t = _timing_sigma(times, req.release_frame, req.end_frame)
    warnings: list[str] = []

    if req.mode == "frame_count":
        distance, sigma_d = req.distance_m, 0.0
        warnings.append(FRAME_COUNT_WARNING)
        track: list[TrackPoint] = []
    else:
        assert req.release_ball is not None and req.end_ball is not None
        if cal is None:
            raise calib.CalibrationError("Calibrate the pitch before using two-point mode.")
        px = np.array(
            [[req.release_ball.x, req.release_ball.y], [req.end_ball.x, req.end_ball.y]],
            dtype=np.float64,
        )
        world = calib.project(cal.homography, px)
        distance = float(np.linalg.norm(world[1] - world[0]))
        per_point = [cal.reprojection_error_px * calib.metres_per_px(cal.homography, p) for p in px]
        sigma_d = math.hypot(*per_point)
        if cal.mode == "ground_plane":
            warnings.append(
                "Ground-plane calibration treats the airborne ball as if it were "
                "on the pitch. Side-on vertical-plane calibration is more accurate."
            )
        track = [
            TrackPoint(
                frame=f,
                t_s=times[f],
                x_px=float(p[0]),
                y_px=float(p[1]),
                x_m=float(w[0]),
                z_m=float(w[1]),
                source="manual",
            )
            for f, p, w in zip((req.release_frame, req.end_frame), px, world, strict=True)
        ]

    if dt <= 0:
        raise ValueError("The end frame must come after the release frame in time.")
    v = distance / dt
    rel = math.hypot(sigma_d / distance if distance else 0.0, sigma_t / dt)
    return SpeedResult(
        release_speed_kmh=None,
        avg_speed_kmh=v * MS_TO_KMH,
        error_estimate_kmh=v * rel * MS_TO_KMH,
        method=req.mode,
        fps=fps,
        release_frame=req.release_frame,
        end_frame=req.end_frame,
        track=track,
        warnings=warnings,
    )
