from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from itertools import combinations
from typing import Any

import cv2
import numpy as np


MIN_FEATURES = 80
MIN_MATCHES = 16
MIN_INLIERS = 10
RATIO_TEST = 0.75
RANSAC_REPROJ_THRESHOLD = 4.0


@dataclass(frozen=True)
class PairMatchStats:
    source_camera_id: int
    target_camera_id: int
    matches: int
    inliers: int
    confidence: float


@dataclass(frozen=True)
class StitchResult:
    reference_camera_id: int
    canvas_width: int
    canvas_height: int
    homographies: dict[int, list[list[float]]]
    pair_stats: list[PairMatchStats]
    unmatched_camera_ids: list[int]


def detect_features(frame: np.ndarray) -> tuple[list[Any], np.ndarray | None]:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    detector = cv2.AKAZE_create()
    keypoints, descriptors = detector.detectAndCompute(gray, None)

    if descriptors is not None and len(keypoints) >= MIN_FEATURES:
        return list(keypoints), descriptors

    if hasattr(cv2, 'SIFT_create'):
        sift = cv2.SIFT_create()
        keypoints, descriptors = sift.detectAndCompute(gray, None)
        if descriptors is not None and len(keypoints) >= MIN_FEATURES:
            return list(keypoints), descriptors

    orb = cv2.ORB_create(nfeatures=1000)
    keypoints, descriptors = orb.detectAndCompute(gray, None)
    if descriptors is not None:
        return list(keypoints), descriptors

    return list(keypoints or []), descriptors


def _matcher_for(descriptors: np.ndarray) -> cv2.BFMatcher:
    norm = cv2.NORM_HAMMING if descriptors.dtype == np.uint8 else cv2.NORM_L2
    return cv2.BFMatcher(norm, crossCheck=False)


def _ratio_matches(desc_a: np.ndarray, desc_b: np.ndarray) -> list[Any]:
    if desc_a is None or desc_b is None or len(desc_a) < 2 or len(desc_b) < 2:
        return []
    if desc_a.dtype != desc_b.dtype:
        return []
    matches = _matcher_for(desc_a).knnMatch(desc_a, desc_b, k=2)
    good_matches = []
    for candidates in matches:
        if len(candidates) < 2:
            continue
        first, second = candidates
        if first.distance < RATIO_TEST * second.distance:
            good_matches.append(first)
    return good_matches


def _compute_pair_homography(
    keypoints_a: list[Any],
    desc_a: np.ndarray | None,
    keypoints_b: list[Any],
    desc_b: np.ndarray | None,
) -> tuple[np.ndarray | None, int, int, float]:
    if desc_a is None or desc_b is None:
        return None, 0, 0, 0.0

    matches = _ratio_matches(desc_a, desc_b)
    if len(matches) < MIN_MATCHES:
        return None, len(matches), 0, 0.0

    points_a = np.float32([keypoints_a[match.queryIdx].pt for match in matches]).reshape(-1, 1, 2)
    points_b = np.float32([keypoints_b[match.trainIdx].pt for match in matches]).reshape(-1, 1, 2)
    matrix, mask = cv2.findHomography(points_a, points_b, cv2.RANSAC, RANSAC_REPROJ_THRESHOLD)
    if matrix is None or mask is None:
        return None, len(matches), 0, 0.0

    inliers = int(mask.sum())
    confidence = inliers / max(1, len(matches))
    if inliers < MIN_INLIERS:
        return None, len(matches), inliers, confidence

    return matrix.astype(np.float64), len(matches), inliers, confidence


def compute_pairwise_homographies(
    frames: dict[int, np.ndarray],
) -> tuple[dict[tuple[int, int], np.ndarray], list[PairMatchStats]]:
    features = {
        camera_id: detect_features(frame)
        for camera_id, frame in frames.items()
    }
    pairwise: dict[tuple[int, int], np.ndarray] = {}
    stats: list[PairMatchStats] = []

    for camera_a, camera_b in combinations(frames.keys(), 2):
        keypoints_a, desc_a = features[camera_a]
        keypoints_b, desc_b = features[camera_b]
        matrix, matches, inliers, confidence = _compute_pair_homography(
            keypoints_a,
            desc_a,
            keypoints_b,
            desc_b,
        )
        stats.append(
            PairMatchStats(
                source_camera_id=int(camera_a),
                target_camera_id=int(camera_b),
                matches=matches,
                inliers=inliers,
                confidence=round(confidence, 4),
            )
        )
        if matrix is None:
            continue
        pairwise[(int(camera_a), int(camera_b))] = matrix
        pairwise[(int(camera_b), int(camera_a))] = np.linalg.inv(matrix)

    return pairwise, stats


def _normalize_camera_order(
    frames: dict[int, np.ndarray],
    camera_order: list[int] | None,
) -> list[int]:
    if camera_order is None:
        return [int(camera_id) for camera_id in frames.keys()]

    normalized = [int(camera_id) for camera_id in camera_order]
    if len(normalized) < 2:
        raise ValueError('Camera order must contain at least two cameras')
    if len(set(normalized)) != len(normalized):
        raise ValueError('Camera order must not contain duplicate cameras')

    frame_ids = {int(camera_id) for camera_id in frames.keys()}
    missing = [camera_id for camera_id in normalized if camera_id not in frame_ids]
    if missing:
        raise ValueError(f'Camera order contains cameras without frames: {missing}')
    return normalized


