"""PaddleOCR recognition backend."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
from paddleocr import PaddleOCR

logger = logging.getLogger(__name__)


@dataclass
class OCRResult:
    """Single character recognition result."""

    char: str
    confidence: float


class PaddleBackend:
    """PaddleOCR character recognition wrapper."""

    def __init__(self, use_gpu: bool = True, lang: str = "en") -> None:
        """
        Args:
            use_gpu: Use GPU acceleration (falls back to CPU if unavailable)
            lang: Language (en, ch, etc.)
        """
        logger.info(f"Loading PaddleOCR (GPU={use_gpu}, lang={lang})")

        self.ocr = PaddleOCR(
            use_angle_cls=False,  # We normalize geometry ourselves
            lang=lang,
            use_gpu=use_gpu,
            enable_mkldnn=True,  # CPU optimization
        )

    def recognize(self, crop: np.ndarray) -> list[OCRResult]:
        """
        Recognize characters in plate crop.

        Args:
            crop: BGR image, normalized 200x60 or raw bbox

        Returns:
            List of OCRResult (char, confidence) in reading order
        """
        if crop.size == 0:
            return []

        # PaddleOCR expects BGR but internally converts
        results = self.ocr.ocr(crop, cls=False)

        if not results or not results[0]:
            return []

        # results[0] = [(text, score), ...] from left to right
        ocr_results = []
        for text, score in results[0]:
            # Each "text" is typically a single char
            for char in text:
                ocr_results.append(OCRResult(char=char, confidence=float(score)))

        return ocr_results

    def __repr__(self) -> str:
        return "PaddleOCR"
