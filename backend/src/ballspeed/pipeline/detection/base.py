"""Detector interface. Classical CV now; a fine-tuned YOLO model can drop in later."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

import numpy as np
from numpy.typing import NDArray

Image = NDArray[np.uint8]


@dataclass(frozen=True)
class Detection:
    x: float
    y: float
    radius: float
    score: float


@dataclass(frozen=True)
class Roi:
    x: int
    y: int
    width: int
    height: int


class BallDetector(Protocol):
    def detect(self, frame: Image, roi: Roi | None) -> list[Detection]:
        """Return ball candidates in full-frame pixel coordinates, best first."""
        ...


def make_detector(kind: Literal["classical", "yolo"], weights: Path | None) -> BallDetector:
    if kind == "yolo":
        from ballspeed.pipeline.detection.yolo import YoloDetector

        return YoloDetector(weights)
    from ballspeed.pipeline.detection.classical import ClassicalDetector

    return ClassicalDetector()
