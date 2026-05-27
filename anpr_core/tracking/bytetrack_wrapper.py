"""ByteTrack wrapper for multi-frame plate tracking."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
from supervision import ByteTrack, Detections

logger = logging.getLogger(__name__)


@dataclass
class TrackedPlate:
    """Tracked plate across frames."""

    track_id: int
    frame_idx: int
    bbox: tuple[float, float, float, float]  # xyxy
    plate_text: str
    confidence: float
    char_confidences: list[float]


class PlateTracker:
    """Track plates across video frames using ByteTrack."""

    def __init__(
        self,
        frame_rate: int = 30,
        track_thresh: float = 0.25,
        track_buffer: int = 30,
        match_thresh: float = 0.8,
    ) -> None:
        """
        Args:
            frame_rate: Video FPS
            track_thresh: Detection confidence threshold for tracking
            track_buffer: Frames to keep track alive without detection
            match_thresh: IOU threshold for matching
        """
        self.tracker = ByteTrack(
            frame_rate=frame_rate,
            track_thresh=track_thresh,
            track_buffer=track_buffer,
            match_thresh=match_thresh,
        )

        # Store tracking state: {track_id: [(frame_idx, plate_text, char_confs), ...]}
        self.history = {}
        self.frame_counter = 0

        logger.info(
            f"Initialized PlateTracker (fps={frame_rate}, buffer={track_buffer}, thresh={match_thresh})"
        )

    def update(
        self,
        detections_xyxy: np.ndarray,  # (N, 4)
        confidences: np.ndarray,  # (N,)
        plate_texts: list[str] | None = None,
        char_confidences_list: list[list[float]] | None = None,
    ) -> dict[int, TrackedPlate]:
        """
        Update tracker with detections from current frame.

        Args:
            detections_xyxy: (N, 4) boxes in xyxy format
            confidences: (N,) confidence scores
            plate_texts: (N,) recognized plate strings (optional)
            char_confidences_list: (N,) list of per-char confidence lists

        Returns:
            {track_id: TrackedPlate} for tracks in current frame
        """
        if len(detections_xyxy) == 0:
            self.frame_counter += 1
            return {}

        # Create supervision Detections
        detections = Detections(
            xyxy=detections_xyxy,
            confidence=confidences,
            class_id=np.zeros(len(detections_xyxy), dtype=int),
        )

        # Track
        detections = self.tracker.update_with_detections(detections)

        # Map to TrackedPlate
        tracked = {}
        for i, (box, conf, track_id) in enumerate(
            zip(detections.xyxy, detections.confidence, detections.tracker_id)
        ):
            track_id = int(track_id)

            # Get plate text if available
            plate_text = plate_texts[i] if plate_texts and i < len(plate_texts) else ""
            char_confs = (
                char_confidences_list[i] if char_confidences_list and i < len(char_confidences_list) else []
            )

            # Update history
            if track_id not in self.history:
                self.history[track_id] = []

            self.history[track_id].append(
                {
                    "frame_idx": self.frame_counter,
                    "plate_text": plate_text,
                    "char_confidences": char_confs,
                }
            )

            # Create TrackedPlate
            tracked[track_id] = TrackedPlate(
                track_id=track_id,
                frame_idx=self.frame_counter,
                bbox=tuple(box),
                plate_text=plate_text,
                confidence=float(conf),
                char_confidences=char_confs,
            )

        self.frame_counter += 1

        return tracked

    def get_track_history(self, track_id: int) -> list[dict]:
        """Get all detections for a track."""
        return self.history.get(track_id, [])

    def reset(self) -> None:
        """Reset tracker state."""
        self.tracker.reset()
        self.history.clear()
        self.frame_counter = 0


__all__ = ["PlateTracker", "TrackedPlate"]
