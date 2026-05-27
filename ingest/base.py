"""Frame ingest interface and base implementation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

import numpy as np


@dataclass
class Frame:
    """Single captured frame."""

    image: np.ndarray
    timestamp: float
    source_id: str
    width: int
    height: int
    fps: float = 0.0


class FrameSource(ABC):
    """Abstract frame source."""

    @abstractmethod
    def read(self) -> Optional[Frame]:
        """Read next frame. Return None if source exhausted/error."""

    @abstractmethod
    def close(self) -> None:
        """Release resources."""

    @property
    @abstractmethod
    def source_id(self) -> str:
        """Unique source identifier."""

    def __enter__(self) -> FrameSource:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
