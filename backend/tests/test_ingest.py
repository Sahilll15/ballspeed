import numpy as np
import pytest

from ballspeed.pipeline.ingest import capture_times, probe
from ballspeed.synth import SyntheticClip, Variant


@pytest.mark.parametrize("variant", ["cfr", "vfr", "warped"])
def test_pts_match_capture_times(clips: dict[Variant, SyntheticClip], variant: Variant) -> None:
    clip = clips[variant]
    p = probe(clip.path)
    assert p.frame_count == len(clip.frames)
    truth = np.array([f.t_s for f in clip.frames])
    assert np.max(np.abs(np.array(p.pts_s) - truth)) < 1e-4
    assert p.is_vfr is (variant == "vfr")


def test_slowmo_is_detected_and_rescaled(clips: dict[Variant, SyntheticClip]) -> None:
    clip = clips["slowmo"]
    p = probe(clip.path)
    assert p.nominal_fps == pytest.approx(30.0)
    assert p.tagged_capture_fps == pytest.approx(240.0)
    times = capture_times(p.pts_s, p.measured_fps, p.tagged_capture_fps or 0)
    truth = np.array([f.t_s for f in clip.frames])
    assert np.max(np.abs(np.array(times) - truth)) < 1e-4
