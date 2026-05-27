"""Character-level OCR fusion (PaddleOCR + CRNN)."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

from anpr_core.ocr.crnn_backend import CRNNBackend
from anpr_core.ocr.paddle_backend import PaddleBackend

logger = logging.getLogger(__name__)


@dataclass
class FusedOCRResult:
    """Fused OCR result."""

    plate_text: str
    char_confidences: list[float]
    plate_confidence: float
    backend_a: str  # Which backend was used for each char
    backend_b: str


class OCRFuser:
    """
    Multi-backend OCR fusion.

    Runs PaddleOCR (primary) + CRNN (secondary) in parallel,
    fuses by character-level confidence voting.
    """

    def __init__(
        self,
        crnn_model_path: str | None = None,
        use_gpu: bool = True,
    ) -> None:
        """
        Args:
            crnn_model_path: Path to CRNN weights
            use_gpu: Use GPU
        """
        self.paddle = PaddleBackend(use_gpu=use_gpu, lang="en")
        self.crnn = CRNNBackend(model_path=crnn_model_path, device="cuda:0" if use_gpu else "cpu")

        logger.info("Initialized OCR fusion: PaddleOCR + CRNN")

    def recognize(self, crop: np.ndarray) -> FusedOCRResult:
        """
        Recognize plate text via fusion.

        Args:
            crop: Normalized plate image (200x60 or similar)

        Returns:
            FusedOCRResult with fused text + confidence
        """
        if crop.size == 0:
            return FusedOCRResult(
                plate_text="",
                char_confidences=[],
                plate_confidence=0.0,
                backend_a="paddle",
                backend_b="crnn",
            )

        # Parallel inference
        results_a = self.paddle.recognize(crop)
        results_b = self.crnn.recognize(crop)

        # Fuse
        fused = self._fuse_results(results_a, results_b)

        return fused

    def _fuse_results(self, results_a: list, results_b: list) -> FusedOCRResult:
        """
        Fuse character-level results from 2 backends.

        Fusion logic:
        - If both backends agree (conf within 0.2): use higher confidence
        - If disagree: use higher confidence char
        - Pad shorter result with blanks
        """
        # Equalize lengths
        len_a, len_b = len(results_a), len(results_b)
        max_len = max(len_a, len_b)

        plate_text = ""
        char_confidences = []

        for i in range(max_len):
            # Get results or None
            r_a = results_a[i] if i < len_a else None
            r_b = results_b[i] if i < len_b else None

            if r_a is None and r_b is None:
                break

            if r_a is None:
                # Only B has result
                plate_text += r_b.char
                char_confidences.append(r_b.confidence)
            elif r_b is None:
                # Only A has result
                plate_text += r_a.char
                char_confidences.append(r_a.confidence)
            else:
                # Both have results
                conf_a, conf_b = r_a.confidence, r_b.confidence

                if abs(conf_a - conf_b) < 0.2:
                    # Agreement → use higher confidence
                    if conf_a >= conf_b:
                        plate_text += r_a.char
                        char_confidences.append(conf_a)
                    else:
                        plate_text += r_b.char
                        char_confidences.append(conf_b)
                else:
                    # Disagreement → use higher confidence char
                    if conf_a >= conf_b:
                        plate_text += r_a.char
                        char_confidences.append(conf_a)
                    else:
                        plate_text += r_b.char
                        char_confidences.append(conf_b)

        # Plate-level confidence = min char confidence
        plate_confidence = min(char_confidences) if char_confidences else 0.0

        return FusedOCRResult(
            plate_text=plate_text,
            char_confidences=char_confidences,
            plate_confidence=plate_confidence,
            backend_a="paddle",
            backend_b="crnn",
        )

    def __repr__(self) -> str:
        return f"OCRFuser(A={self.paddle}, B={self.crnn})"
