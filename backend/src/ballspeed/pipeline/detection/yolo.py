"""Optional YOLO detector for a fine-tuned ball model. Install with: uv sync --extra yolo."""

from pathlib import Path
from typing import Any

from ballspeed.pipeline.detection.base import Detection, Image, Roi


class YoloDetector:
    def __init__(self, weights: Path | None, conf: float = 0.25) -> None:
        if weights is None or not weights.exists():
            raise ValueError("Set BALLSPEED_YOLO_WEIGHTS to a trained ball model (.pt file).")
        try:
            from ultralytics import YOLO
        except ImportError as e:
            raise ValueError("ultralytics is not installed. Run: uv sync --extra yolo") from e
        self._model: Any = YOLO(str(weights))
        self._conf = conf

    def detect(self, frame: Image, roi: Roi | None) -> list[Detection]:
        ox, oy = (roi.x, roi.y) if roi else (0, 0)
        view = frame[oy : oy + roi.height, ox : ox + roi.width] if roi else frame
        result = self._model.predict(view, conf=self._conf, verbose=False)[0]
        out = []
        for (x1, y1, x2, y2), score in zip(
            result.boxes.xyxy.tolist(), result.boxes.conf.tolist(), strict=True
        ):
            out.append(
                Detection(
                    (x1 + x2) / 2 + ox, (y1 + y2) / 2 + oy, max(x2 - x1, y2 - y1) / 2, float(score)
                )
            )
        out.sort(key=lambda d: d.score, reverse=True)
        return out
