"""Integration tests for frame scheduler and pipeline."""

import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock

import cv2
import numpy as np
import pytest

from anpr_core.pipeline.scheduler import FrameScheduler
from ingest.base import Frame, FrameSource
from ingest.file import FileSource


class MockFrameSource(FrameSource):
    """Mock frame source for testing."""

    def __init__(self, num_frames: int = 10, delay_sec: float = 0.01):
        self.num_frames = num_frames
        self.delay_sec = delay_sec
        self.count = 0

    def read(self) -> Frame | None:
        if self.count >= self.num_frames:
            return None
        self.count += 1
        if self.delay_sec > 0:
            time.sleep(self.delay_sec)
        image = np.ones((480, 640, 3), dtype=np.uint8) * (self.count % 256)
        return Frame(
            image=image,
            timestamp=time.time(),
            source_id="mock-source",
            width=640,
            height=480,
            fps=30.0,
        )

    def close(self) -> None:
        pass

    @property
    def source_id(self) -> str:
        return "mock-source"


def test_scheduler_reads_all_frames():
    """Scheduler reads all frames from source."""
    source = MockFrameSource(num_frames=10, delay_sec=0.001)
    scheduler = FrameScheduler(source, max_queue=5)

    frames = []
    while True:
        frame = scheduler.get(timeout=0.5)
        if frame is None and scheduler.stats.frames_read >= 10:
            break
        if frame:
            frames.append(frame)

    scheduler.stop()
    assert len(frames) == 10


def test_scheduler_respects_queue_limit():
    """Scheduler does not exceed max_queue depth."""
    source = MockFrameSource(num_frames=50, delay_sec=0.001)
    max_queue = 5
    scheduler = FrameScheduler(source, max_queue=max_queue)

    time.sleep(0.1)  # Let reader thread fill queue
    queue_depth = scheduler.queue.qsize()
    assert queue_depth <= max_queue

    scheduler.stop()


def test_scheduler_drops_frames_on_backpressure():
    """Scheduler drops oldest frame when queue is full."""
    source = MockFrameSource(num_frames=30, delay_sec=0.005)
    scheduler = FrameScheduler(source, max_queue=3)

    time.sleep(0.2)  # Let frames accumulate
    dropped = scheduler.stats.frames_dropped

    scheduler.stop()
    assert dropped > 0, "Expected frames to be dropped under backpressure"


def test_scheduler_stats_tracking():
    """Scheduler tracks reading statistics."""
    source = MockFrameSource(num_frames=15, delay_sec=0.001)
    scheduler = FrameScheduler(source, max_queue=10)

    frames_read = 0
    while True:
        frame = scheduler.get(timeout=0.5)
        if frame is None and scheduler.stats.frames_read >= 15:
            break
        if frame:
            frames_read += 1

    scheduler.stop()
    assert scheduler.stats.frames_read == 15
    assert scheduler.stats.frames_consumed == frames_read


def test_scheduler_with_image_dir():
    """Scheduler reads from image directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        # Create test images
        for i in range(5):
            img = np.ones((480, 640, 3), dtype=np.uint8) * (i * 50)
            cv2.imwrite(str(tmpdir / f"frame_{i:03d}.jpg"), img)

        source = FileSource(str(tmpdir))
        scheduler = FrameScheduler(source, max_queue=10)

        frames = []
        while True:
            frame = scheduler.get(timeout=0.5)
            if frame is None:
                break
            if frame:
                frames.append(frame)

        scheduler.stop()
        assert len(frames) == 5


def test_scheduler_context_manager():
    """Scheduler works as context manager."""
    source = MockFrameSource(num_frames=5)
    with FrameScheduler(source, max_queue=3) as scheduler:
        frame = scheduler.get(timeout=0.5)
        assert frame is not None
