"""Pixel to metre homography for a plane of the pitch.

vertical_plane: the plane through both middle stumps, which the ball travels in (side-on view).
ground_plane: the pitch surface. An airborne ball is not on it, so projecting the ball there is
only an approximation; prefer vertical_plane for side-on footage.
"""

from itertools import combinations

import cv2
import numpy as np
from numpy.typing import NDArray

from ballspeed.models import Calibration, CalibrationRequest

FloatArray = NDArray[np.float64]

MIN_TRIANGLE_AREA_PX = 25.0
MIN_TRIANGLE_AREA_M = 1e-3


class CalibrationError(ValueError):
    pass


def _min_triangle_area(pts: FloatArray) -> float:
    def area(a: FloatArray, b: FloatArray, c: FloatArray) -> float:
        (ux, uy), (vx, vy) = b - a, c - a
        return abs(float(ux * vy - uy * vx)) / 2

    areas = [area(a, b, c) for a, b, c in combinations(pts, 3)]
    return float(min(areas))


def compute(req: CalibrationRequest) -> Calibration:
    img = np.array([[p.image.x, p.image.y] for p in req.points], dtype=np.float64)
    world = np.array([[p.world.x, p.world.y] for p in req.points], dtype=np.float64)
    if _min_triangle_area(img) < MIN_TRIANGLE_AREA_PX and len(img) == 4:
        raise CalibrationError("Three of the clicked points are almost in a line.")
    if _min_triangle_area(world) < MIN_TRIANGLE_AREA_M and len(world) == 4:
        raise CalibrationError("Three of the reference points are in a line in the real world.")
    found, _ = cv2.findHomography(img, world, method=0)
    if found is None:
        raise CalibrationError("Could not compute a homography from these points.")
    h = np.asarray(found, dtype=np.float64)
    if h is None or not np.all(np.isfinite(h)) or abs(np.linalg.det(h)) < 1e-12:
        raise CalibrationError("Could not compute a homography from these points.")
    h_inv: FloatArray = np.linalg.inv(h).astype(np.float64)
    back = project(h_inv, world)
    err = float(np.mean(np.linalg.norm(back - img, axis=1)))
    return Calibration(
        mode=req.mode,
        points=req.points,
        homography=h.tolist(),
        reprojection_error_px=err,
    )


def project(h: FloatArray | list[list[float]], pts: FloatArray) -> FloatArray:
    hm = np.asarray(h, dtype=np.float64)
    homog = np.hstack([pts, np.ones((len(pts), 1))]) @ hm.T
    out: FloatArray = homog[:, :2] / homog[:, 2:3]
    return out


def metres_per_px(h: FloatArray | list[list[float]], pt: FloatArray) -> float:
    """Local scale of the homography at an image point (mean of the two axis gains)."""
    d = 1.0
    base = project(h, pt[None, :])[0]
    gx = np.linalg.norm(project(h, (pt + np.array([d, 0.0]))[None, :])[0] - base)
    gy = np.linalg.norm(project(h, (pt + np.array([0.0, d]))[None, :])[0] - base)
    return float((gx + gy) / 2)
