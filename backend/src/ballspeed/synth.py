"""Synthetic side-on delivery videos with exact ground truth, used to validate every phase.

World frame is the vertical plane through both middle stumps: x along the pitch from the
bowler's stumps, z up from the ground.
"""

import argparse
import json
import math
import subprocess
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Literal

import cv2
import numpy as np
from numpy.typing import NDArray
from scipy.integrate import solve_ivp
from scipy.optimize import brentq

from ballspeed.ffmpeg import binary
from ballspeed.pipeline import pitch

Variant = Literal["cfr", "vfr", "slowmo", "warped"]
Image = NDArray[np.uint8]

GRAVITY = 9.81
ARM_LENGTH_M = 0.75


@dataclass(frozen=True)
class SceneSpec:
    width: int = 1280
    height: int = 720
    capture_fps: float = 240.0
    duration_s: float = 0.75
    px_per_m: float = 55.0
    origin_px: tuple[float, float] = (87.0, 600.0)
    release_speed_kmh: float = 140.0
    release_x_m: float = pitch.POPPING_CREASE_OFFSET_M
    release_z_m: float = 2.2
    good_length_m: float = 6.0
    drag_k: float = 0.0076
    restitution: float = 0.55
    bounce_friction: float = 0.88
    release_frame_offset: float = 24.37
    ball_radius_px: float = 3.0
    noise_sigma: float = 3.0
    jitter_s: float = 0.0
    encode_fps: float | None = None
    warp: tuple[tuple[float, ...], ...] | None = None
    seed: int = 7


@dataclass(frozen=True)
class FrameTruth:
    index: int
    t_s: float
    x_m: float
    z_m: float
    u_px: float
    v_px: float
    released: bool


@dataclass(frozen=True)
class CalibrationTruth:
    label: str
    image: tuple[float, float]
    world: tuple[float, float]


@dataclass(frozen=True)
class SyntheticClip:
    path: Path
    spec: SceneSpec
    release_t_s: float
    release_speed_ms: float
    release_frame: int
    bounce_t_s: float
    bounce_x_m: float
    frames: list[FrameTruth] = field(repr=False)
    calibration: list[CalibrationTruth] = field(repr=False)

    def write_json(self, path: Path) -> None:
        payload = asdict(self)
        payload["path"] = str(self.path)
        path.write_text(json.dumps(payload, indent=1))


class Flight:
    """Ball flight with quadratic air drag and a single lossy bounce."""

    def __init__(self, spec: SceneSpec, release_angle: float) -> None:
        self.spec = spec
        v0 = spec.release_speed_kmh / pitch.MS_TO_KMH
        r = pitch.BALL_DIAMETER_M / 2
        state0 = [
            spec.release_x_m,
            spec.release_z_m,
            v0 * math.cos(release_angle),
            -v0 * math.sin(release_angle),
        ]

        def hit_ground(_t: float, y: NDArray[np.float64]) -> float:
            return float(y[1] - r)

        setattr(hit_ground, "terminal", True)  # noqa: B010 (solve_ivp event protocol)
        setattr(hit_ground, "direction", -1)  # noqa: B010

        horizon = spec.duration_s + 1.0
        pre = solve_ivp(
            self._rhs,
            (0.0, horizon),
            state0,
            events=hit_ground,
            dense_output=True,
            rtol=1e-10,
            atol=1e-12,
        )
        if not pre.t_events[0].size:
            raise ValueError("ball never bounced; adjust the release angle or duration")
        self.bounce_t = float(pre.t_events[0][0])
        bx, bz, bvx, bvz = pre.sol(self.bounce_t)
        post_state = [bx, bz, bvx * spec.bounce_friction, -bvz * spec.restitution]
        post = solve_ivp(
            self._rhs,
            (self.bounce_t, horizon),
            post_state,
            dense_output=True,
            rtol=1e-10,
            atol=1e-12,
        )
        self._pre = pre.sol
        self._post = post.sol
        self.bounce_x = float(bx)

    def _rhs(self, _t: float, y: NDArray[np.float64]) -> list[float]:
        vx, vz = y[2], y[3]
        speed = math.hypot(vx, vz)
        k = self.spec.drag_k
        return [vx, vz, -k * speed * vx, -k * speed * vz - GRAVITY]

    def position(self, t: float) -> tuple[float, float]:
        sol = self._pre if t <= self.bounce_t else self._post
        x, z, _, _ = sol(t)
        return float(x), float(z)


def solve_release_angle(spec: SceneSpec) -> float:
    target = pitch.STUMP_TO_STUMP_M - spec.good_length_m
    root: float = brentq(lambda a: Flight(spec, a).bounce_x - target, 0.0, 0.35, xtol=1e-12)
    return root


