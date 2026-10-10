"""Multi-candidate Kalman tracking (constant acceleration, image space). The longest track wins."""

from dataclasses import dataclass, field

import numpy as np
from filterpy.common import Q_discrete_white_noise
from filterpy.kalman import KalmanFilter
from numpy.typing import NDArray
from scipy.linalg import block_diag

from ballspeed.pipeline.detection import Detection

GATE_CHI2 = 13.8  # 99.9% for 2 degrees of freedom
MAX_MISSES = 6
MIN_HITS = 5


@dataclass(frozen=True)
class TrackerConfig:
    meas_sigma_px: float = 1.5
    jerk_var: float = 1e8
    init_vel_sigma: float = 4000.0
    init_acc_sigma: float = 3000.0
    max_jump_px: float = 160.0


@dataclass(frozen=True)
class Sample:
    frame: int
    t_s: float
    est: tuple[float, float]
    meas: tuple[float, float] | None
    confidence: float


@dataclass
class _Track:
    kf: KalmanFilter
    last_t: float
    last_meas_frame: int
    samples: list[Sample] = field(default_factory=list)
    hits: int = 1
    misses: int = 0

    @property
    def displacement(self) -> float:
        pts = [s.meas for s in self.samples if s.meas is not None]
        return float(np.hypot(pts[-1][0] - pts[0][0], pts[-1][1] - pts[0][1])) if pts else 0.0


def _transition(dt: float) -> NDArray[np.float64]:
    f1 = np.array([[1, dt, dt * dt / 2], [0, 1, dt], [0, 0, 1]], dtype=np.float64)
    out: NDArray[np.float64] = block_diag(f1, f1)
    return out


class Tracker:
    def __init__(self, config: TrackerConfig | None = None) -> None:
        self.cfg = config or TrackerConfig()
        self.active: list[_Track] = []
        self.finished: list[_Track] = []

    def _new_track(self, d: Detection, frame: int, t: float) -> _Track:
        c = self.cfg
        kf = KalmanFilter(dim_x=6, dim_z=2)
        kf.x = np.array([d.x, 0.0, 0.0, d.y, 0.0, 0.0])
        kf.P = np.diag([c.meas_sigma_px**2, c.init_vel_sigma**2, c.init_acc_sigma**2] * 2)
        kf.H = np.array([[1, 0, 0, 0, 0, 0], [0, 0, 0, 1, 0, 0]], dtype=np.float64)
        kf.R = np.eye(2) * c.meas_sigma_px**2
        tr = _Track(kf=kf, last_t=t, last_meas_frame=frame)
        tr.samples.append(Sample(frame, t, (d.x, d.y), (d.x, d.y), d.score))
        return tr

    def _predict(self, tr: _Track, t: float) -> None:
        dt = t - tr.last_t
        tr.kf.F = _transition(dt)
        q = Q_discrete_white_noise(dim=3, dt=dt, var=self.cfg.jerk_var)
        tr.kf.Q = block_diag(q, q)
        tr.kf.predict()
        tr.last_t = t

    def _gate(self, tr: _Track, d: Detection, frame: int) -> float | None:
        kf = tr.kf
        y = np.array([d.x, d.y]) - kf.H @ kf.x
        s = kf.H @ kf.P @ kf.H.T + kf.R
        d2 = float(y @ np.linalg.solve(s, y))
        gap = frame - tr.last_meas_frame
        if d2 > GATE_CHI2 or float(np.hypot(*y)) > self.cfg.max_jump_px * gap:
            return None
        return d2

    def step(self, frame: int, t: float, detections: list[Detection]) -> None:
        for tr in self.active:
            self._predict(tr, t)
        pairs = sorted(
            (d2, ti, di)
            for ti, tr in enumerate(self.active)
            for di, det in enumerate(detections)
            if (d2 := self._gate(tr, det, frame)) is not None
        )
        used_t: set[int] = set()
        used_d: set[int] = set()
        for _, ti, di in pairs:
            if ti in used_t or di in used_d:
                continue
            used_t.add(ti)
            used_d.add(di)
            tr, det = self.active[ti], detections[di]
            tr.kf.update(np.array([det.x, det.y]))
            tr.hits += 1
            tr.misses = 0
            tr.last_meas_frame = frame
            est = (float(tr.kf.x[0]), float(tr.kf.x[3]))
            tr.samples.append(Sample(frame, t, est, (det.x, det.y), det.score))
        still: list[_Track] = []
        for ti, tr in enumerate(self.active):
            if ti not in used_t:
                tr.misses += 1
                if tr.misses > MAX_MISSES:
                    self.finished.append(tr)
                    continue
                est = (float(tr.kf.x[0]), float(tr.kf.x[3]))
                tr.samples.append(Sample(frame, t, est, None, 0.0))
            still.append(tr)
        for di, det in enumerate(detections):
            if di not in used_d:
                still.append(self._new_track(det, frame, t))
        self.active = still

    def best(self) -> list[Sample]:
        """The ball track: most measurements, then furthest travelled. Trailing misses dropped."""
        tracks = [t for t in [*self.finished, *self.active] if t.hits >= MIN_HITS]
        if not tracks:
            return []
        tr = max(tracks, key=lambda t: (t.hits, t.displacement))
        last = max(i for i, s in enumerate(tr.samples) if s.meas is not None)
        return tr.samples[: last + 1]
