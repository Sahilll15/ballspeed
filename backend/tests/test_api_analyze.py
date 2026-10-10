import time

import pytest
from fastapi.testclient import TestClient

from ballspeed.synth import SyntheticClip, Variant
from tests.conftest import upload
from tests.test_api_manual import calibrate

TRUE_KMH = 140.0


def run_job(
    client: TestClient, vid: object, body: dict[str, object] | None = None
) -> dict[str, object]:
    r = client.post(f"/api/videos/{vid}/analyze", json=body or {})
    assert r.status_code == 202, r.text
    job_id = r.json()["id"]
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        job: dict[str, object] = client.get(f"/api/jobs/{job_id}").json()
        if job["state"] in ("done", "failed"):
            return job
        time.sleep(0.1)
    raise AssertionError("job timed out")


@pytest.mark.parametrize("variant", ["cfr", "vfr", "slowmo", "warped"])
def test_recovers_release_speed_within_2_percent(
    client: TestClient, clips: dict[Variant, SyntheticClip], variant: Variant
) -> None:
    clip = clips[variant]
    vid = upload(client, clip)["id"]
    calibrate(client, vid, clip)
    job = run_job(client, vid)
    assert job["state"] == "done", job["error"]
    res = job["result"]
    assert isinstance(res, dict)
    speed = float(res["release_speed_kmh"])
    assert abs(speed - TRUE_KMH) / TRUE_KMH < 0.02, f"{variant}: {speed:.2f} km/h"
    # The ball hides against the arm for a few frames after leaving the hand; never early.
    assert 0 <= res["release_frame"] - clip.release_frame <= 4
    bounce_truth = max(f.index for f in clip.frames if f.t_s < clip.bounce_t_s)
    assert res["bounce_frame"] is not None and abs(res["bounce_frame"] - bounce_truth) <= 2
    assert 0 < res["error_estimate_kmh"] < 3
    assert abs(speed - TRUE_KMH) <= res["error_estimate_kmh"] + 0.5


def test_analyze_needs_calibration(client: TestClient, clips: dict[Variant, SyntheticClip]) -> None:
    vid = upload(client, clips["cfr"])["id"]
    r = client.post(f"/api/videos/{vid}/analyze", json={})
    assert r.json()["code"] == "CALIBRATION_MISSING"


def test_low_fps_is_rejected(client: TestClient, clips: dict[Variant, SyntheticClip]) -> None:
    clip = clips["cfr"]
    vid = upload(client, clip)["id"]
    calibrate(client, vid, clip)
    client.patch(f"/api/videos/{vid}", json={"capture_fps": 30})
    job = run_job(client, vid)
    assert job["state"] == "failed"
    assert isinstance(job["error"], dict) and job["error"]["code"] == "FPS_TOO_LOW"


def test_release_override(client: TestClient, clips: dict[Variant, SyntheticClip]) -> None:
    clip = clips["cfr"]
    vid = upload(client, clip)["id"]
    calibrate(client, vid, clip)
    job = run_job(client, vid, {"release_frame_override": 40})
    res = job["result"]
    assert isinstance(res, dict) and res["release_frame"] >= 40
