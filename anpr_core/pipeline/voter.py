"""Character-level multi-frame voting."""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class VotingResult:
    """Result of character voting across frames."""

    plate_text: str
    char_confidences: list[float]
    plate_confidence: float
    num_frames: int
    confidence_method: str  # "mean", "min", or "max"


class CharacterVoter:
    """Voting mechanism for characters across video frames."""

    def __init__(
        self,
        min_votes: int = 3,
        min_vote_fraction: float = 0.67,
        confidence_method: str = "mean",
    ) -> None:
        """
        Args:
            min_votes: Minimum votes required (e.g., 3 frames)
            min_vote_fraction: Minimum fraction of votes (e.g., 67%)
            confidence_method: How to combine confidence scores
                - "mean": average confidence
                - "min": minimum confidence (conservative)
                - "max": maximum confidence (optimistic)
        """
        self.min_votes = min_votes
        self.min_vote_fraction = min_vote_fraction
        self.confidence_method = confidence_method

    def vote(self, frame_results: list[dict]) -> VotingResult:
        """
        Vote across multiple frames.

        Each frame_result should have:
        {
            "plate_text": "ABC123",
            "char_confidences": [0.95, 0.92, ...]
        }

        Returns:
            VotedResult with final plate text and char-level confidence
        """
        if not frame_results:
            return VotingResult(
                plate_text="",
                char_confidences=[],
                plate_confidence=0.0,
                num_frames=0,
                confidence_method=self.confidence_method,
            )

        num_frames = len(frame_results)
        max_len = max(len(r["plate_text"]) for r in frame_results)

        voted_text = ""
        voted_confidences = []

        for char_pos in range(max_len):
            # Collect votes for this character position
            votes = []
            confidences = []

            for frame_result in frame_results:
                plate_text = frame_result.get("plate_text", "")
                char_confs = frame_result.get("char_confidences", [])

                if char_pos < len(plate_text):
                    votes.append(plate_text[char_pos])
                    if char_pos < len(char_confs):
                        confidences.append(char_confs[char_pos])

            if not votes:
                continue

            # Majority vote
            char, vote_count = self._majority_vote(votes)

            if vote_count < self.min_votes and vote_count / num_frames < self.min_vote_fraction:
                # Not enough votes
                voted_text += "_"  # Mark as unconfident
                voted_confidences.append(0.0)
            else:
                voted_text += char
                # Confidence: combine across frames that voted for this char
                char_frame_confs = [c for v, c in zip(votes, confidences) if v == char]
                if char_frame_confs:
                    conf = self._combine_confidence(char_frame_confs)
                    voted_confidences.append(conf)
                else:
                    voted_confidences.append(0.5)

        # Plate-level confidence
        plate_confidence = min(voted_confidences) if voted_confidences else 0.0

        return VotingResult(
            plate_text=voted_text,
            char_confidences=voted_confidences,
            plate_confidence=plate_confidence,
            num_frames=num_frames,
            confidence_method=self.confidence_method,
        )

    def _majority_vote(self, votes: list[str]) -> tuple[str, int]:
        """
        Get majority-voted character and vote count.

        Args:
            votes: List of character votes

        Returns:
            (char, vote_count)
        """
        vote_counts = {}
        for v in votes:
            vote_counts[v] = vote_counts.get(v, 0) + 1

        if not vote_counts:
            return "", 0

        char, count = max(vote_counts.items(), key=lambda x: x[1])
        return char, count

    def _combine_confidence(self, confidences: list[float]) -> float:
        """Combine confidence scores from multiple frames."""
        if not confidences:
            return 0.0

        if self.confidence_method == "mean":
            return sum(confidences) / len(confidences)
        elif self.confidence_method == "min":
            return min(confidences)
        elif self.confidence_method == "max":
            return max(confidences)
        else:
            return sum(confidences) / len(confidences)


__all__ = ["CharacterVoter", "VotingResult"]
