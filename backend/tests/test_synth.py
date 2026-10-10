import math

import numpy as np

from ballspeed.pipeline import pitch
from ballspeed.synth import SyntheticClip, Variant


def test_ground_truth_is_physical(clips: dict[Variant, SyntheticClip]) -> None:
    clip = clips["cfr"]
    assert math.isclose(clip.release_speed_ms * 3.6, 140.0)
    assert math.isclose(clip.bounce_x_m, pitch.STUMP_TO_STUMP_M - 6.0, abs_tol=1e-6)
    flight = [f for f in clip.frames if f.released]
    xs = np.array([f.x_m for f in flight])
    assert np.all(np.diff(xs) > 0), "ball must travel down the pitch"
    first = flight[0]
    assert abs(first.x_m - pitch.POPPING_CREASE_OFFSET_M) < 0.2


def test_ball_drawn_where_truth_says(clips: dict[Variant, SyntheticClip]) -> None:
    import cv2

    clip = clips["cfr"]
    cap = cv2.VideoCapture(str(clip.path))
    for i in range(60):
        ok, frame = cap.read()
        assert ok
        if i in (35, 59):
            f = clip.frames[i]
            u, v = round(f.u_px), round(f.v_px)
            patch = frame[v - 1 : v + 2, u - 1 : u + 2].astype(int)
            assert patch.mean() > 200, f"no bright ball at frame {i}"
    cap.release()