def compute_ordered_pairwise_homographies(
    frames: dict[int, np.ndarray],
    camera_order: list[int],
) -> tuple[dict[tuple[int, int], np.ndarray], list[PairMatchStats]]:
    features = {
        camera_id: detect_features(frames[camera_id])
        for camera_id in camera_order
    }
    pairwise: dict[tuple[int, int], np.ndarray] = {}
    stats: list[PairMatchStats] = []

    for camera_a, camera_b in zip(camera_order, camera_order[1:], strict=False):
        keypoints_a, desc_a = features[camera_a]
        keypoints_b, desc_b = features[camera_b]
        matrix, matches, inliers, confidence = _compute_pair_homography(
            keypoints_a,
            desc_a,
            keypoints_b,
            desc_b,
        )
        stats.append(
            PairMatchStats(
                source_camera_id=int(camera_a),
                target_camera_id=int(camera_b),
                matches=matches,
                inliers=inliers,
                confidence=round(confidence, 4),
            )
        )
        if matrix is None:
            frame_width = frames[camera_a].shape[1]
            matrix = np.array(
                [
                    [1.0, 0.0, float(-frame_width)],
                    [0.0, 1.0, 0.0],
                    [0.0, 0.0, 1.0],
                ],
                dtype=np.float64,
            )
        pairwise[(int(camera_a), int(camera_b))] = matrix
        pairwise[(int(camera_b), int(camera_a))] = np.linalg.inv(matrix)

    return pairwise, stats


def _choose_reference_camera(
    camera_ids: list[int],
    pairwise: dict[tuple[int, int], np.ndarray],
    reference_camera_id: int | None,
) -> int:
    if reference_camera_id is not None:
        if reference_camera_id not in camera_ids:
            raise ValueError('Reference camera must be a group member')
        return reference_camera_id

    degrees = {
        camera_id: sum(1 for source, _target in pairwise.keys() if source == camera_id)
        for camera_id in camera_ids
    }
    return max(camera_ids, key=lambda camera_id: (degrees[camera_id], -camera_id))


def chain_homographies(
    camera_ids: list[int],
    pairwise: dict[tuple[int, int], np.ndarray],
    reference_camera_id: int,
) -> dict[int, np.ndarray]:
    chained: dict[int, np.ndarray] = {reference_camera_id: np.eye(3, dtype=np.float64)}
    queue: deque[int] = deque([reference_camera_id])

    while queue:
        current = queue.popleft()
        for candidate in camera_ids:
            if candidate in chained:
                continue
            matrix = pairwise.get((candidate, current))
            if matrix is None:
                continue
            chained[candidate] = chained[current] @ matrix
            queue.append(candidate)

    return chained


def compute_canvas_and_offsets(
    frames: dict[int, np.ndarray],
    chained_homographies: dict[int, np.ndarray],
) -> tuple[int, int, dict[int, np.ndarray]]:
    warped_corners = []
    for camera_id, matrix in chained_homographies.items():
        height, width = frames[camera_id].shape[:2]
        corners = np.float32([
            [0, 0],
            [width, 0],
            [width, height],
            [0, height],
        ]).reshape(-1, 1, 2)
        warped_corners.append(cv2.perspectiveTransform(corners, matrix))

    if not warped_corners:
        raise ValueError('No cameras could be mapped into panorama')

    all_corners = np.concatenate(warped_corners, axis=0)
    min_x, min_y = np.floor(all_corners.min(axis=0).ravel()).astype(int)
    max_x, max_y = np.ceil(all_corners.max(axis=0).ravel()).astype(int)

    translation = np.array(
        [
            [1.0, 0.0, float(-min_x)],
            [0.0, 1.0, float(-min_y)],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )

    canvas_width = max(1, int(max_x - min_x))
    canvas_height = max(1, int(max_y - min_y))
    final_homographies = {
        camera_id: translation @ matrix
        for camera_id, matrix in chained_homographies.items()
    }
    return canvas_width, canvas_height, final_homographies


def auto_stitch(
    frames: dict[int, np.ndarray],
    reference_camera_id: int | None = None,
    camera_order: list[int] | None = None,
) -> StitchResult:
    if len(frames) < 2:
        raise ValueError('At least two camera frames are required for panorama stitching')

    camera_ids = _normalize_camera_order(frames, camera_order)
    if camera_order is None:
        pairwise, pair_stats = compute_pairwise_homographies(frames)
    else:
        pairwise, pair_stats = compute_ordered_pairwise_homographies(frames, camera_ids)

    if not pairwise:
        raise ValueError('Could not find overlapping camera pairs')

    reference = _choose_reference_camera(
        camera_ids,
        pairwise,
        reference_camera_id if camera_order is None else reference_camera_id or camera_ids[0],
    )
    chained = chain_homographies(camera_ids, pairwise, reference)
    canvas_width, canvas_height, final_homographies = compute_canvas_and_offsets(frames, chained)

    unmatched = sorted(set(camera_ids) - set(final_homographies.keys()))
    return StitchResult(
        reference_camera_id=reference,
        canvas_width=canvas_width,
        canvas_height=canvas_height,
        homographies={
            camera_id: matrix.astype(float).tolist()
            for camera_id, matrix in final_homographies.items()
        },
        pair_stats=pair_stats,
        unmatched_camera_ids=unmatched,
    )
