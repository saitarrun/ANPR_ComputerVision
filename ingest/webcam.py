"""Laptop/desktop webcam ingest."""

from __future__ import annotations

import logging
import time
from typing import Optional

import cv2

from ingest.base import Frame, FrameSource

logger = logging.getLogger(__name__)


class WebcamSource(FrameSource):
    """Laptop camera via cv2.VideoCapture."""

    def __init__(
        self,
        index: int = 0,
        width: int = 1280,
        height: int = 720,
        fps: float = 30.0,
    ) -> None:
        self.index = index
        self.cap = cv2.VideoCapture(index)
        if not self.cap.isOpened():
            raise RuntimeError(f"Failed to open camera {index}")

        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self.cap.set(cv2.CAP_PROP_FPS, fps)

        self._width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self._height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self._fps = self.cap.get(cv2.CAP_PROP_FPS)
        self._ts_prev = time.time()
        logger.info(f"Opened webcam {index}: {self._width}x{self._height} @ {self._fps} fps")

    def read(self) -> Optional[Frame]:
        ok, image = self.cap.read()
        if not ok:
            return None
        ts = time.time()
        return Frame(
            image=image,
            timestamp=ts,
            source_id=f"webcam-{self.index}",
            width=self._width,
            height=self._height,
            fps=self._fps,
        )

    def close(self) -> None:
        if self.cap:
            self.cap.release()

    @property
    def source_id(self) -> str:
        return f"webcam-{self.index}"
