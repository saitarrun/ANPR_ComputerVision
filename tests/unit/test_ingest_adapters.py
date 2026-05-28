"""Unit tests for ingest adapters."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import cv2
import numpy as np
import pytest

from ingest.base import Frame, FrameSource
from ingest.file import FileSource
from ingest.iphone import iPhoneSource
from ingest.rtsp import RTSPSource
from ingest.webcam import WebcamSource


def test_frame_creation():
    """Frame instantiation."""
    image = np.zeros((720, 1280, 3), dtype=np.uint8)
    frame = Frame(
        image=image,
        timestamp=1234567890.5,
        source_id="test-source",
        width=1280,
        height=720,
        fps=30.0,
    )
    assert frame.width == 1280
    assert frame.height == 720
    assert frame.fps == 30.0
    assert frame.image.shape == (720, 1280, 3)


def test_frame_defaults():
    """Frame with default fps."""
    image = np.zeros((480, 640, 3), dtype=np.uint8)
    frame = Frame(
        image=image,
        timestamp=1234567890.0,
        source_id="cam",
        width=640,
        height=480,
    )
    assert frame.fps == 0.0


@patch("cv2.VideoCapture")
def test_webcam_init(mock_capture):
    """WebcamSource initialization."""
    mock_cap = MagicMock()
    mock_cap.isOpened.return_value = True
    mock_cap.get.side_effect = [1280.0, 720.0, 30.0]
    mock_capture.return_value = mock_cap

    source = WebcamSource(index=0, width=1280, height=720, fps=30.0)
    assert source.source_id == "webcam-0"
    assert source.index == 0
    mock_capture.assert_called_once_with(0)


@patch("cv2.VideoCapture")
def test_webcam_init_fail(mock_capture):
    """WebcamSource fails if camera unavailable."""
    mock_cap = MagicMock()
    mock_cap.isOpened.return_value = False
    mock_capture.return_value = mock_cap

    with pytest.raises(RuntimeError, match="Failed to open camera"):
        WebcamSource(index=0)


def test_file_source_image_dir():
    """FileSource reads image directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        # Create dummy images
        img1 = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.imwrite(str(tmpdir / "frame_001.jpg"), img1)
        cv2.imwrite(str(tmpdir / "frame_002.jpg"), img1)

        source = FileSource(str(tmpdir))
        assert source._is_video is False
        assert len(source.images) == 2


def test_file_source_nonexistent():
    """FileSource raises on missing file."""
    with pytest.raises(FileNotFoundError):
        FileSource("/nonexistent/path/file.mp4")


def test_file_source_empty_dir():
    """FileSource raises on empty image dir."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with pytest.raises(RuntimeError, match="No images"):
            FileSource(str(tmpdir))


def test_file_source_read_image():
    """FileSource reads images from directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        # Create dummy image
        img = np.ones((480, 640, 3), dtype=np.uint8) * 128
        cv2.imwrite(str(tmpdir / "frame.jpg"), img)

        source = FileSource(str(tmpdir))
        frame = source.read()

        assert frame is not None
        assert frame.image.shape == (480, 640, 3)
        assert frame.source_id == f"file-frame.jpg"
