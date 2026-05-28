"""End-to-end ANPR pipeline orchestrator (M3–M5).

Orchestrates the full accurate detection pipeline:
1. Detection (M2): YOLOv8s detector → bboxes
2. Normalization (M3): Perspective transform to canonical 200x60
3. Quality Gate (M3): Reject low-quality crops before OCR
4. OCR Fusion (M3): PaddleOCR + CRNN char-level voting
5. Tracking (M4): ByteTrack across frames + char voting
6. Region Classification (M5): Route to per-region postprocessor
7. Confidence Gate (M5): Persist or review_queue decision

Target SLA: <2s end-to-end per frame (incl. tracking buffer).
Confidence gate: >=0.75 plate-level, >=0.6 per-char.
"""

from __future__ import annotations

import base64
import io
import logging
from dataclasses import dataclass, field
from typing import Optional

import cv2
import numpy as np

from anpr_core.detect.normalize import detect_corners_from_bbox, normalize_plate
from anpr_core.detect.yolo_detector import Detection, YOLODetector
from anpr_core.ocr.fuser import OCRFuser
from anpr_core.pipeline.voter import CharacterVoter, VotingResult
from anpr_core.postproc.gate import ConfidenceGate, GateDecision
from anpr_core.postproc.region_classifier import RegionClassifier, RegionResult
from anpr_core.postproc.regions.eu import EUPostprocessor
from anpr_core.postproc.regions.india import IndiaPostprocessor
from anpr_core.postproc.regions.us import USPostprocessor
from anpr_core.quality.quality_gate import QualityGate, QualityResult
from anpr_core.tracking.bytetrack_wrapper import PlateTracker, TrackedPlate

logger = logging.getLogger(__name__)


@dataclass
class PipelineDetection:
    """Single detection through pipeline."""

    frame_id: int
    track_id: int
    bbox: tuple[float, float, float, float]  # xyxy
    bbox_conf: float  # Detector confidence
    plate_text: str
    char_confidences: list[float]
    plate_confidence: float
    region: str  # "IN", "EU", "US"
    quality_score: float
    is_low_quality: bool
    postproc_fixes: list[str]  # Confusion fixes applied
    should_persist: bool  # Final gate decision
    reject_reasons: list[str]  # Why rejected (if applicable)


@dataclass
class PipelineOutput:
    """Full pipeline output per frame."""

    frame_id: int
    timestamp: float
    image_shape: tuple[int, int, int]  # H, W, C
    num_raw_detections: int
    num_passed_quality: int
    num_tracked: int
    num_persisted: int
    detections: list[PipelineDetection] = field(default_factory=list)
    stats: dict = field(default_factory=dict)


