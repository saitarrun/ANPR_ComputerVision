"""US plate postprocessing: flexible format."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# US format: flexible (1-3 letters + 1-5 digits, or reversed)
US_PATTERNS = [
    r"^[A-Z]{1,3}\d{1,5}$",  # ABC1234, AB12345, A12345
    r"^\d{1,5}[A-Z]{1,3}$",  # 1234ABC, 12345AB
]

CONFUSION_MAP = {
    "0": ["O"],
    "1": ["I", "L"],
    "5": ["S"],
    "O": ["0"],
    "I": ["1"],
    "L": ["1"],
    "S": ["5"],
}


@dataclass
class PostprocResult:
    """Result of postprocessing."""

    plate_text: str
    is_valid: bool
    fixes_applied: list[str]


class USPostprocessor:
    """US plate format validation."""

    def postprocess(self, plate_text: str) -> PostprocResult:
        """
        Postprocess and validate US plate.

        Steps:
        1. Uppercase
        2. Try flexible patterns
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

        # Check 1: Try removing spaces
        text_no_space = text.replace(" ", "")
        if self._is_valid(text_no_space):
            fixes.append("removed_space")
            return PostprocResult(plate_text=text_no_space, is_valid=True, fixes_applied=fixes)

        # Check 2: Try confusion fixes
        text, swap_count = self._fix_confusion(text, max_swaps=1)
        if swap_count > 0:
            fixes.append("fixed_confusion")
            if self._is_valid(text):
                return PostprocResult(plate_text=text, is_valid=True, fixes_applied=fixes)

        # Still invalid
        return PostprocResult(plate_text=text, is_valid=False, fixes_applied=fixes)

    def _is_valid(self, text: str) -> bool:
        """Check if text matches any US pattern."""
        return any(re.match(pattern, text) for pattern in US_PATTERNS)

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


__all__ = ["USPostprocessor", "PostprocResult"]
