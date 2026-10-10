import numpy as np
import pytest

from ballspeed.models import CalibrationPoint, CalibrationRequest, Point2D
from ballspeed.pipeline import calibration as calib
from ballspeed.synth import SyntheticClip, Variant


def request_for(clip: SyntheticClip) -> CalibrationRequest:
    return CalibrationRequest(
        mode="vertical_plane",
        points=[
            CalibrationPoint(
                label=c.label,
                image=Point2D(x=c.image[0], y=c.image[1]),
                world=Point2D(x=c.world[0], y=c.world[1]),
            )
            for c in clip.calibration
        ],
    )


@pytest.mark.parametrize("variant", ["cfr", "warped"])
def test_recovers_ball_world_positions(
    clips: dict[Variant, SyntheticClip], variant: Variant
) -> None:
    clip = clips[variant]
    cal = calib.compute(request_for(clip))
    assert cal.reprojection_error_px < 1e-3
    px = np.array([[f.u_px, f.v_px] for f in clip.frames])
    world = np.array([[f.x_m, f.z_m] for f in clip.frames])
    assert np.max(np.abs(calib.project(cal.homography, px) - world)) < 0.01


def test_rejects_collinear_points() -> None:
    pts = [
        CalibrationPoint(
            label=str(i),
            image=Point2D(x=10 * i, y=5 * i),
            world=Point2D(x=float(i), y=float(i % 2)),
        )
        for i in range(4)
    ]
    with pytest.raises(calib.CalibrationError, match="line"):
        calib.compute(CalibrationRequest(points=pts))
