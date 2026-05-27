"""Confidence gating: decide persist vs review queue."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class GateDecision:
    """Gate decision result."""

    should_persist: bool
    confidence_score: float
    reasons: list[str]


class ConfidenceGate:
    """
    Final confidence gating before persistence.

    Rules:
    - Per-char confidence >= min_char_conf
    - Plate-level confidence >= min_plate_conf
    - Regex validation passed
    """

    def __init__(
        self,
        min_char_confidence: float = 0.6,
        min_plate_confidence: float = 0.75,
    ) -> None:
        """
        Args:
            min_char_confidence: Per-character threshold
            min_plate_confidence: Plate-level threshold
        """
        self.min_char_confidence = min_char_confidence
        self.min_plate_confidence = min_plate_confidence

    def decide(
        self,
        plate_text: str,
        char_confidences: list[float],
        plate_confidence: float,
        regex_passed: bool,
    ) -> GateDecision:
        """
        Decide whether to persist detection or route to review queue.

        Args:
            plate_text: Recognized plate string
            char_confidences: Per-character confidences
            plate_confidence: Overall plate confidence
            regex_passed: Whether regex validation passed

        Returns:
            GateDecision (persist or review)
        """
        reasons = []

        # Check 1: Regex passed
        if not regex_passed:
            reasons.append("regex_failed")

        # Check 2: Per-char confidence
        if char_confidences:
            min_char_conf = min(char_confidences)
            if min_char_conf < self.min_char_confidence:
                reasons.append(f"low_char_conf={min_char_conf:.2f} < {self.min_char_confidence}")

        # Check 3: Plate-level confidence
        if plate_confidence < self.min_plate_confidence:
            reasons.append(f"low_plate_conf={plate_confidence:.2f} < {self.min_plate_confidence}")

        # Decision
        should_persist = len(reasons) == 0
        confidence_score = min(char_confidences) if char_confidences else plate_confidence

        return GateDecision(
            should_persist=should_persist,
            confidence_score=confidence_score,
            reasons=reasons,
        )


__all__ = ["ConfidenceGate", "GateDecision"]
