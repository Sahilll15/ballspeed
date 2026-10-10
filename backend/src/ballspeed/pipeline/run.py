"""Automatic pipeline: detect, track, find release and bounce, fit speed."""

import math
from collections.abc import Callable

import cv2
import numpy as np

from ballspeed.config import settings
from ballspeed.errors import ApiError, ErrorCode
from ballspeed.models import AnalyzeRequest, Calibration, SpeedResult, TrackPoint
from ballspeed.pipeline import calibration as calib
from ballspeed.pipeline import release, speed
from ballspeed.pipeline.detection import make_detector
from ballspeed.pipeline.detection.base import Image, Roi
from ballspeed.pipeline.pitch import MS_TO_KMH, STUMP_TO_STUMP_M
from ballspeed.pipeline.speed import FloatArray
from ballspeed.pipeline.tracking import Sample, Tracker
from ballspeed.storage import VideoRecord

Progress = Callable[[float, str], None]

ROI_WORLD = ((-1.5, -0.3), (STUMP_TO_STUMP_M + 1.5, 3.5))
POSE_WINDOW = 8
MIN_REL_ERROR = 0.002
RELEASE_LAG_FRAMES = 5


def roi_from_calibration(cal: Calibration, width: int, height: int) -> Roi | None:
    """Image box around the pitch plane up to 3.5 m high, so crowd and sky are ignored."""
    (x0, z0), (x1, z1) = ROI_WORLD
    corners = np.array([[x0, z0], [x1, z0], [x1, z1], [x0, z1]], dtype=np.float64)
    inv = np.linalg.inv(np.asarray(cal.homography, dtype=np.float64))
    px = calib.project(inv, corners)
    lo = np.clip(px.min(axis=0), 0, [width, height]).astype(int)
    hi = np.clip(px.max(axis=0), 0, [width, height]).astype(int)
    if hi[0] - lo[0] < 16 or hi[1] - lo[1] < 16:
        return None
    return Roi(int(lo[0]), int(lo[1]), int(hi[0] - lo[0]), int(hi[1] - lo[1]))


def _load(rec: VideoRecord, i: int) -> Image:
    img: Image | None = cv2.imread(str(rec.frames_dir / f"{i:06d}.jpg"))  # type: ignore[assignment]
    if img is None:
        raise ApiError(ErrorCode.FRAME_OUT_OF_RANGE, f"Frame {i} is missing on disk.", status=500)
    return img


def analyze(rec: VideoRecord, req: AnalyzeRequest, progress: Progress) -> SpeedResult:
    cal = rec.calibration
    if cal is None:
        raise ApiError(
            ErrorCode.CALIBRATION_MISSING,
            "Calibrate the pitch before analysing.",
            "Click the base and top of both sets of stumps.",
        )
    if rec.capture_fps < settings.min_fps_auto:
        raise ApiError(
            ErrorCode.FPS_TOO_LOW,
            f"{rec.capture_fps:.0f} fps is too low for automatic tracking.",
            "Use manual mode, or film at 240 fps slow motion.",
        )
    times = rec.times_s
    first, last = (rec.trim.start, rec.trim.end) if rec.trim else (0, rec.probe.frame_count - 1)
    roi = (
        Roi(int(req.roi.x), int(req.roi.y), int(req.roi.width), int(req.roi.height))
        if req.roi
        else roi_from_calibration(cal, rec.probe.width, rec.probe.height)
    )
    try:
        detector = make_detector(req.detector or settings.detector, settings.yolo_weights)
    except ValueError as e:
        raise ApiError(ErrorCode.INVALID_INPUT, str(e)) from e

    tracker = Tracker()
    n = last - first + 1
    for k, i in enumerate(range(first, last + 1)):
        tracker.step(i, times[i], detector.detect(_load(rec, i), roi))
        if k % 10 == 0:
            progress(0.8 * k / n, "Tracking the ball")

    samples = tracker.best()
    measured = [s for s in samples if s.meas is not None]
    if len(measured) < speed.MIN_FLIGHT_POINTS:
        raise ApiError(
            ErrorCode.BALL_NOT_FOUND,
            "Could not find the ball in flight.",
            "Film side-on with the whole pitch in frame, or use manual mode.",
            status=422,
        )
    progress(0.85, "Fitting the trajectory")
    t = np.array([s.t_s for s in measured])
    world = calib.project(cal.homography, np.array([s.meas for s in measured]))

    release_idx: int | None = None
    if req.release_frame_override is not None:
        release_idx = next(
            (k for k, s in enumerate(measured) if s.frame >= req.release_frame_override), None
        )
    try:
        fit = speed.fit_track(t, world, release_idx)
        refined = False
        if req.release_frame_override is None:
            fit, refined = _refine_release(rec, measured, t, world, fit, progress)
    except ValueError as e:
        raise ApiError(
            ErrorCode.BALL_NOT_FOUND,
            f"Ball track too short: {e}.",
            "Check the calibration and trim, or use manual mode.",
            status=422,
        ) from e

    fixed = req.release_frame_override is not None or refined
    return _result(rec, cal, samples, measured, world, fit, fixed)


