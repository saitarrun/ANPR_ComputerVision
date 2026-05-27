"""iPhone camera ingest (Continuity Camera or RTSP)."""

from __future__ import annotations

import logging
from typing import Optional

import cv2

from ingest.base import Frame, FrameSource
from ingest.rtsp import RTSPSource

logger = logging.getLogger(__name__)


class iPhoneSource(FrameSource):
    """iPhone via Continuity Camera (as cv2 device) or RTSP stream."""

    def __init__(
        self,
        source: str = "continuity",
        device_index: int = 1,
        rtsp_url: Optional[str] = None,
    ) -> None:
        """
        Args:
            source: 'continuity' or 'rtsp'
            device_index: cv2 device index for Continuity (usually 1+)
            rtsp_url: RTSP URL for iPhone streaming app (Larix, IP Webcam, etc.)
        """
        self.source = source
        if source == "continuity":
            from ingest.webcam import WebcamSource

            self._impl: FrameSource = WebcamSource(index=device_index)
            logger.info(f"iPhone Continuity Camera on device {device_index}")
        elif source == "rtsp":
            if not rtsp_url:
                raise ValueError("rtsp_url required for source='rtsp'")
            self._impl = RTSPSource(url=rtsp_url)
            logger.info(f"iPhone RTSP: {rtsp_url}")
        else:
            raise ValueError(f"Unknown source: {source}")

    def read(self) -> Optional[Frame]:
        frame = self._impl.read()
        if frame:
            frame.source_id = f"iphone-{self.source}"
        return frame

    def close(self) -> None:
        self._impl.close()

    @property
    def source_id(self) -> str:
        return f"iphone-{self.source}"