def _frame_times(spec: SceneSpec) -> NDArray[np.float64]:
    n = round(spec.duration_s * spec.capture_fps)
    i = np.arange(n, dtype=np.float64)
    # Must match the setpts expression in _Encoder so pts equal capture times.
    return i / spec.capture_fps + spec.jitter_s * np.sin(1.3 * i)


def _canvas_px(spec: SceneSpec, x: float, z: float) -> tuple[float, float]:
    ox, oy = spec.origin_px
    return ox + spec.px_per_m * x, oy - spec.px_per_m * z


def _world_to_px(spec: SceneSpec, x: float, z: float) -> tuple[float, float]:
    u, v = _canvas_px(spec, x, z)
    if spec.warp is None:
        return u, v
    h = np.asarray(spec.warp, dtype=np.float64)
    p = h @ np.array([u, v, 1.0])
    return float(p[0] / p[2]), float(p[1] / p[2])


def _background(spec: SceneSpec) -> Image:
    rng = np.random.default_rng(spec.seed)
    h, w = spec.height, spec.width
    ground_v = int(spec.origin_px[1])
    img = np.zeros((h, w, 3), dtype=np.uint8)
    sky = np.linspace(200, 160, ground_v)[:, None]
    img[:ground_v] = np.stack([sky + 30, sky + 10, sky - 20], axis=-1).astype(np.uint8)
    img[ground_v : ground_v + 25] = (95, 150, 185)
    img[ground_v + 25 :] = (55, 125, 60)
    texture = rng.normal(0, 6, (h, w, 1))
    img = np.clip(img.astype(np.float64) + texture, 0, 255).astype(np.uint8)
    s = spec.px_per_m
    for x_m in (0.0, pitch.STUMP_TO_STUMP_M):
        u = round(spec.origin_px[0] + s * x_m)
        top = round(spec.origin_px[1] - s * pitch.STUMP_HEIGHT_M)
        cv2.rectangle(img, (u - 1, top), (u + 1, ground_v), (170, 210, 235), -1)
        cv2.line(img, (u - 4, top - 1), (u + 4, top - 1), (150, 190, 220), 1)
    for x_m in (pitch.POPPING_CREASE_OFFSET_M, pitch.FRAME_COUNT_DISTANCE_M):
        u = round(spec.origin_px[0] + s * x_m)
        cv2.line(img, (u, ground_v), (u, ground_v + 25), (250, 250, 250), 1)
    return img


def _sub(p: tuple[float, float]) -> tuple[int, int]:
    return round(p[0] * 16), round(p[1] * 16)


def _render(
    spec: SceneSpec,
    bg: Image,
    ball_canvas: tuple[float, float],
    shoulder: tuple[float, float],
    hand: tuple[float, float],
    rng: np.random.Generator,
) -> Image:
    s = spec.px_per_m
    img = bg.copy()
    sh_u, sh_v = _canvas_px(spec, *shoulder)
    body_w = 0.4 * s
    cv2.rectangle(
        img,
        (int(sh_u - body_w / 2), int(sh_v)),
        (int(sh_u + body_w / 2), int(spec.origin_px[1])),
        (90, 60, 40),
        -1,
    )
    cv2.circle(img, (int(sh_u), int(sh_v - 0.25 * s)), int(0.12 * s), (120, 150, 190), -1)
    cv2.line(
        img, _sub((sh_u, sh_v)), _sub(_canvas_px(spec, *hand)), (120, 150, 190), 4, cv2.LINE_AA, 4
    )
    cv2.circle(
        img,
        _sub(ball_canvas),
        round(spec.ball_radius_px * 16),
        (245, 245, 245),
        -1,
        cv2.LINE_AA,
        4,
    )
    if spec.warp is not None:
        h = np.asarray(spec.warp, dtype=np.float64)
        img = cv2.warpPerspective(  # type: ignore[assignment]
            img,
            h,
            (spec.width, spec.height),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REPLICATE,
        )
    noise = rng.normal(0, spec.noise_sigma, img.shape)
    return np.clip(img.astype(np.float64) + noise, 0, 255).astype(np.uint8)


