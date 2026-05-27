"""RTSP camera ingest with reconnect."""

from __future__ import annotations

import logging
import time
from typing import Optional

import cv2

from ingest.base import Frame, FrameSource

logger = logging.getLogger(__name__)


class RTSPSource(FrameSource):
    """RTSP stream with exponential backoff reconnect."""

    def __init__(
        self,
        url: str,
        backoff_sec: float = 2.0,
        max_backoff_sec: float = 60.0,
        width: int = 1280,
        height: int = 720,
    ) -> None:
        self.url = url
        self.backoff_sec = backoff_sec
        self.max_backoff_sec = max_backoff_sec
        self._width = width
        self._height = height

        self.cap: Optional[cv2.VideoCapture] = None
        self._backoff = backoff_sec
        self._last_fail_time = 0.0
        self._connect()

    def _connect(self) -> bool:
        now = time.time()
        if now - self._last_fail_time < self._backoff:
            return False

        try:
            cap = cv2.VideoCapture(self.url)
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._height)

            ok, _ = cap.read()
            if not ok:
                cap.release()
                raise RuntimeError("Cannot read frame")

            self.cap = cap
            self._backoff = self.backoff_sec
            logger.info(f"RTSP connected: {self.url}")
            return True
        except Exception as e:
            logger.warning(f"RTSP connect failed: {e}. Retry in {self._backoff:.1f}s")
            self._last_fail_time = now
            self._backoff = min(self._backoff * 1.5, self.max_backoff_sec)
            return False

    def read(self) -> Optional[Frame]:
        if not self.cap or not self.cap.isOpened():
            if not self._connect():
                return None

        try:
            ok, image = self.cap.read()
            if not ok:
                self.cap.release()
                self.cap = None
                raise RuntimeError("Read failed")

            w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = self.cap.get(cv2.CAP_PROP_FPS)

            return Frame(
                image=image,
                timestamp=time.time(),
                source_id=f"rtsp-{self.url.split('://')[-1][:20]}",
                width=w,
                height=h,
                fps=fps,
            )
        except Exception as e:
            logger.warning(f"RTSP read error: {e}")
            if self.cap:
                self.cap.release()
                self.cap = None
            return None

    def close(self) -> None:
        if self.cap:
            self.cap.release()

    @property
    def source_id(self) -> str:
        return f"rtsp-{self.url.split('://')[-1][:20]}"
