"""EU plate postprocessing: multi-pattern Latin alphabet."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# EU format variants
EU_PATTERNS = [
    r"^[A-Z]{2}\d{3}[A-Z]{3}$",  # AB123CDE
    r"^[A-Z]{3}\d{3,4}[A-Z]{0,2}$",  # ABC123DE or ABC1234D
]

CONFUSION_MAP = {
    "0": ["O"],
    "1": ["I"],
    "5": ["S"],
    "O": ["0"],
    "I": ["1"],
    "S": ["5"],
}


@dataclass
class PostprocResult:
    """Result of postprocessing."""

    plate_text: str
    is_valid: bool
    fixes_applied: list[str]


class EUPostprocessor:
    """EU plate format validation."""

    def postprocess(self, plate_text: str) -> PostprocResult:
        """
        Postprocess and validate EU plate.

        Steps:
        1. Uppercase
        2. Try multi-pattern match
        3. If fail, try confusion fixes
        4. Final validation

        Args:
            plate_text: Raw OCR text

        Returns:
            PostprocResult
        """
        fixes = []
        text = plate_text.upper().strip()

        # Check 0: Already valid?
        if self._is_valid(text):
            return PostprocResult(plate_text=text, is_valid=True, fixes_applied=[])

        # Check 1: Try confusion fixes
        text, swap_count = self._fix_confusion(text, max_swaps=1)
        if swap_count > 0:
            fixes.append("fixed_confusion")
            if self._is_valid(text):
                return PostprocResult(plate_text=text, is_valid=True, fixes_applied=fixes)

        # Still invalid
        return PostprocResult(plate_text=text, is_valid=False, fixes_applied=fixes)

    def _is_valid(self, text: str) -> bool:
        """Check if text matches any EU pattern."""
        return any(re.match(pattern, text) for pattern in EU_PATTERNS)

    def _fix_confusion(self, text: str, max_swaps: int = 1) -> tuple[str, int]:
        """Fix common OCR errors."""
        for pos in range(len(text)):
            char = text[pos]

            if char not in CONFUSION_MAP:
                continue

            for candidate in CONFUSION_MAP[char]:
                test_text = text[:pos] + candidate + text[pos + 1 :]

                if self._is_valid(test_text):
                    return test_text, 1

        return text, 0


__all__ = ["EUPostprocessor", "PostprocResult"]
