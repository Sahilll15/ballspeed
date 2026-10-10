from enum import StrEnum

from fastapi import Request
from fastapi.responses import JSONResponse


class ErrorCode(StrEnum):
    UNSUPPORTED_FORMAT = "UNSUPPORTED_FORMAT"
    VIDEO_TOO_LARGE = "VIDEO_TOO_LARGE"
    VIDEO_NOT_FOUND = "VIDEO_NOT_FOUND"
    JOB_NOT_FOUND = "JOB_NOT_FOUND"
    FRAME_OUT_OF_RANGE = "FRAME_OUT_OF_RANGE"
    FPS_TOO_LOW = "FPS_TOO_LOW"
    SLOWMO_TIMEBASE_SUSPECT = "SLOWMO_TIMEBASE_SUSPECT"
    CALIBRATION_MISSING = "CALIBRATION_MISSING"
    CALIBRATION_DEGENERATE = "CALIBRATION_DEGENERATE"
    BALL_NOT_FOUND = "BALL_NOT_FOUND"
    INVALID_INPUT = "INVALID_INPUT"


class ApiError(Exception):
    def __init__(self, code: ErrorCode, message: str, hint: str = "", status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint
        self.status = status

    def payload(self) -> dict[str, str]:
        return {"code": self.code.value, "message": self.message, "hint": self.hint}


async def api_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ApiError)
    return JSONResponse(status_code=exc.status, content=exc.payload())
