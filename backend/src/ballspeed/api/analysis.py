from fastapi import APIRouter

from ballspeed.api.videos import StoreDep
from ballspeed.errors import ApiError, ErrorCode
from ballspeed.models import Calibration, CalibrationRequest, ManualSpeedRequest, SpeedResult
from ballspeed.pipeline import calibration as calib
from ballspeed.pipeline import speed

router = APIRouter(prefix="/api/videos/{video_id}", tags=["analysis"])


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
