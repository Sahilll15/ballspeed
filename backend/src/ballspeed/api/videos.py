import shutil
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import FileResponse

from ballspeed.config import settings
from ballspeed.errors import ApiError, ErrorCode
from ballspeed.models import CaptureFpsSource, Timestamps, VideoMeta, VideoPatch
from ballspeed.pipeline.ingest import ProbeError, extract_frames, probe
from ballspeed.storage import Store, VideoRecord

router = APIRouter(prefix="/api/videos", tags=["videos"])

ALLOWED_SUFFIXES = {".mp4", ".mov", ".m4v"}
CHUNK = 1 << 20


def get_store(request: Request) -> Store:
    store: Store = request.app.state.store
    return store


StoreDep = Annotated[Store, Depends(get_store)]


def _save_upload(upload: UploadFile, dest: Path) -> None:
    limit = settings.max_upload_mb * CHUNK
    written = 0
    with dest.open("wb") as f:
        while chunk := upload.file.read(CHUNK):
            written += len(chunk)
            if written > limit:
                raise ApiError(
                    ErrorCode.VIDEO_TOO_LARGE,
                    f"Upload is larger than {settings.max_upload_mb} MB.",
                    "Trim the clip to the delivery before uploading.",
                    status=413,
                )
            f.write(chunk)


def _fps_warnings(rec: VideoRecord) -> list[str]:
    out: list[str] = []
    if rec.probe.is_vfr:
        out.append("Variable frame rate detected. Timing uses per-frame timestamps.")
    if rec.capture_fps < settings.min_fps_auto:
        out.append(
            f"{rec.capture_fps:.0f} fps is too low for automatic tracking. Manual "
            "mode works, but expect a wide error range. Film at 240 fps if you can."
        )
    if rec.capture_fps_source == "metadata":
        out.append(
            f"Slow-motion clip: timing rescaled to the {rec.capture_fps:.0f} fps capture "
            "rate from metadata."
        )
    elif rec.probe.measured_fps <= 60:
        out.append(
            "If this was filmed in slow motion, set the capture fps, otherwise speeds "
            "will read far too low."
        )
    return out


@router.post("", response_model=VideoMeta, status_code=201)
def upload_video(store: StoreDep, file: Annotated[UploadFile, File()]) -> VideoMeta:
    name = file.filename or "upload"
    suffix = Path(name).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise ApiError(
            ErrorCode.UNSUPPORTED_FORMAT,
            f"'{suffix or name}' is not supported.",
            "Upload an .mp4 or .mov video.",
            status=415,
        )
    vid, d = store.new_dir()
    try:
        src = d / f"source{suffix}"
        _save_upload(file, src)
        try:
            p = probe(src)
        except ProbeError as e:
            raise ApiError(
                ErrorCode.UNSUPPORTED_FORMAT,
                str(e),
                "Check that the file is a playable video.",
                status=415,
            ) from e
        source: CaptureFpsSource = "metadata" if p.tagged_capture_fps else "container"
        rec = VideoRecord(
            id=vid,
            dir=d,
            filename=name,
            probe=p,
            capture_fps=p.tagged_capture_fps or p.measured_fps,
            capture_fps_source=source,
        )
        if rec.capture_fps < settings.min_fps_manual:
            raise ApiError(
                ErrorCode.FPS_TOO_LOW,
                f"Video is {rec.capture_fps:.1f} fps; at least "
                f"{settings.min_fps_manual:.0f} fps is needed.",
                "Record at 240 fps slow motion on a tripod.",
            )
        extract_frames(src, rec.frames_dir)
        rec.warnings = _fps_warnings(rec)
    except BaseException:
        shutil.rmtree(d, ignore_errors=True)
        raise
    store.add(rec)
    return rec.meta()


@router.get("/{video_id}", response_model=VideoMeta)
def get_video(store: StoreDep, video_id: str) -> VideoMeta:
    return store.get(video_id).meta()


@router.patch("/{video_id}", response_model=VideoMeta)
def patch_video(store: StoreDep, video_id: str, patch: VideoPatch) -> VideoMeta:
    rec = store.get(video_id)
    if patch.capture_fps is not None:
        rec.capture_fps = patch.capture_fps
        rec.capture_fps_source = "user"
    if patch.trim is not None:
        if patch.trim.end >= rec.probe.frame_count:
            raise ApiError(
                ErrorCode.FRAME_OUT_OF_RANGE,
                f"Trim end {patch.trim.end} is past the last frame {rec.probe.frame_count - 1}.",
            )
        rec.trim = patch.trim
    rec.warnings = _fps_warnings(rec)
    return rec.meta()


@router.get("/{video_id}/timestamps", response_model=Timestamps)
def get_timestamps(store: StoreDep, video_id: str) -> Timestamps:
    rec = store.get(video_id)
    return Timestamps(video_id=video_id, t_s=rec.times_s)


@router.get("/{video_id}/frames/{index}.jpg", response_class=FileResponse)
def get_frame(store: StoreDep, video_id: str, index: int) -> FileResponse:
    rec = store.get(video_id)
    path = rec.frames_dir / f"{index:06d}.jpg"
    if index < 0 or not path.exists():
        raise ApiError(
            ErrorCode.FRAME_OUT_OF_RANGE,
            f"Frame {index} does not exist (0 to {rec.probe.frame_count - 1}).",
            status=404,
        )
    return FileResponse(
        path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"}
    )


@router.delete("/{video_id}", status_code=204)
def delete_video(store: StoreDep, video_id: str) -> None:
    store.get(video_id)
    store.delete(video_id)
