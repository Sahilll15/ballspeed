"""Release frame: where the ball path starts fitting free flight, refined by MediaPipe if present.

Without pose the estimate runs a few frames late: the ball hides against the arm at first.
"""

from collections.abc import Callable

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]

MIN_SEED = 6
MIN_RESIDUAL_M = 0.04


def _quad_residual(t: FloatArray, xz: FloatArray, t_new: float, p_new: FloatArray) -> float:
    pred = [np.polyval(np.polyfit(t, xz[:, k], 2), t_new) for k in range(2)]
    return float(np.hypot(pred[0] - p_new[0], pred[1] - p_new[1]))


def ballistic_start(t: FloatArray, xz: FloatArray, end: int) -> int:
    """Walk back from the clean second half of the pre-bounce track until points stop fitting.

    Anything before release (ball in hand, swinging on the arm) breaks the quadratic model.
    """
    seed = max(MIN_SEED, end // 2)
    start = max(end - seed, 0)
    fit = (
        np.polyfit(t[start:end], xz[start:end, 0], 2),
        np.polyfit(t[start:end], xz[start:end, 1], 2),
    )
    rms = float(
        np.sqrt(
            np.mean(
                (np.polyval(fit[0], t[start:end]) - xz[start:end, 0]) ** 2
                + (np.polyval(fit[1], t[start:end]) - xz[start:end, 1]) ** 2
            )
        )
    )
    threshold = max(MIN_RESIDUAL_M, 4 * rms)
    while start > 0:
        r = _quad_residual(t[start:end], xz[start:end], float(t[start - 1]), xz[start - 1])
        if r > threshold:
            break
        start -= 1
    return start


def bounce_index(t: FloatArray, xz: FloatArray, rise_m: float = 0.05) -> int | None:
    """First sample after the lowest point of the arc, if the ball clearly rises again."""
    z = xz[:, 1]
    i = int(np.argmin(z))
    if i < len(z) - 2 and float(np.max(z[i + 1 :])) > z[i] + rise_m:
        # The true contact sits between i and the neighbour on the falling side.
        return i + 1 if z[i + 1] < z[i - 1] else i
    return None


WristFinder = Callable[[int], tuple[float, float] | None]


def refine_with_pose(
    frames: list[int], ball_px_at: Callable[[int], tuple[float, float]], wrist_at: WristFinder
) -> int | None:
    """Frame where the back-extrapolated ball path passes closest to the bowling wrist."""
    best: tuple[float, int] | None = None
    for f in frames:
        w = wrist_at(f)
        if w is None:
            continue
        bx, by = ball_px_at(f)
        d = float(np.hypot(bx - w[0], by - w[1]))
        if best is None or d < best[0]:
            best = (d, f)
    return best[1] if best else None


def mediapipe_wrist_finder(load_frame: Callable[[int], NDArray[np.uint8]]) -> WristFinder | None:
    """Wrist locator using MediaPipe Pose, or None when mediapipe is not installed."""
    try:
        import mediapipe as mp
    except ImportError:
        return None
    pose = mp.solutions.pose.Pose(static_image_mode=True, model_complexity=1)

    def find(frame: int) -> tuple[float, float] | None:
        img = load_frame(frame)
        res = pose.process(img[:, :, ::-1])
        if res.pose_landmarks is None:
            return None
        lm = res.pose_landmarks.landmark
        h, w = img.shape[:2]
        wrists = [
            lm[mp.solutions.pose.PoseLandmark.LEFT_WRIST],
            lm[mp.solutions.pose.PoseLandmark.RIGHT_WRIST],
        ]
        # The bowling hand is the higher wrist around release.
        top = min((p for p in wrists if p.visibility > 0.5), key=lambda p: p.y, default=None)
        return None if top is None else (top.x * w, top.y * h)

    return find
