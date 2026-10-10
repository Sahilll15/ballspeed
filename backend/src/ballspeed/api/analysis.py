import logging
import uuid
from concurrent.futures import Executor

from fastapi import APIRouter, Request

from ballspeed.api.videos import StoreDep
from ballspeed.errors import ApiError, ErrorCode
from ballspeed.models import (
    AnalyzeRequest,
    ApiErrorBody,
    Calibration,
    CalibrationRequest,
    JobStatus,
    ManualSpeedRequest,
    SpeedResult,
)
from ballspeed.pipeline import calibration as calib
from ballspeed.pipeline import run, speed
from ballspeed.storage import Store, VideoRecord

router = APIRouter(prefix="/api/videos/{video_id}", tags=["analysis"])
jobs_router = APIRouter(prefix="/api/jobs", tags=["analysis"])
log = logging.getLogger(__name__)


@router.put("/calibration", response_model=Calibration)
def put_calibration(store: StoreDep, video_id: str, req: CalibrationRequest) -> Calibration:
    rec = store.get(video_id)
    try:
        rec.calibration = calib.compute(req)
    except calib.CalibrationError as e:
        raise ApiError(
            ErrorCode.CALIBRATION_DEGENERATE,
            str(e),
            "Click the base and top of both sets of stumps, spread across the frame.",
            status=422,
        ) from e
    return rec.calibration


@router.get("/calibration", response_model=Calibration)
def get_calibration(store: StoreDep, video_id: str) -> Calibration:
    rec = store.get(video_id)
    if rec.calibration is None:
        raise ApiError(
            ErrorCode.CALIBRATION_MISSING,
            "This video has not been calibrated.",
            "Click the four stump points on a frame first.",
            status=404,
        )
    return rec.calibration


@router.post("/speed/manual", response_model=SpeedResult)
def manual_speed(store: StoreDep, video_id: str, req: ManualSpeedRequest) -> SpeedResult:
    rec = store.get(video_id)
    last = rec.probe.frame_count - 1
    if req.end_frame > last:
        raise ApiError(
            ErrorCode.FRAME_OUT_OF_RANGE, f"Frame {req.end_frame} is past the last frame {last}."
        )
    if req.mode == "two_point" and rec.calibration is None:
        raise ApiError(
            ErrorCode.CALIBRATION_MISSING,
            "Two-point mode needs the pitch calibrated first.",
            "Click the base and top of both sets of stumps.",
        )
    result = speed.manual(req, rec.times_s, rec.calibration, rec.capture_fps)
    result.warnings = [*rec.warnings, *result.warnings]
    return result


def _run_job(store: Store, rec: VideoRecord, job_id: str, req: AnalyzeRequest) -> None:
    def update(**changes: object) -> None:
        store.put_job(store.get_job(job_id).model_copy(update=changes))

    def progress(fraction: float, stage: str) -> None:
        update(state="running", progress=round(fraction, 3), stage=stage)

    try:
        progress(0.0, "Starting")
        result = run.analyze(rec, req, progress)
        update(state="done", progress=1.0, stage="Done", result=result)
    except ApiError as e:
        update(state="failed", stage="Failed", error=ApiErrorBody(**e.payload()))
    except Exception as e:
        log.exception("analysis job %s failed", job_id)
        update(
            state="failed",
            stage="Failed",
            error=ApiErrorBody(code="INTERNAL", message=f"Analysis crashed: {e}"),
        )


@router.post("/analyze", response_model=JobStatus, status_code=202)
def start_analysis(
    request: Request, store: StoreDep, video_id: str, req: AnalyzeRequest
) -> JobStatus:
    rec = store.get(video_id)
    if rec.calibration is None:
        raise ApiError(
            ErrorCode.CALIBRATION_MISSING,
            "Calibrate the pitch before analysing.",
            "Click the base and top of both sets of stumps.",
        )
    job = JobStatus(id=uuid.uuid4().hex[:12], video_id=video_id, state="queued", stage="Queued")
    store.put_job(job)
    executor: Executor = request.app.state.executor
    executor.submit(_run_job, store, rec, job.id, req)
    return job


@jobs_router.get("/{job_id}", response_model=JobStatus)
def get_job(store: StoreDep, job_id: str) -> JobStatus:
    return store.get_job(job_id)
