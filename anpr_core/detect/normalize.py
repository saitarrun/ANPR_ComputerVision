"""Geometric normalization: perspective transform tilted plates to canonical 200x60."""

from __future__ import annotations

import logging

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# Canonical plate dimensions
PLATE_WIDTH = 200
PLATE_HEIGHT = 60


def normalize_plate(
    crop: np.ndarray,
    corners: np.ndarray | None = None,
) -> np.ndarray:
    """
    Normalize plate to canonical perspective.

    Args:
        crop: Plate crop (BGR)
        corners: 4 corner points (top-left, top-right, bottom-right, bottom-left).
                If None, assumes crop is already roughly aligned.

    Returns:
        Normalized crop (200x60, canonical perspective)
    """
    if crop.size == 0:
        return crop

    h, w = crop.shape[:2]

    # If no corners provided, use crop edges
    if corners is None:
        corners = np.array(
            [
                [0, 0],
                [w, 0],
                [w, h],
                [0, h],
            ],
            dtype=np.float32,
        )
    else:
        corners = np.array(corners, dtype=np.float32)

    # Destination: canonical 200x60 rectangle
    dst_pts = np.array(
        [
            [0, 0],
            [PLATE_WIDTH, 0],
            [PLATE_WIDTH, PLATE_HEIGHT],
            [0, PLATE_HEIGHT],
        ],
        dtype=np.float32,
    )

    # Perspective transform
    M = cv2.getPerspectiveTransform(corners, dst_pts)
    normalized = cv2.warpPerspective(crop, M, (PLATE_WIDTH, PLATE_HEIGHT))

    return normalized


def detect_corners_from_bbox(
    bbox: tuple[float, float, float, float],
    image_shape: tuple[int, int, int],
    tilt_degrees: float = 0.0,
) -> np.ndarray:
    """
    Estimate 4 corner points from bbox (simple heuristic).

    For tilted plates, can apply small rotation estimate.

    Args:
        bbox: (x1, y1, x2, y2) in pixel coords
        image_shape: (H, W, C)
        tilt_degrees: Estimated rotation (radians)

    Returns:
        4 corner points
    """
    x1, y1, x2, y2 = bbox
    w = x2 - x1
    h = y2 - y1

    # Center of bbox
    cx = (x1 + x2) / 2
    cy = (y1 + y2) / 2

    # Corner offsets (before rotation)
    corners = np.array(
        [
            [x1, y1],
            [x2, y1],
            [x2, y2],
            [x1, y2],
        ],
        dtype=np.float32,
    )

    # Rotate around center if tilt provided
    if tilt_degrees != 0:
        angle_rad = np.radians(tilt_degrees)
        cos_a = np.cos(angle_rad)
        sin_a = np.sin(angle_rad)

        for i in range(4):
            # Translate to center
            corners[i, 0] -= cx
            corners[i, 1] -= cy
            # Rotate
            x = corners[i, 0] * cos_a - corners[i, 1] * sin_a
            y = corners[i, 0] * sin_a + corners[i, 1] * cos_a
            # Translate back
            corners[i, 0] = x + cx
            corners[i, 1] = y + cy

    return corners


def estimate_tilt_from_crop(crop: np.ndarray) -> float:
    """
    Estimate tilt angle of plate from crop (heuristic).

    Uses edge detection + Hough line transform to find top/bottom edges.
    Returns estimated tilt in degrees (±25 max).

    Args:
        crop: Plate crop

    Returns:
        Estimated tilt in degrees
    """
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)

    # Edge detection
    edges = cv2.Canny(gray, 50, 150)

    # Hough lines
    lines = cv2.HoughLines(edges, 1, np.pi / 180, 50)

    if lines is None:
        return 0.0

    # Estimate angle from horizontal lines
    angles = []
    for line in lines:
        rho, theta = line[0]
        angle_deg = np.degrees(theta)
        # Normalize to [-90, 90]
        if angle_deg > 90:
            angle_deg -= 180
        angles.append(angle_deg)

    if angles:
        # Average angle
        mean_angle = np.mean(angles)
        # Clamp to ±25
        return np.clip(mean_angle, -25, 25)

    return 0.0


__all__ = [
    "normalize_plate",
    "detect_corners_from_bbox",
    "estimate_tilt_from_crop",
    "PLATE_WIDTH",
    "PLATE_HEIGHT",
]
