"""Quality gating: reject low-quality detections before OCR."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import cv2
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class QualityResult:
    """Quality assessment result."""

    passes_gate: bool
    quality_score: float  # 0.0-1.0
    issues: list[str]  # List of failed checks


class QualityGate:
    """Assess plate crop quality before OCR."""

    def __init__(
        self,
        blur_threshold: float = 100.0,
        glare_threshold: float = 200,
        aspect_ratio_range: tuple[float, float] = (2.5, 8.0),
        min_char_height_px: int = 8,
        min_detection_conf: float = 0.5,
    ) -> None:
        """
        Args:
            blur_threshold: Laplacian variance threshold (>= = sharp)
            glare_threshold: Histogram peak threshold (<= = no glare)
            aspect_ratio_range: (min, max) w/h ratio
            min_char_height_px: Minimum character height in pixels
            min_detection_conf: Minimum detector confidence
        """
        self.blur_threshold = blur_threshold
        self.glare_threshold = glare_threshold
        self.aspect_ratio_range = aspect_ratio_range
        self.min_char_height_px = min_char_height_px
        self.min_detection_conf = min_detection_conf

    def assess(
        self,
        crop: np.ndarray,
        bbox: tuple[float, float, float, float] | None = None,
        detection_conf: float = 1.0,
    ) -> QualityResult:
        """
        Assess crop quality.

        Args:
            crop: Plate crop (BGR)
            bbox: (x1, y1, x2, y2) in original image coords
            detection_conf: Detector confidence (0-1)

        Returns:
            QualityResult with pass/fail + issues
        """
        issues = []

        # Check 1: Detection confidence
        if detection_conf < self.min_detection_conf:
            issues.append(f"detection_conf={detection_conf:.2f} < {self.min_detection_conf}")

        # Check 2: Blur (Laplacian variance)
        blur_score = self._blur_score(crop)
        if blur_score < self.blur_threshold:
            issues.append(f"blur={blur_score:.1f} < {self.blur_threshold}")

        # Check 3: Glare (histogram peak)
        glare_score = self._glare_score(crop)
        if glare_score > self.glare_threshold:
            issues.append(f"glare={glare_score:.1f} > {self.glare_threshold}")

        # Check 4: Aspect ratio sanity
        h, w = crop.shape[:2]
        aspect = w / h if h > 0 else 0
        min_aspect, max_aspect = self.aspect_ratio_range
        if not (min_aspect <= aspect <= max_aspect):
            issues.append(f"aspect_ratio={aspect:.2f} not in [{min_aspect}, {max_aspect}]")

        # Check 5: Minimum character height
        if h < self.min_char_height_px:
            issues.append(f"height={h} < {self.min_char_height_px}")

        # Overall quality score: 0.0 if any check fails, 1.0 if all pass
        quality_score = 0.0 if issues else 1.0

        passes_gate = len(issues) == 0

        return QualityResult(
            passes_gate=passes_gate,
            quality_score=quality_score,
            issues=issues,
        )

    def _blur_score(self, crop: np.ndarray) -> float:
        """
        Compute blur metric (Laplacian variance).

        Higher = sharper. Typical range: [0, 500+].
        Threshold: >= 100 is acceptable.
        """
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        laplacian = cv2.Laplacian(gray, cv2.CV_64F)
        variance = laplacian.var()
        return float(variance)

    def _glare_score(self, crop: np.ndarray) -> float:
        """
        Compute glare metric (histogram peak).

        Lower = less glare/overexposed. Typical range: [0, 255].
        Threshold: <= 200 is acceptable.
        """
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        hist = cv2.calcHist([gray], [0], None, [256], [0, 256])
        peak = float(np.max(hist))
        return peak


def should_skip_ocr(quality_result: QualityResult) -> bool:
    """
    Decide whether to skip OCR based on quality.

    Args:
        quality_result: Quality assessment

    Returns:
        True if should skip OCR
    """
    return not quality_result.passes_gate


__all__ = ["QualityGate", "QualityResult", "should_skip_ocr"]