class _Encoder:
    def __init__(self, spec: SceneSpec, out: Path) -> None:
        in_fps = spec.encode_fps or spec.capture_fps
        args = [
            binary("ffmpeg"),
            "-y",
            "-loglevel",
            "error",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "bgr24",
            "-s",
            f"{spec.width}x{spec.height}",
            "-framerate",
            f"{in_fps}",
            "-i",
            "-",
        ]
        if spec.jitter_s:
            expr = f"(N/{spec.capture_fps}+{spec.jitter_s}*sin(N*1.3))/TB"
            args += [
                "-vf",
                f"settb=1/240000,setpts='{expr}'",
                "-fps_mode",
                "passthrough",
                "-enc_time_base:v",
                "1/240000",
                "-video_track_timescale",
                "240000",
            ]
        movflags = "+faststart"
        if spec.encode_fps is not None:
            movflags += "+use_metadata_tags"
            args += ["-metadata", f"com.android.capture.fps={spec.capture_fps:.6f}"]
        args += [
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "14",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            movflags,
            str(out),
        ]
        self.proc = subprocess.Popen(args, stdin=subprocess.PIPE, stderr=subprocess.PIPE)

    def write(self, img: Image) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.write(img.tobytes())

    def close(self) -> None:
        _, err = self.proc.communicate()
        if self.proc.returncode != 0:
            raise RuntimeError(f"ffmpeg encode failed: {err.decode(errors='replace')[-400:]}")


def generate(out: Path, spec: SceneSpec | None = None) -> SyntheticClip:
    spec = spec or SceneSpec()
    angle = solve_release_angle(spec)
    flight = Flight(spec, angle)
    v0 = spec.release_speed_kmh / pitch.MS_TO_KMH
    omega = v0 / ARM_LENGTH_M
    times = _frame_times(spec)
    t_rel = float(spec.release_frame_offset / spec.capture_fps)
    rel_x, rel_z = spec.release_x_m, spec.release_z_m
    shoulder = (rel_x - ARM_LENGTH_M * math.sin(angle), rel_z - ARM_LENGTH_M * math.cos(angle))

    def hand_at(t: float) -> tuple[float, float]:
        psi = angle + omega * (t - t_rel)
        psi = max(min(psi, angle + 0.8 * math.pi), angle - 1.3 * math.pi)
        return shoulder[0] + ARM_LENGTH_M * math.sin(psi), shoulder[1] + ARM_LENGTH_M * math.cos(
            psi
        )

    bg = _background(spec)
    rng = np.random.default_rng(spec.seed + 1)
    enc = _Encoder(spec, out)
    truth: list[FrameTruth] = []
    try:
        for i, t in enumerate(times.tolist()):
            released = t >= t_rel
            x, z = flight.position(t - t_rel) if released else hand_at(t)
            u, v = _world_to_px(spec, x, z)
            truth.append(FrameTruth(i, float(t), x, z, u, v, released))
            enc.write(_render(spec, bg, _canvas_px(spec, x, z), shoulder, hand_at(t), rng))
    finally:
        enc.close()

    calib = [
        CalibrationTruth(label, _world_to_px(spec, x, z), (x, z))
        for label, x, z in (
            ("bowler_stump_base", 0.0, 0.0),
            ("bowler_stump_top", 0.0, pitch.STUMP_HEIGHT_M),
            ("batter_stump_base", pitch.STUMP_TO_STUMP_M, 0.0),
            ("batter_stump_top", pitch.STUMP_TO_STUMP_M, pitch.STUMP_HEIGHT_M),
        )
    ]
    release_frame = next(f.index for f in truth if f.released)
    return SyntheticClip(
        out, spec, t_rel, v0, release_frame, t_rel + flight.bounce_t, flight.bounce_x, truth, calib
    )


def default_warp(spec: SceneSpec) -> tuple[tuple[float, ...], ...]:
    w, h = spec.width, spec.height
    src = np.array([[0, 0], [w, 0], [w, h], [0, h]], dtype=np.float32)
    dst = np.array([[40, 30], [w - 10, 80], [w - 60, h - 20], [10, h - 5]], dtype=np.float32)
    m = cv2.getPerspectiveTransform(src, dst)
    return tuple(tuple(float(v) for v in row) for row in m)


def variant_spec(variant: Variant, base: SceneSpec | None = None) -> SceneSpec:
    base = base or SceneSpec()
    match variant:
        case "cfr":
            return base
        case "vfr":
            return replace(base, jitter_s=0.0015)
        case "slowmo":
            return replace(base, encode_fps=30.0)
        case "warped":
            return replace(base, warp=default_warp(base))


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a synthetic delivery video.")
    parser.add_argument("out", type=Path)
    parser.add_argument("--variant", choices=["cfr", "vfr", "slowmo", "warped"], default="cfr")
    parser.add_argument("--speed-kmh", type=float, default=140.0)
    args = parser.parse_args()
    spec = replace(variant_spec(args.variant), release_speed_kmh=args.speed_kmh)
    clip = generate(args.out, spec)
    clip.write_json(args.out.with_suffix(".truth.json"))
    print(
        f"{args.out}: release {clip.release_speed_ms * 3.6:.1f} km/h at frame "
        f"{clip.release_frame}, bounce x={clip.bounce_x_m:.2f} m"
    )


if __name__ == "__main__":
    main()
