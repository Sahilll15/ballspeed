from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ballspeed.config import Settings
from ballspeed.main import create_app
from ballspeed.synth import SyntheticClip, Variant, generate, variant_spec


@pytest.fixture(scope="session")
def clips(tmp_path_factory: pytest.TempPathFactory) -> dict[Variant, SyntheticClip]:
    d = tmp_path_factory.mktemp("synth")
    variants: list[Variant] = ["cfr", "vfr", "slowmo", "warped"]
    return {v: generate(d / f"{v}.mp4", variant_spec(v)) for v in variants}


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    app = create_app(Settings(data_dir=tmp_path / "data"))
    with TestClient(app) as c:
        yield c


def upload(client: TestClient, clip: SyntheticClip) -> dict[str, object]:
    with clip.path.open("rb") as f:
        r = client.post("/api/videos", files={"file": (clip.path.name, f, "video/mp4")})
    assert r.status_code == 201, r.text
    body: dict[str, object] = r.json()
    return body
