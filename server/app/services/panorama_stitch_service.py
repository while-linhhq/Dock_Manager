from __future__ import annotations

import base64
import zlib
from collections import deque
from dataclasses import dataclass, field
from itertools import combinations
from typing import Any

import cv2
import numpy as np


MIN_FEATURES = 200
MIN_MATCHES = 18
MIN_INLIERS = 12
RATIO_TEST = 0.7
RANSAC_REPROJ_THRESHOLD = 3.5
FEATURE_LONG_EDGE = 960
BLEND_WEIGHT_LONG_EDGE = 900
MIN_DETERMINANT = 1e-6
MAX_HOMOGRAPHY_SCALE = 20.0
MIN_HOMOGRAPHY_SCALE = 0.03


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
    stitch_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class _FeatureSet:
    keypoints: list[Any]
    descriptors: np.ndarray | None


def _resize_for_features(frame: np.ndarray) -> tuple[np.ndarray, float]:
    height, width = frame.shape[:2]
    long_edge = max(width, height)
    if long_edge <= FEATURE_LONG_EDGE:
        return frame, 1.0
    scale = FEATURE_LONG_EDGE / float(long_edge)
    resized = cv2.resize(frame, (int(width * scale), int(height * scale)), interpolation=cv2.INTER_AREA)
    return resized, scale


def _mask_timestamp_overlay(gray: np.ndarray) -> np.ndarray:
    masked = gray.copy()
    height, width = masked.shape[:2]
    # Camera timestamp/name overlays live in the top corners and produce false feature matches.
    top_h = max(24, int(height * 0.08))
    left_w = max(160, int(width * 0.34))
    right_w = max(120, int(width * 0.22))
    masked[:top_h, :left_w] = 0
    masked[:top_h, max(0, width - right_w):] = 0
    return masked


def _rescale_keypoints(keypoints: list[Any], scale: float) -> list[Any]:
    if abs(scale - 1.0) < 1e-6:
        return list(keypoints)
    inv_scale = 1.0 / scale
    scaled = []
    for keypoint in keypoints:
        clone = cv2.KeyPoint(
            keypoint.pt[0] * inv_scale,
            keypoint.pt[1] * inv_scale,
            keypoint.size * inv_scale,
            keypoint.angle,
            keypoint.response,
            keypoint.octave,
            keypoint.class_id,
        )
        scaled.append(clone)
    return scaled


def detect_features(frame: np.ndarray) -> tuple[list[Any], np.ndarray | None]:
    resized, scale = _resize_for_features(frame)
    gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
    gray = _mask_timestamp_overlay(gray)

    if hasattr(cv2, 'SIFT_create'):
        sift = cv2.SIFT_create(nfeatures=3000, contrastThreshold=0.015)
        keypoints, descriptors = sift.detectAndCompute(gray, None)
        if descriptors is not None:
            return _rescale_keypoints(list(keypoints), scale), descriptors

    detector = cv2.AKAZE_create()
    keypoints, descriptors = detector.detectAndCompute(gray, None)
    if descriptors is not None:
        return _rescale_keypoints(list(keypoints), scale), descriptors

    orb = cv2.ORB_create(nfeatures=2500, fastThreshold=12)
    keypoints, descriptors = orb.detectAndCompute(gray, None)
    if descriptors is not None:
        return _rescale_keypoints(list(keypoints), scale), descriptors

    return _rescale_keypoints(list(keypoints or []), scale), descriptors


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


def _is_valid_homography(matrix: np.ndarray, frame_a_shape: tuple[int, ...], frame_b_shape: tuple[int, ...]) -> bool:
    if matrix.shape != (3, 3) or not np.isfinite(matrix).all():
        return False
    determinant = float(np.linalg.det(matrix[:2, :2]))
    if abs(determinant) < MIN_DETERMINANT:
        return False

    height_a, width_a = frame_a_shape[:2]
    height_b, width_b = frame_b_shape[:2]
    corners = np.float32([[0, 0], [width_a, 0], [width_a, height_a], [0, height_a]]).reshape(-1, 1, 2)
    warped = cv2.perspectiveTransform(corners, matrix).reshape(-1, 2)
    if not np.isfinite(warped).all():
        return False

    x_span = float(warped[:, 0].max() - warped[:, 0].min())
    y_span = float(warped[:, 1].max() - warped[:, 1].min())
    if x_span <= 1.0 or y_span <= 1.0:
        return False
    scale_x = x_span / max(1.0, float(width_b))
    scale_y = y_span / max(1.0, float(height_b))
    return MIN_HOMOGRAPHY_SCALE <= scale_x <= MAX_HOMOGRAPHY_SCALE and MIN_HOMOGRAPHY_SCALE <= scale_y <= MAX_HOMOGRAPHY_SCALE


