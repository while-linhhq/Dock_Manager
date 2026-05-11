from __future__ import annotations

import cv2
import numpy as np

from app.schemas.camera_group import CalibrationPointPair
from app.services.panorama_stitch_service import compute_canvas_and_offsets


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


def compute_pair_homography(points: list[CalibrationPointPair]) -> tuple[np.ndarray, int]:
    homography, inliers = compute_homography(points)
    return np.array(homography, dtype=np.float64), inliers


def chain_manual_pair_homographies(
    camera_order: list[int],
    pair_homographies: dict[tuple[int, int], np.ndarray],
    reference_camera_id: int | None = None,
) -> dict[int, np.ndarray]:
    if len(camera_order) < 2:
        raise ValueError('Camera order must contain at least two cameras')
    if len(set(camera_order)) != len(camera_order):
        raise ValueError('Camera order must not contain duplicate cameras')

    reference = reference_camera_id if reference_camera_id is not None else camera_order[0]
    if reference not in camera_order:
        raise ValueError('Reference camera must exist in camera order')

    bidirectional: dict[tuple[int, int], np.ndarray] = {}
    for (source_id, target_id), matrix in pair_homographies.items():
        bidirectional[(source_id, target_id)] = matrix
        bidirectional[(target_id, source_id)] = np.linalg.inv(matrix)

    chained: dict[int, np.ndarray] = {reference: np.eye(3, dtype=np.float64)}

    reference_index = camera_order.index(reference)
    for index in range(reference_index - 1, -1, -1):
        source_id = camera_order[index]
        target_id = camera_order[index + 1]
        matrix = bidirectional.get((source_id, target_id))
        if matrix is None:
            raise ValueError(f'Missing pair homography {source_id} -> {target_id}')
        chained[source_id] = chained[target_id] @ matrix

    for index in range(reference_index + 1, len(camera_order)):
        source_id = camera_order[index]
        target_id = camera_order[index - 1]
        matrix = bidirectional.get((source_id, target_id))
        if matrix is None:
            raise ValueError(f'Missing pair homography {source_id} -> {target_id}')
        chained[source_id] = chained[target_id] @ matrix

    return chained


def compute_canvas_from_manual_homographies(
    frames: dict[int, np.ndarray],
    chained_homographies: dict[int, np.ndarray],
) -> tuple[int, int, dict[int, np.ndarray]]:
    return compute_canvas_and_offsets(frames, chained_homographies)
