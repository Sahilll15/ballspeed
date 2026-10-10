"""Temp-dir storage for uploads and an in-memory registry of videos and jobs. No database."""

import shutil
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from ballspeed.errors import ApiError, ErrorCode
from ballspeed.models import Calibration, CaptureFpsSource, FrameRange, JobStatus, VideoMeta
from ballspeed.pipeline.ingest import Probe, capture_times


@dataclass
class VideoRecord:
    id: str
    dir: Path
    filename: str
    probe: Probe
    capture_fps: float
    capture_fps_source: CaptureFpsSource
    trim: FrameRange | None = None
    calibration: Calibration | None = None
    warnings: list[str] = field(default_factory=list)
    last_access: float = field(default_factory=time.monotonic)

    @property
    def source(self) -> Path:
        return next(self.dir.glob("source.*"))

    @property
    def frames_dir(self) -> Path:
        return self.dir / "frames"

    @property
    def times_s(self) -> list[float]:
        return capture_times(self.probe.pts_s, self.probe.measured_fps, self.capture_fps)

    def meta(self) -> VideoMeta:
        p = self.probe
        return VideoMeta(
            id=self.id,
            filename=self.filename,
            width=p.width,
            height=p.height,
            frame_count=p.frame_count,
            duration_s=self.times_s[-1],
            nominal_fps=p.nominal_fps,
            measured_fps=p.measured_fps,
            capture_fps=self.capture_fps,
            capture_fps_source=self.capture_fps_source,
            is_vfr=p.is_vfr,
            slowmo_detected=self.capture_fps > p.measured_fps * 1.5,
            trim=self.trim,
            calibrated=self.calibration is not None,
            warnings=self.warnings,
        )


class Store:
    def __init__(self, root: Path | None, ttl_s: float) -> None:
        self.root = root or Path(tempfile.mkdtemp(prefix="ballspeed-"))
        self.root.mkdir(parents=True, exist_ok=True)
        self.ttl_s = ttl_s
        self.videos: dict[str, VideoRecord] = {}
        self.jobs: dict[str, JobStatus] = {}
        self._lock = threading.Lock()

    def new_dir(self) -> tuple[str, Path]:
        vid = uuid.uuid4().hex[:12]
        d = self.root / vid
        d.mkdir()
        return vid, d

    def add(self, rec: VideoRecord) -> None:
        with self._lock:
            self.videos[rec.id] = rec

    def get(self, vid: str) -> VideoRecord:
        with self._lock:
            rec = self.videos.get(vid)
        if rec is None:
            raise ApiError(
                ErrorCode.VIDEO_NOT_FOUND,
                f"No video with id {vid}.",
                "It may have expired. Upload it again.",
                status=404,
            )
        rec.last_access = time.monotonic()
        return rec

    def delete(self, vid: str) -> None:
        with self._lock:
            rec = self.videos.pop(vid, None)
            for jid in [j for j, s in self.jobs.items() if s.video_id == vid]:
                del self.jobs[jid]
        if rec is not None:
            shutil.rmtree(rec.dir, ignore_errors=True)

    def put_job(self, job: JobStatus) -> None:
        with self._lock:
            self.jobs[job.id] = job

    def get_job(self, jid: str) -> JobStatus:
        with self._lock:
            job = self.jobs.get(jid)
        if job is None:
            raise ApiError(ErrorCode.JOB_NOT_FOUND, f"No job with id {jid}.", status=404)
        return job

    def sweep(self) -> int:
        now = time.monotonic()
        with self._lock:
            stale = [v for v, r in self.videos.items() if now - r.last_access > self.ttl_s]
        for vid in stale:
            self.delete(vid)
        return len(stale)

    def close(self) -> None:
        for vid in list(self.videos):
            self.delete(vid)
        shutil.rmtree(self.root, ignore_errors=True)
