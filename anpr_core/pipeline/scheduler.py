"""Frame scheduler with bounded queue and backpressure."""

from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

from ingest.base import Frame, FrameSource

logger = logging.getLogger(__name__)


@dataclass
class SchedulerStats:
    """Scheduler stats."""

    frames_read: int = 0
    frames_dropped: int = 0
    frames_consumed: int = 0
    queue_size: int = 0
    fps_actual: float = 0.0
    ts_start: float = field(default_factory=time.time)

    @property
    def elapsed(self) -> float:
        return time.time() - self.ts_start

    @property
    def fps_avg(self) -> float:
        if self.elapsed < 0.1:
            return 0.0
        return self.frames_read / self.elapsed


class FrameScheduler:
    """Thread-safe frame queue from source."""

    def __init__(self, source: FrameSource, max_queue: int = 10) -> None:
        self.source = source
        self.max_queue = max_queue
        self.queue: queue.Queue[Frame] = queue.Queue(maxsize=max_queue)
        self.stats = SchedulerStats()
        self._stop = False
        self._thread = threading.Thread(target=self._reader_loop, daemon=True)
        self._thread.start()

    def _reader_loop(self) -> None:
        try:
            while not self._stop:
                frame = self.source.read()
                if frame is None:
                    logger.info("Source exhausted")
                    break

                self.stats.frames_read += 1

                try:
                    self.queue.put_nowait(frame)
                except queue.Full:
                    try:
                        self.queue.get_nowait()
                        self.stats.frames_dropped += 1
                        self.queue.put_nowait(frame)
                    except queue.Empty:
                        pass
        except Exception as e:
            logger.exception(f"Reader loop error: {e}")
        finally:
            self.source.close()

    def get(self, timeout: float = 0.1) -> Optional[Frame]:
        try:
            frame = self.queue.get(timeout=timeout)
            self.stats.frames_consumed += 1
            self.stats.queue_size = self.queue.qsize()
            return frame
        except queue.Empty:
            return None

    def stop(self) -> None:
        self._stop = True
        self._thread.join(timeout=1.0)

    def __enter__(self) -> FrameScheduler:
        return self

    def __exit__(self, *args: object) -> None:
        self.stop()
