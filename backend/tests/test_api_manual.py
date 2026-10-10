import math

from fastapi.testclient import TestClient

from ballspeed.pipeline.pitch import FRAME_COUNT_DISTANCE_M
from ballspeed.synth import SyntheticClip, Variant
from tests.conftest import upload


def calibrate(client: TestClient, vid: object, clip: SyntheticClip) -> None:
    points = [
        {
            "label": c.label,
            "image": {"x": c.image[0], "y": c.image[1]},
            "world": {"x": c.world[0], "y": c.world[1]},
        }
        for c in clip.calibration
    ]
    r = client.put(f"/api/videos/{vid}/calibration", json={"points": points})
    assert r.status_code == 200, r.text


def last_pre_bounce(clip: SyntheticClip) -> int:
    return max(f.index for f in clip.frames if f.t_s < clip.bounce_t_s)


def test_frame_count_mode(client: TestClient, clips: dict[Variant, SyntheticClip]) -> None:
    clip = clips["cfr"]
    vid = upload(client, clip)["id"]
    r = client.post(
        f"/api/videos/{vid}/speed/manual",
        json={"mode": "frame_count", "release_frame": 25, "end_frame": 160},
    )
    body = r.json()
    dt = clip.frames[160].t_s - clip.frames[25].t_s
    assert math.isclose(body["avg_speed_kmh"], FRAME_COUNT_DISTANCE_M / dt * 3.6, rel_tol=1e-3)
    assert 0 < body["error_estimate_kmh"] < 2.0
    assert any("radar" in w for w in body["warnings"])


def test_two_point_mode_matches_truth(
    client: TestClient, clips: dict[Variant, SyntheticClip]
) -> None:
    for variant in ("cfr", "slowmo", "warped", "vfr"):
        clip = clips[variant]
        vid = upload(client, clip)["id"]
        calibrate(client, vid, clip)
        a, b = clip.frames[clip.release_frame], clip.frames[last_pre_bounce(clip)]
        r = client.post(
            f"/api/videos/{vid}/speed/manual",
            json={
                "mode": "two_point",
                "release_frame": a.index,
                "end_frame": b.index,
                "release_ball": {"x": a.u_px, "y": a.v_px},
                "end_ball": {"x": b.u_px, "y": b.v_px},
            },
        )
        assert r.status_code == 200, r.text
        truth = math.hypot(b.x_m - a.x_m, b.z_m - a.z_m) / (b.t_s - a.t_s) * 3.6
        assert math.isclose(r.json()["avg_speed_kmh"], truth, rel_tol=0.005), variant


def test_two_point_requires_calibration(
    client: TestClient, clips: dict[Variant, SyntheticClip]
) -> None:
    vid = upload(client, clips["cfr"])["id"]
    r = client.post(
        f"/api/videos/{vid}/speed/manual",
        json={
            "mode": "two_point",
            "release_frame": 25,
            "end_frame": 100,
            "release_ball": {"x": 1, "y": 1},
            "end_ball": {"x": 2, "y": 2},
        },
    )
    assert r.json()["code"] == "CALIBRATION_MISSING"


def test_validation_errors_use_api_shape(
    client: TestClient, clips: dict[Variant, SyntheticClip]
) -> None:
    vid = upload(client, clips["cfr"])["id"]
    r = client.post(
        f"/api/videos/{vid}/speed/manual",
        json={"mode": "frame_count", "release_frame": 50, "end_frame": 20},
    )
    assert r.status_code == 422 and r.json()["code"] == "INVALID_INPUT"