def _refine_release(
    rec: VideoRecord,
    measured: list[Sample],
    t: FloatArray,
    world: FloatArray,
    fit: speed.TrackFit,
    progress: Progress,
) -> tuple[speed.TrackFit, bool]:
    finder = release.mediapipe_wrist_finder(lambda i: _load(rec, i))
    if finder is None:
        return fit, False
    progress(0.9, "Checking release against the bowler's wrist")
    s0 = measured[fit.release_idx]
    tau = t[fit.release_idx : fit.end_idx + 1] - t[fit.release_idx]
    meas = np.array([s.meas for s in measured[fit.release_idx : fit.end_idx + 1]])
    px_fit = [np.polyfit(tau, meas[:, k], 2) for k in range(2)]
    times = rec.times_s

    def ball_at(f: int) -> tuple[float, float]:
        dt = times[f] - s0.t_s
        return float(np.polyval(px_fit[0], dt)), float(np.polyval(px_fit[1], dt))

    lo = max(s0.frame - POSE_WINDOW, 0)
    frame = release.refine_with_pose(list(range(lo, s0.frame + 2)), ball_at, finder)
    if frame is None:
        return fit, False
    idx = next((k for k, s in enumerate(measured) if s.frame >= frame), fit.release_idx)
    return (speed.fit_track(t, world, idx) if idx != fit.release_idx else fit), True


def _result(
    rec: VideoRecord,
    cal: Calibration,
    samples: list[Sample],
    measured: list[Sample],
    world: FloatArray,
    fit: speed.TrackFit,
    release_fixed: bool,
) -> SpeedResult:
    seg = world[fit.release_idx : fit.end_idx + 1]
    length = float(np.sum(np.hypot(*np.diff(seg, axis=0).T)))
    mid = np.array(measured[(fit.release_idx + fit.end_idx) // 2].meas)
    rel_cal = cal.reprojection_error_px * calib.metres_per_px(cal.homography, mid)
    rel_cal = rel_cal * math.sqrt(2) / max(length, 1e-6)
    v = fit.release_speed_ms
    # The ball can stay hidden against the arm for a few frames, so release may be earlier
    # than the first sighting; the ball was faster then by decel * lag.
    lag = 1 if release_fixed else RELEASE_LAG_FRAMES
    frame_dt = 1 / rec.capture_fps
    err = math.hypot(
        2 * fit.sigma_ms, v * rel_cal, v * MIN_REL_ERROR, fit.decel_ms2 * lag * frame_dt
    )

    est = calib.project(cal.homography, np.array([s.est for s in samples]))
    track = [
        TrackPoint(
            frame=s.frame,
            t_s=s.t_s,
            x_px=s.est[0],
            y_px=s.est[1],
            x_m=float(w[0]),
            z_m=float(w[1]),
            source="detected" if s.meas is not None else "predicted",
            confidence=s.confidence,
        )
        for s, w in zip(samples, est, strict=True)
    ]
    warnings = list(rec.warnings)
    kmh = v * MS_TO_KMH
    if kmh < 40 and rec.probe.measured_fps <= 60 and rec.capture_fps_source != "user":
        warnings.append(
            f"{kmh:.0f} km/h is implausibly slow. If this is a slow-motion clip, "
            "set the capture fps (for example 240)."
        )
    if fit.bounce_idx is None:
        warnings.append("No bounce found; used every tracked point after release.")
    return SpeedResult(
        release_speed_kmh=kmh,
        avg_speed_kmh=fit.avg_speed_ms * MS_TO_KMH,
        error_estimate_kmh=err * MS_TO_KMH,
        method="track_fit",
        fps=rec.capture_fps,
        release_frame=measured[fit.release_idx].frame,
        bounce_frame=measured[fit.bounce_idx].frame if fit.bounce_idx is not None else None,
        end_frame=measured[fit.end_idx].frame,
        track=track,
        warnings=warnings,
    )
