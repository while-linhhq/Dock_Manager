from __future__ import annotations

import cv2
import numpy as np

from app.schemas.camera_group import CalibrationPointPair


def compute_homography(points: list[CalibrationPointPair]) -> tuple[list[list[float]], int]:
    if len(points) < 4:
        raise ValueError('At least 4 point pairs are required')

    src = np.array([point.src for point in points], dtype=np.float32)
    dst = np.array([point.dst for point in points], dtype=np.float32)
    matrix, mask = cv2.findHomography(src, dst, cv2.RANSAC)
    if matrix is None:
        raise ValueError('Could not compute homography from provided points')

    inliers = int(mask.sum()) if mask is not None else len(points)
    return matrix.astype(float).tolist(), inliers


def refine_homography(
    current_homography: list[list[float]] | None,
    points: list[CalibrationPointPair],
) -> tuple[list[list[float]], int]:
    correction, inliers = compute_homography(points)
    correction_matrix = np.array(correction, dtype=np.float64)
    if current_homography is None:
        return correction_matrix.astype(float).tolist(), inliers

    current_matrix = np.array(current_homography, dtype=np.float64)
    refined = correction_matrix @ current_matrix
    return refined.astype(float).tolist(), inliers