class ANPROrchestrator:
    """
    End-to-end ANPR pipeline: detect → normalize → quality → OCR → track → classify → gate → persist.
    """

    def __init__(
        self,
        detector_model_path: str | None = None,
        crnn_model_path: str | None = None,
        region_classifier_model_path: str | None = None,
        use_gpu: bool = True,
        device: str = "auto",
    ) -> None:
        """
        Initialize orchestrator with all subcomponents.

        Args:
            detector_model_path: Path to YOLOv8 detector
            crnn_model_path: Path to CRNN weights
            region_classifier_model_path: Path to region classifier weights
            use_gpu: GPU for OCR + region classifier
            device: "auto" | "cpu" | "cuda:0" | "mps"
        """
        logger.info("Initializing ANPROrchestrator...")

        # Detector (M2)
        self.detector = YOLODetector(model_path=detector_model_path, device=device)
        logger.info(f"✓ Detector: {self.detector.model_name}")

        # Normalization (M3)
        self.normalizer = None  # Used as standalone function

        # Quality gating (M3)
        self.quality_gate = QualityGate(
            blur_threshold=100.0,
            glare_threshold=200,
            aspect_ratio_range=(2.5, 8.0),
            min_char_height_px=8,
            min_detection_conf=0.5,
        )
        logger.info("✓ Quality Gate initialized")

        # OCR fusion (M3)
        self.ocr_fuser = OCRFuser(crnn_model_path=crnn_model_path, use_gpu=use_gpu)
        logger.info("✓ OCR Fuser (PaddleOCR + CRNN) initialized")

        # Tracking (M4)
        self.tracker = PlateTracker(
            frame_rate=30, lost_track_buffer=5, minimum_matching_threshold=0.8
        )
        logger.info("✓ Plate Tracker (ByteTrack) initialized")

        # Multi-frame voting (M4)
        self.voter = CharacterVoter(min_votes=3, min_vote_fraction=0.67, confidence_method="mean")
        logger.info("✓ Character Voter initialized")

        # Region classification (M5)
        region_device = "cuda:0" if use_gpu else "cpu"
        self.region_classifier = RegionClassifier(
            model_path=region_classifier_model_path, device=region_device
        )
        logger.info("✓ Region Classifier (IN/EU/US) initialized")

        # Region-specific postprocessors (M5)
        self.postproc_india = IndiaPostprocessor()
        self.postproc_eu = EUPostprocessor()
        self.postproc_us = USPostprocessor()
        logger.info("✓ Region postprocessors (IN/EU/US) initialized")

        # Confidence gate (M5)
        self.confidence_gate = ConfidenceGate(
            min_char_confidence=0.6, min_plate_confidence=0.75
        )
        logger.info("✓ Confidence Gate initialized")

        self.frame_counter = 0

    def process_frame(
        self,
        image: np.ndarray,
        frame_id: int | None = None,
        timestamp: float = 0.0,
    ) -> PipelineOutput:
        """
        Process single frame through full ANPR pipeline.

        Args:
            image: BGR numpy array (H, W, 3)
            frame_id: Frame identifier (auto-increment if None)
            timestamp: Unix timestamp of frame

        Returns:
            PipelineOutput with all detections + pipeline stats
        """
        if frame_id is None:
            frame_id = self.frame_counter
            self.frame_counter += 1

        if image is None or image.size == 0:
            logger.warning(f"Frame {frame_id}: empty image")
            return PipelineOutput(
                frame_id=frame_id,
                timestamp=timestamp,
                image_shape=image.shape if image is not None else (0, 0, 0),
                num_raw_detections=0,
                num_passed_quality=0,
                num_tracked=0,
                num_persisted=0,
            )

        h, w, c = image.shape
        output = PipelineOutput(
            frame_id=frame_id,
            timestamp=timestamp,
            image_shape=(h, w, c),
            num_raw_detections=0,
            num_passed_quality=0,
            num_tracked=0,
            num_persisted=0,
        )

        # ===== M2: DETECT =====
        try:
            raw_detections = self.detector.detect(image)
        except Exception as e:
            logger.error(f"Detector error: {e}", exc_info=True)
            return output

        output.num_raw_detections = len(raw_detections)
        logger.debug(f"Frame {frame_id}: {len(raw_detections)} raw detections")

        if not raw_detections:
            output.stats["stage"] = "no_detections"
            return output

        # ===== M3: NORMALIZE + QUALITY GATE =====
        normalized_crops = []
        quality_filtered_dets = []

        for det in raw_detections:
            x1, y1, x2, y2 = det.bbox
            # Clamp to image bounds
            x1 = max(0, int(x1))
            y1 = max(0, int(y1))
            x2 = min(w, int(x2))
            y2 = min(h, int(y2))

            if x2 <= x1 or y2 <= y1:
                logger.warning(f"Invalid bbox after clamp: {(x1, y1, x2, y2)}")
                continue

            # Crop
            crop = image[y1:y2, x1:x2]

            # Normalize (perspective transform)
            try:
                corners = detect_corners_from_bbox((x1, y1, x2, y2), image.shape)
                normalized_crop = normalize_plate(crop, corners)
            except Exception as e:
                logger.warning(f"Normalization error: {e}")
                normalized_crop = crop

            # Quality gate
            quality_result = self.quality_gate.assess(normalized_crop, detection_conf=det.conf)

            if not quality_result.passes_gate:
                logger.debug(
                    f"Frame {frame_id}: detection rejected (quality_score={quality_result.quality_score:.2f}, "
                    f"issues={quality_result.issues})"
                )
                continue

            normalized_crops.append(normalized_crop)
            quality_filtered_dets.append(det)

        output.num_passed_quality = len(normalized_crops)
        logger.debug(f"Frame {frame_id}: {len(normalized_crops)} passed quality gate")

        if not normalized_crops:
            output.stats["stage"] = "failed_quality_gate"
            return output

        # ===== M3: OCR FUSION =====
        ocr_results = []
        for crop in normalized_crops:
            try:
                fused_result = self.ocr_fuser.recognize(crop)
                ocr_results.append(fused_result)
            except Exception as e:
                logger.error(f"OCR error: {e}", exc_info=True)
                # Fallback: empty result
                from anpr_core.ocr.fuser import FusedOCRResult
                ocr_results.append(
                    FusedOCRResult(
                        plate_text="",
                        char_confidences=[],
                        plate_confidence=0.0,
                        backend_a="paddle",
                        backend_b="crnn",
                    )
                )

        # ===== M4: TRACKING + VOTING =====
        # Prepare detections for tracker
        detections_xyxy = np.array([det.bbox for det in quality_filtered_dets], dtype=np.float32)
        confidences = np.array([det.conf for det in quality_filtered_dets], dtype=np.float32)
        plate_texts = [ocr.plate_text for ocr in ocr_results]
        char_confidences_list = [ocr.char_confidences for ocr in ocr_results]

        # Track
        try:
            tracked_plates = self.tracker.update(
                detections_xyxy=detections_xyxy,
                confidences=confidences,
                plate_texts=plate_texts,
                char_confidences_list=char_confidences_list,
            )
        except Exception as e:
            logger.error(f"Tracking error: {e}", exc_info=True)
            tracked_plates = {}

        output.num_tracked = len(tracked_plates)
        logger.debug(f"Frame {frame_id}: {len(tracked_plates)} tracked plates")

        # ===== M5: REGION CLASSIFY + POSTPROC + CONFIDENCE GATE =====
        pipeline_detections = []

        for idx, (det, ocr_result, tracked) in enumerate(
            zip(quality_filtered_dets, ocr_results, tracked_plates.values())
        ):
            # Region classification
            try:
                region_result = self.region_classifier.classify(normalized_crops[idx])
            except Exception as e:
                logger.warning(f"Region classification error: {e}")
                region_result = RegionResult(region="IN", confidence=0.0, scores={})

            region = region_result.region

            # Get tracked history for voting
            track_history = self.tracker.get_track_history(tracked.track_id)

            # Voting (if we have history)
            final_text = ocr_result.plate_text
            final_char_confs = ocr_result.char_confidences
            final_plate_conf = ocr_result.plate_confidence

            if len(track_history) >= 3:
                try:
                    voting_result = self.voter.vote(track_history)
                    final_text = voting_result.plate_text
                    final_char_confs = voting_result.char_confidences
                    final_plate_conf = voting_result.plate_confidence
                    logger.debug(
                        f"Frame {frame_id}, track {tracked.track_id}: voted text={final_text}, "
                        f"conf={final_plate_conf:.2f}"
                    )
                except Exception as e:
                    logger.warning(f"Voting error: {e}")

            # Region-specific postprocessing
            postproc_result = None
            postproc_fixes = []
            is_valid = False

            if region == "IN":
                try:
                    postproc_result = self.postproc_india.postprocess(final_text)
                    postproc_fixes = postproc_result.fixes_applied
                    is_valid = postproc_result.is_valid
                except Exception as e:
                    logger.warning(f"India postproc error: {e}")

            elif region == "EU":
                try:
                    postproc_result = self.postproc_eu.postprocess(final_text)
                    postproc_fixes = postproc_result.fixes_applied
                    is_valid = postproc_result.is_valid
                except Exception as e:
                    logger.warning(f"EU postproc error: {e}")

            elif region == "US":
                try:
                    postproc_result = self.postproc_us.postprocess(final_text)
                    postproc_fixes = postproc_result.fixes_applied
                    is_valid = postproc_result.is_valid
                except Exception as e:
                    logger.warning(f"US postproc error: {e}")

            # Update text if postproc succeeded
            if postproc_result and is_valid:
                final_text = postproc_result.plate_text

            # Confidence gate
            gate_decision = self.confidence_gate.decide(
                plate_text=final_text,
                char_confidences=final_char_confs,
                plate_confidence=final_plate_conf,
                regex_passed=is_valid,
            )

            # Pipeline detection
            pipeline_det = PipelineDetection(
                frame_id=frame_id,
                track_id=tracked.track_id,
                bbox=tracked.bbox,
                bbox_conf=tracked.confidence,
                plate_text=final_text,
                char_confidences=final_char_confs,
                plate_confidence=final_plate_conf,
                region=region,
                quality_score=1.0,  # Passed quality gate
                is_low_quality=False,
                postproc_fixes=postproc_fixes,
                should_persist=gate_decision.should_persist,
                reject_reasons=gate_decision.reasons,
            )

            pipeline_detections.append(pipeline_det)

            if gate_decision.should_persist:
                output.num_persisted += 1
                logger.info(
                    f"Frame {frame_id}, track {tracked.track_id}: PERSIST "
                    f"text={final_text}, region={region}, conf={final_plate_conf:.2f}"
                )
            else:
                logger.debug(
                    f"Frame {frame_id}, track {tracked.track_id}: REJECT "
                    f"text={final_text}, reasons={gate_decision.reasons}"
                )

        output.detections = pipeline_detections
        output.stats = {
            "stage": "completed",
            "raw_detections": output.num_raw_detections,
            "passed_quality": output.num_passed_quality,
            "tracked": output.num_tracked,
            "persisted": output.num_persisted,
        }

        logger.debug(f"Frame {frame_id}: {output.num_persisted} persisted detections")
        return output

    def reset_tracking(self) -> None:
        """Reset tracking state (e.g., at scene boundary)."""
        self.tracker.reset()
        logger.info("Tracking state reset")


__all__ = ["ANPROrchestrator", "PipelineDetection", "PipelineOutput"]
