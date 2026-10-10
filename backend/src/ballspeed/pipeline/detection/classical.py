"""Background subtraction plus blob filtering by size, shape and brightness."""

import math
from dataclasses import dataclass

import cv2
import numpy as np

from ballspeed.pipeline.detection.base import Detection, Image, Roi


@dataclass(frozen=True)
class ClassicalConfig:
    min_area_px: float = 4.0
    max_area_px: float = 900.0
    max_aspect: float = 4.0
    min_fill: float = 0.35
    min_brightness: float = 150.0
    max_saturation: float = 90.0
    var_threshold: float = 24.0
    history: int = 120


class ClassicalDetector:
    """Stateful: feed frames in order. A bright, compact, moving blob is a ball candidate."""

    def __init__(self, config: ClassicalConfig | None = None) -> None:
        self.cfg = config or ClassicalConfig()
        self._mog = cv2.createBackgroundSubtractorMOG2(
            history=self.cfg.history, varThreshold=self.cfg.var_threshold, detectShadows=False
        )
        self._kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))

    def detect(self, frame: Image, roi: Roi | None) -> list[Detection]:
        ox, oy = (roi.x, roi.y) if roi else (0, 0)
        view = frame[oy : oy + roi.height, ox : ox + roi.width] if roi else frame
        mask = self._mog.apply(view)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, self._kernel)
        hsv = cv2.cvtColor(view, cv2.COLOR_BGR2HSV)
        n, labels, stats, cents = cv2.connectedComponentsWithStats(mask, connectivity=8)
        out: list[Detection] = []
        for i in range(1, n):
            x, y, w, h, area = (int(v) for v in stats[i])
            if not self.cfg.min_area_px <= area <= self.cfg.max_area_px:
                continue
            aspect = max(w, h) / max(min(w, h), 1)
            fill = area / (w * h)
            if aspect > self.cfg.max_aspect or fill < self.cfg.min_fill:
                continue
            blob = labels[y : y + h, x : x + w] == i
            pix = hsv[y : y + h, x : x + w][blob]
            bright, sat = float(pix[:, 2].mean()), float(pix[:, 1].mean())
            if bright < self.cfg.min_brightness or sat > self.cfg.max_saturation:
                continue
            # Brightness-weighted centroid is steadier than the mask centroid for tiny blobs.
            vals = view[y : y + h, x : x + w].astype(np.float64).mean(axis=2) * blob
            total = vals.sum()
            yy, xx = np.mgrid[y : y + h, x : x + w]
            cx = float((vals * xx).sum() / total) if total else float(cents[i][0])
            cy = float((vals * yy).sum() / total) if total else float(cents[i][1])
            score = fill * min(bright / 255, 1.0) / aspect
            out.append(Detection(cx + ox, cy + oy, math.sqrt(area / math.pi), score))
        out.sort(key=lambda d: d.score, reverse=True)
        return out
