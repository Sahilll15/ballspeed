"""Speed from marked frames, clicked ball positions, or a fitted track."""

import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy.optimize import least_squares

from ballspeed.models import Calibration, ManualSpeedRequest, SpeedResult, TrackPoint
from ballspeed.pipeline import calibration as calib
from ballspeed.pipeline import release
from ballspeed.pipeline.pitch import MS_TO_KMH

FloatArray = NDArray[np.float64]

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


MIN_FLIGHT_POINTS = 6


@dataclass(frozen=True)
class TrackFit:
    release_speed_ms: float
    avg_speed_ms: float
    sigma_ms: float
    decel_ms2: float
    release_idx: int
    bounce_idx: int | None
    end_idx: int


def _robust_quadratic(tau: FloatArray, y: FloatArray) -> tuple[FloatArray, FloatArray]:
    """Quadratic fit with soft-L1 loss; returns coefficients [c, b, a] and their covariance."""

    def resid(p: FloatArray) -> FloatArray:
        out: FloatArray = p[0] + p[1] * tau + p[2] * tau**2 - y
        return out

    init = np.polyfit(tau, y, 2)[::-1]
    res = least_squares(resid, init, loss="soft_l1", f_scale=0.02)
    j = res.jac
    dof = max(len(y) - 3, 1)
    s2 = float(np.sum(res.fun**2) / dof)
    cov: FloatArray = np.linalg.pinv(j.T @ j) * s2
    coef: FloatArray = res.x
    return coef, cov


def fit_track(t: FloatArray, xz: FloatArray, release_idx: int | None) -> TrackFit:
    """Fit position against time over pre-bounce flight; speed at release is the radar figure.

    x and z come from the vertical-plane homography, so they are true metres in the ball's plane.
    """
    bounce = release.bounce_index(t, xz)
    end = bounce if bounce is not None else len(t)
    start = release.ballistic_start(t, xz, end) if release_idx is None else release_idx
    if end - start < MIN_FLIGHT_POINTS:
        raise ValueError(f"only {end - start} ball positions between release and bounce")
    tau = t[start:end] - t[start]
    (_cx, bx, ax), cov_x = _robust_quadratic(tau, xz[start:end, 0])
    (_cz, bz, az), cov_z = _robust_quadratic(tau, xz[start:end, 1])
    v0 = math.hypot(bx, bz)
    # Speed variance from the release-velocity terms, d|v|/dbx = bx/|v|.
    sigma = math.sqrt((bx / v0) ** 2 * cov_x[1, 1] + (bz / v0) ** 2 * cov_z[1, 1])
    dense = np.linspace(0, tau[-1], 200)
    speeds = np.hypot(bx + 2 * ax * dense, bz + 2 * az * dense)
    decel = abs(2 * (bx * ax + bz * az) / v0)
    return TrackFit(v0, float(np.mean(speeds)), sigma, decel, start, bounce, end - 1)
