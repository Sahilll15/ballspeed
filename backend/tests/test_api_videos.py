from fastapi.testclient import TestClient

from ballspeed.synth import SyntheticClip, Variant
from tests.conftest import upload


def test_upload_returns_meta_and_frames(
    client: TestClient, clips: dict[Variant, SyntheticClip]
) -> None:
    meta = upload(client, clips["cfr"])
    assert meta["frame_count"] == 180
    assert meta["capture_fps"] == pytest_approx(240.0)
    vid = meta["id"]
    r = client.get(f"/api/videos/{vid}/frames/0.jpg")
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
    assert client.get(f"/api/videos/{vid}/frames/180.jpg").json()["code"] == "FRAME_OUT_OF_RANGE"


def test_slowmo_metadata_sets_capture_fps(
    client: TestClient, clips: dict[Variant, SyntheticClip]
) -> None:
    meta = upload(client, clips["slowmo"])
    assert meta["capture_fps_source"] == "metadata"
    assert meta["slowmo_detected"] is True
    assert abs(float(str(meta["duration_s"])) - 179 / 240) < 1e-3


def test_user_capture_fps_override(client: TestClient, clips: dict[Variant, SyntheticClip]) -> None:
    vid = upload(client, clips["cfr"])["id"]
    meta = client.patch(f"/api/videos/{vid}", json={"capture_fps": 480}).json()
    assert meta["capture_fps_source"] == "user"
    ts = client.get(f"/api/videos/{vid}/timestamps").json()["t_s"]
    assert abs(ts[-1] - 179 / 480) < 1e-3


def test_rejects_non_video(client: TestClient) -> None:
    r = client.post("/api/videos", files={"file": ("notes.txt", b"hello", "text/plain")})
    assert r.status_code == 415
    assert r.json()["code"] == "UNSUPPORTED_FORMAT"
    r = client.post("/api/videos", files={"file": ("fake.mp4", b"not a video", "video/mp4")})
    assert r.status_code == 415


def test_unknown_video_404(client: TestClient) -> None:
    r = client.get("/api/videos/nope")
    assert r.status_code == 404 and r.json()["hint"]


def pytest_approx(v: float) -> object:
    import pytest

    return pytest.approx(v)
