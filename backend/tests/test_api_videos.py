from pathlib import Path

import numpy as np
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


def test_rejects_playlist_disguised_as_mp4(client: TestClient, tmp_path: object) -> None:
    secret = "/etc/hosts"
    playlist = f"#EXTM3U\n#EXT-X-TARGETDURATION:1\n#EXTINF:1,\nfile://{secret}\n#EXT-X-ENDLIST\n"
    r = client.post("/api/videos", files={"file": ("x.mp4", playlist.encode(), "video/mp4")})
    assert r.status_code == 415
    concat = f"ffconcat version 1.0\nfile '{secret}'\n"
    r = client.post("/api/videos", files={"file": ("y.mov", concat.encode(), "video/mp4")})
    assert r.status_code == 415


def test_extracts_only_the_probed_stream(client: TestClient, tmp_path: Path) -> None:
    from ballspeed import ffmpeg

    small, big, both = tmp_path / "s.mp4", tmp_path / "b.mp4", tmp_path / "both.mp4"
    for out, size in ((small, "160x120"), (big, "640x480")):
        ffmpeg.run(
            "ffmpeg",
            [
                "-v",
                "error",
                "-f",
                "lavfi",
                "-i",
                f"testsrc=s={size}:r=60:d=0.5",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                str(out),
            ],
        )
    ffmpeg.run(
        "ffmpeg",
        [
            "-v",
            "error",
            "-i",
            str(small),
            "-i",
            str(big),
            "-map",
            "0:v",
            "-map",
            "1:v",
            "-c",
            "copy",
            str(both),
        ],
    )
    with both.open("rb") as f:
        r = client.post("/api/videos", files={"file": ("both.mp4", f, "video/mp4")})
    assert r.status_code == 201, r.text
    assert (r.json()["width"], r.json()["height"]) == (160, 120)
    import cv2

    vid = r.json()["id"]
    img = client.get(f"/api/videos/{vid}/frames/0.jpg").content
    frame = cv2.imdecode(np.frombuffer(img, np.uint8), cv2.IMREAD_COLOR)
    assert frame.shape[:2] == (120, 160)


def test_calibration_point_limit(client: TestClient, clips: dict[Variant, SyntheticClip]) -> None:
    vid = upload(client, clips["cfr"])["id"]
    pts = [
        {"label": str(i), "image": {"x": i, "y": i * i}, "world": {"x": i, "y": 1}}
        for i in range(500)
    ]
    r = client.put(f"/api/videos/{vid}/calibration", json={"points": pts})
    assert r.status_code == 422 and r.json()["code"] == "INVALID_INPUT"
