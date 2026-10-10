"""API request and response models. Mirrored by frontend/src/api/types.ts."""

from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

from ballspeed.pipeline import pitch


class Point2D(BaseModel):
    x: float
    y: float


class Rect(BaseModel):
    x: float
    y: float
    width: float = Field(gt=0)
    height: float = Field(gt=0)


class FrameRange(BaseModel):
    start: int = Field(ge=0)
    end: int = Field(ge=0)

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if self.end <= self.start:
            raise ValueError("end must be after start")
        return self


CaptureFpsSource = Literal["container", "metadata", "user"]


class VideoMeta(BaseModel):
    id: str
    filename: str
    width: int
    height: int
    frame_count: int
    duration_s: float = Field(description="Real capture-time duration, after slow-mo rescaling.")
    nominal_fps: float
    measured_fps: float
    capture_fps: float
    capture_fps_source: CaptureFpsSource
    is_vfr: bool
    slowmo_detected: bool
    trim: FrameRange | None = None
    calibrated: bool = False
    warnings: list[str] = []


class VideoPatch(BaseModel):
    capture_fps: float | None = Field(default=None, gt=0, le=2000)
    trim: FrameRange | None = None


class Timestamps(BaseModel):
    video_id: str
    t_s: list[float]


CalibrationMode = Literal["vertical_plane", "ground_plane"]
MAX_CALIBRATION_POINTS = 12


class CalibrationPoint(BaseModel):
    label: str
    image: Point2D
    world: Point2D = Field(
        description="Metres. vertical_plane: x along pitch, y up. ground_plane: x along, y across."
    )


class CalibrationRequest(BaseModel):
    mode: CalibrationMode = "vertical_plane"
    points: list[CalibrationPoint] = Field(min_length=4, max_length=MAX_CALIBRATION_POINTS)


class Calibration(CalibrationRequest):
    homography: list[list[float]]
    reprojection_error_px: float


class ManualSpeedRequest(BaseModel):
    mode: Literal["frame_count", "two_point"]
    release_frame: int = Field(ge=0)
    end_frame: int = Field(ge=0)
    distance_m: float = Field(default=pitch.FRAME_COUNT_DISTANCE_M, gt=0)
    release_ball: Point2D | None = None
    end_ball: Point2D | None = None

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.end_frame <= self.release_frame:
            raise ValueError("end_frame must be after release_frame")
        if self.mode == "two_point" and (self.release_ball is None or self.end_ball is None):
            raise ValueError("two_point mode needs release_ball and end_ball pixel positions")
        return self


class AnalyzeRequest(BaseModel):
    roi: Rect | None = None
    release_frame_override: int | None = Field(default=None, ge=0)
    detector: Literal["classical", "yolo"] | None = None


class TrackPoint(BaseModel):
    frame: int
    t_s: float
    x_px: float
    y_px: float
    x_m: float | None = None
    z_m: float | None = None
    source: Literal["detected", "predicted", "manual"]
    confidence: float = 1.0


SpeedMethod = Literal["frame_count", "two_point", "track_fit"]


class SpeedResult(BaseModel):
    release_speed_kmh: float | None
    avg_speed_kmh: float
    error_estimate_kmh: float
    method: SpeedMethod
    fps: float
    release_frame: int
    bounce_frame: int | None = None
    end_frame: int
    track: list[TrackPoint] = []
    warnings: list[str] = []


class ApiErrorBody(BaseModel):
    code: str
    message: str
    hint: str = ""


JobState = Literal["queued", "running", "done", "failed"]


class JobStatus(BaseModel):
    id: str
    video_id: str
    state: JobState
    progress: float = 0.0
    stage: str = ""
    result: SpeedResult | None = None
    error: ApiErrorBody | None = None
