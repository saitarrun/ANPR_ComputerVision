"""File ingest (mp4 or image sequence)."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional

import cv2

from ingest.base import Frame, FrameSource

logger = logging.getLogger(__name__)


class FileSource(FrameSource):
    """Video file or image directory."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

        if self.path.is_file():
            self.cap = cv2.VideoCapture(str(self.path))
            if not self.cap.isOpened():
                raise RuntimeError(f"Cannot open {self.path}")
            self._width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            self._height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            self._fps = self.cap.get(cv2.CAP_PROP_FPS)
            self._is_video = True
            logger.info(f"Video: {self.path}")
        elif self.path.is_dir():
            import glob

            self.images = sorted(glob.glob(str(self.path / "*.jpg")) + glob.glob(str(self.path / "*.png")))
            if not self.images:
                raise RuntimeError(f"No images in {self.path}")
            self.cap = None
            self._idx = 0
            self._width = self._height = self._fps = 0
            self._is_video = False
            logger.info(f"Image dir: {len(self.images)} frames")
        else:
            raise FileNotFoundError(self.path)

    def read(self) -> Optional[Frame]:
        if self._is_video:
            return self._read_video()
        else:
            return self._read_image()

    def _read_video(self) -> Optional[Frame]:
        if not self.cap:
            return None
        ok, image = self.cap.read()
        if not ok:
            return None
        return Frame(
            image=image,
            timestamp=time.time(),
            source_id=f"file-{self.path.name}",
            width=self._width,
            height=self._height,
            fps=self._fps,
        )

    def _read_image(self) -> Optional[Frame]:
        if self._idx >= len(self.images):
            return None
        path = self.images[self._idx]
        image = cv2.imread(path)
        if image is None:
            return None
        if self._width == 0:
            self._height, self._width = image.shape[:2]
        self._idx += 1
        return Frame(
            image=image,
            timestamp=time.time(),
            source_id=f"file-{Path(path).name}",
            width=self._width,
            height=self._height,
            fps=self._fps or 1.0,
        )

    def close(self) -> None:
        if self.cap:
            self.cap.release()

    @property
    def source_id(self) -> str:
        return f"file-{self.path.name}"
