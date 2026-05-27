"""India plate postprocessing: MH02AB1234 format."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# India format: 2 letters (state) + 2 digits + 2 letters + 4 digits
INDIA_REGEX = r"^[A-Z]{2}\d{2}[A-Z]{2}\d{4}$"

# Character confusion map: common OCR errors
CONFUSION_MAP = {
    "0": ["O"],  # Zero vs O
    "1": ["I", "L"],  # One vs I vs L
    "5": ["S"],  # Five vs S
    "8": ["B"],  # Eight vs B
    "2": ["Z"],  # Two vs Z
    "O": ["0"],  # O vs Zero (reverse)
    "I": ["1"],  # I vs One
    "S": ["5"],  # S vs Five
    "B": ["8"],  # B vs Eight
    "Z": ["2"],  # Z vs Two
}


@dataclass
class PostprocResult:
    """Result of postprocessing."""

    plate_text: str
    is_valid: bool
    fixes_applied: list[str]


class IndiaPostprocessor:
    """India plate format validation + confusion fixing."""

    def postprocess(self, plate_text: str) -> PostprocResult:
        """
        Postprocess and validate India plate.

        Steps:
        1. Uppercase
        2. Try regex match
        3. If fail, try confusion-map swaps (up to 2)
        4. Final validation

        Args:
            plate_text: Raw OCR text

        Returns:
            PostprocResult with fixed text + validity
        """
        fixes = []
        text = plate_text.upper().strip()

        # Check 0: Already valid?
        if self._is_valid(text):
            return PostprocResult(plate_text=text, is_valid=True, fixes_applied=[])

        # Check 1: Try single-char confusion fixes
        text, swap_count = self._fix_confusion(text, max_swaps=1)
        if swap_count > 0:
            fixes.append(f"fixed_confusion_1_char")
            if self._is_valid(text):
                return PostprocResult(plate_text=text, is_valid=True, fixes_applied=fixes)

        # Check 2: Try multi-char confusion fixes (up to 2 chars)
        text_orig = plate_text.upper().strip()
        text, swap_count = self._fix_confusion(text_orig, max_swaps=2)
        if swap_count > 0:
            fixes.append(f"fixed_confusion_2_chars")
            if self._is_valid(text):
                return PostprocResult(plate_text=text, is_valid=True, fixes_applied=fixes)

        # Still invalid
        return PostprocResult(plate_text=text, is_valid=False, fixes_applied=fixes)

    def _is_valid(self, text: str) -> bool:
        """Check if text matches India regex."""
        return re.match(INDIA_REGEX, text) is not None

    def _fix_confusion(self, text: str, max_swaps: int = 1) -> tuple[str, int]:
        """
        Attempt to fix characters via confusion map.

        Simple greedy approach: for each position, if current char
        has a confusion entry, try swapping with candidates.

        Args:
            text: Text to fix
            max_swaps: Max number of character swaps

        Returns:
            (fixed_text, num_swaps_made)
        """
        best_text = text
        best_swaps = 0

        # Try all single-swap combinations
        for pos in range(len(text)):
            char = text[pos]

            if char not in CONFUSION_MAP:
                continue

            for candidate in CONFUSION_MAP[char]:
                test_text = text[:pos] + candidate + text[pos + 1 :]

                if self._is_valid(test_text):
                    return test_text, 1

        # Try all 2-swap combinations
        if max_swaps >= 2:
            for pos1 in range(len(text)):
                char1 = text[pos1]
                if char1 not in CONFUSION_MAP:
                    continue

                for cand1 in CONFUSION_MAP[char1]:
                    text_after_1 = text[:pos1] + cand1 + text[pos1 + 1 :]

                    for pos2 in range(pos1 + 1, len(text)):
                        char2 = text_after_1[pos2]
                        if char2 not in CONFUSION_MAP:
                            continue

                        for cand2 in CONFUSION_MAP[char2]:
                            test_text = text_after_1[:pos2] + cand2 + text_after_1[pos2 + 1 :]

                            if self._is_valid(test_text):
                                return test_text, 2

        return text, 0


__all__ = ["IndiaPostprocessor", "PostprocResult"]