def _compute_pair_homography(
    frame_a_shape: tuple[int, ...],
    keypoints_a: list[Any],
    desc_a: np.ndarray | None,
    frame_b_shape: tuple[int, ...],
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
    if inliers < MIN_INLIERS or not _is_valid_homography(matrix, frame_a_shape, frame_b_shape):
        return None, len(matches), inliers, confidence

    return matrix.astype(np.float64), len(matches), inliers, confidence


def compute_pairwise_homographies(
    frames: dict[int, np.ndarray],
) -> tuple[dict[tuple[int, int], np.ndarray], list[PairMatchStats]]:
    features = {camera_id: _FeatureSet(*detect_features(frame)) for camera_id, frame in frames.items()}
    pairwise: dict[tuple[int, int], np.ndarray] = {}
    stats: list[PairMatchStats] = []

    for camera_a, camera_b in combinations(frames.keys(), 2):
        feature_a = features[camera_a]
        feature_b = features[camera_b]
        matrix, matches, inliers, confidence = _compute_pair_homography(
            frames[camera_a].shape,
            feature_a.keypoints,
            feature_a.descriptors,
            frames[camera_b].shape,
            feature_b.keypoints,
            feature_b.descriptors,
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
    features = {camera_id: _FeatureSet(*detect_features(frames[camera_id])) for camera_id in camera_order}
    pairwise: dict[tuple[int, int], np.ndarray] = {}
    stats: list[PairMatchStats] = []

    failed_pairs: list[str] = []
    for camera_a, camera_b in zip(camera_order, camera_order[1:], strict=False):
        feature_a = features[camera_a]
        feature_b = features[camera_b]
        matrix, matches, inliers, confidence = _compute_pair_homography(
            frames[camera_a].shape,
            feature_a.keypoints,
            feature_a.descriptors,
            frames[camera_b].shape,
            feature_b.keypoints,
            feature_b.descriptors,
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
            failed_pairs.append(f'{camera_a}->{camera_b} matches={matches} inliers={inliers}')
            continue
        pairwise[(int(camera_a), int(camera_b))] = matrix
        pairwise[(int(camera_b), int(camera_a))] = np.linalg.inv(matrix)

    if failed_pairs:
        raise ValueError(
            'Could not auto-match adjacent camera pairs. '
            f'Failed pairs: {failed_pairs}. Use manual pair points for these cameras.'
        )
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


def _camera_mask(frame: np.ndarray, matrix: np.ndarray, canvas_width: int, canvas_height: int) -> np.ndarray:
    source_mask = np.ones(frame.shape[:2], dtype=np.uint8) * 255
    return cv2.warpPerspective(source_mask, matrix, (canvas_width, canvas_height)) > 0


def _encode_weight_map(weight: np.ndarray) -> str:
    payload = np.clip(weight * 255.0, 0, 255).astype(np.uint8)
    return base64.b64encode(zlib.compress(payload.tobytes(), level=6)).decode('ascii')


def _blend_weight_shape(canvas_width: int, canvas_height: int) -> tuple[int, int]:
    long_edge = max(canvas_width, canvas_height)
    if long_edge <= BLEND_WEIGHT_LONG_EDGE:
        return canvas_height, canvas_width
    scale = BLEND_WEIGHT_LONG_EDGE / float(long_edge)
    return max(1, int(round(canvas_height * scale))), max(1, int(round(canvas_width * scale)))


def compute_blend_metadata(
    frames: dict[int, np.ndarray],
    homographies: dict[int, np.ndarray],
    canvas_width: int,
    canvas_height: int,
    reference_camera_id: int,
) -> dict[str, Any]:
    masks = {
        camera_id: _camera_mask(frames[camera_id], matrix, canvas_width, canvas_height)
        for camera_id, matrix in homographies.items()
        if camera_id in frames
    }
    if not masks:
        return {}

    distances: dict[int, np.ndarray] = {}
    for camera_id, mask in masks.items():
        dist = cv2.distanceTransform(mask.astype(np.uint8), cv2.DIST_L2, 5)
        if float(dist.max()) > 0:
            dist = dist / float(dist.max())
        distances[camera_id] = dist.astype(np.float32)

    weight_sum = np.zeros((canvas_height, canvas_width), dtype=np.float32)
    for dist in distances.values():
        weight_sum += dist
    weight_sum += 1e-6

    weight_height, weight_width = _blend_weight_shape(canvas_width, canvas_height)
    encoded_weights: dict[str, str] = {}
    for camera_id, dist in distances.items():
        normalized = dist / weight_sum
        resized = cv2.resize(normalized, (weight_width, weight_height), interpolation=cv2.INTER_AREA)
        encoded_weights[str(camera_id)] = _encode_weight_map(resized)

    exposure_gains = compute_exposure_gains(frames, homographies, masks, reference_camera_id)
    return {
        'blend_mode': 'feather_distance_v1',
        'blend_weights_shape': [weight_height, weight_width],
        'blend_weights': encoded_weights,
        'exposure_gains': {str(camera_id): gain for camera_id, gain in exposure_gains.items()},
    }


def compute_exposure_gains(
    frames: dict[int, np.ndarray],
    homographies: dict[int, np.ndarray],
    masks: dict[int, np.ndarray],
    reference_camera_id: int,
) -> dict[int, float]:
    if reference_camera_id not in frames or reference_camera_id not in homographies:
        return {camera_id: 1.0 for camera_id in homographies.keys()}

    canvas_height, canvas_width = next(iter(masks.values())).shape[:2]
    ref_warped = cv2.warpPerspective(
        frames[reference_camera_id],
        homographies[reference_camera_id],
        (canvas_width, canvas_height),
    )
    ref_gray = cv2.cvtColor(ref_warped, cv2.COLOR_BGR2GRAY).astype(np.float32)
    gains: dict[int, float] = {reference_camera_id: 1.0}

    for camera_id, matrix in homographies.items():
        if camera_id == reference_camera_id or camera_id not in frames:
            continue
        warped = cv2.warpPerspective(frames[camera_id], matrix, (canvas_width, canvas_height))
        gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY).astype(np.float32)
        overlap = masks[reference_camera_id] & masks[camera_id]
        if int(overlap.sum()) < 500:
            gains[camera_id] = 1.0
            continue
        ref_mean = float(ref_gray[overlap].mean())
        cur_mean = float(gray[overlap].mean())
        if cur_mean <= 1.0:
            gains[camera_id] = 1.0
            continue
        gains[camera_id] = round(float(np.clip(ref_mean / cur_mean, 0.7, 1.35)), 4)
    return gains


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
    blend_metadata = compute_blend_metadata(frames, final_homographies, canvas_width, canvas_height, reference)

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
        stitch_metadata=blend_metadata,
    )
