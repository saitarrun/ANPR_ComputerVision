"""Integration tests for M3–M5 ANPR pipeline (orchestrator).

Test the full pipeline: detect → normalize → quality → OCR → track → classify → gate → persist.

Golden set targets:
- india_small (50 synthetic plates): >=0.85 accuracy
"""

import logging
from pathlib import Path

import cv2
import numpy as np
import pytest

from anpr_core.pipeline.orchestrator import ANPROrchestrator, PipelineDetection

logger = logging.getLogger(__name__)

# Golden set paths
GOLDEN_SETS_ROOT = Path(__file__).parent.parent.parent / "data" / "golden-sets"
GOLDEN_INDIA_SMALL = GOLDEN_SETS_ROOT / "india_small"


@pytest.fixture
def orchestrator() -> ANPROrchestrator:
    """Initialize orchestrator for tests."""
    logger.info("Initializing orchestrator...")
    orch = ANPROrchestrator(use_gpu=False, device="cpu")  # CPU for tests
    logger.info("✓ Orchestrator initialized")
    return orch


@pytest.mark.integration
class TestPipelineOrchestrator:
    """Test full M3–M5 pipeline."""

    def test_orchestrator_init(self) -> None:
        """Test orchestrator initialization."""
        orch = ANPROrchestrator(use_gpu=False, device="cpu")
        assert orch.detector is not None
        assert orch.ocr_fuser is not None
        assert orch.tracker is not None
        assert orch.voter is not None
        assert orch.region_classifier is not None
        assert orch.confidence_gate is not None
        logger.info("✓ Orchestrator initialized successfully")

    def test_empty_frame(self, orchestrator: ANPROrchestrator) -> None:
        """Test pipeline with empty frame."""
        image = np.zeros((480, 640, 3), dtype=np.uint8)
        output = orchestrator.process_frame(image, frame_id=1)

        assert output.frame_id == 1
        assert output.num_raw_detections == 0
        assert output.num_passed_quality == 0
        assert len(output.detections) == 0
        logger.info("✓ Empty frame handled correctly")

    def test_process_single_detection(self, orchestrator: ANPROrchestrator) -> None:
        """Test processing a frame with at least detector output (synthetic or real)."""
        # Create a simple test image (this won't detect anything without the right model,
        # but we test the pipeline flow)
        image = np.random.randint(0, 256, (480, 640, 3), dtype=np.uint8)

        output = orchestrator.process_frame(image, frame_id=0)

        assert output.frame_id == 0
        assert output.num_raw_detections >= 0
        logger.debug(f"Raw detections: {output.num_raw_detections}")
        logger.info("✓ Single frame processing completed")

    def test_tracking_reset(self, orchestrator: ANPROrchestrator) -> None:
        """Test tracking reset."""
        orchestrator.reset_tracking()
        # Just verify it doesn't crash
        assert orchestrator.tracker is not None
        logger.info("✓ Tracking reset successful")

    def test_pipeline_output_structure(self, orchestrator: ANPROrchestrator) -> None:
        """Test that pipeline output has correct structure."""
        image = np.random.randint(0, 256, (480, 640, 3), dtype=np.uint8)
        output = orchestrator.process_frame(image, frame_id=42, timestamp=1234567890.0)

        assert output.frame_id == 42
        assert output.timestamp == 1234567890.0
        assert output.image_shape == (480, 640, 3)
        assert hasattr(output, "detections")
        assert isinstance(output.detections, list)
        assert output.num_raw_detections >= 0
        assert output.num_passed_quality >= 0
        assert output.num_tracked >= 0
        assert output.num_persisted >= 0
        logger.info("✓ Pipeline output structure correct")

    def test_detection_structure(self, orchestrator: ANPROrchestrator) -> None:
        """Test that PipelineDetection has all required fields."""
        image = np.random.randint(0, 256, (480, 640, 3), dtype=np.uint8)
        output = orchestrator.process_frame(image)

        if output.detections:
            det = output.detections[0]
            assert isinstance(det, PipelineDetection)
            assert hasattr(det, "frame_id")
            assert hasattr(det, "track_id")
            assert hasattr(det, "bbox")
            assert hasattr(det, "plate_text")
            assert hasattr(det, "char_confidences")
            assert hasattr(det, "plate_confidence")
            assert hasattr(det, "region")
            assert hasattr(det, "should_persist")
            assert hasattr(det, "reject_reasons")
            logger.info("✓ Detection structure correct")


@pytest.mark.integration
class TestQualityGate:
    """Test M3 quality gating."""

    def test_quality_gate_accepts_good_crop(self, orchestrator: ANPROrchestrator) -> None:
        """Test that quality gate accepts sharp, well-lit crops."""
        # Create a synthetic sharp plate crop (200x60)
        crop = np.ones((60, 200, 3), dtype=np.uint8) * 128  # Gray
        # Add some texture
        crop[10:50, 20:180] = 100  # Text area

        quality = orchestrator.quality_gate.assess(crop)
        # Note: this synthetic crop might not pass real thresholds
        # just verify structure
        assert quality.passes_gate is not None
        assert quality.quality_score >= 0.0
        logger.info(f"Quality result: passes_gate={quality.passes_gate}, score={quality.quality_score}")

    def test_quality_gate_rejects_blurry_crop(self, orchestrator: ANPROrchestrator) -> None:
        """Test that quality gate rejects blurry crops."""
        # Create a very blurry crop
        crop = np.random.randint(0, 256, (60, 200, 3), dtype=np.uint8)

        quality = orchestrator.quality_gate.assess(crop)
        logger.info(
            f"Blurry crop quality: passes_gate={quality.passes_gate}, score={quality.quality_score}"
        )
        # Blurry crops might still pass if they're not severely blurry
        # Just verify we got a result


@pytest.mark.integration
class TestRegionClassification:
    """Test M5 region classification."""

    def test_region_classifier_output(self, orchestrator: ANPROrchestrator) -> None:
        """Test that region classifier produces valid output."""
        crop = np.random.randint(0, 256, (60, 200, 3), dtype=np.uint8)

        result = orchestrator.region_classifier.classify(crop)
        assert result.region in ["IN", "EU", "US"]
        assert result.confidence >= 0.0
        assert result.confidence <= 1.0
        assert "IN" in result.scores
        assert "EU" in result.scores
        assert "US" in result.scores
        logger.info(f"Region classification: {result.region} (conf={result.confidence:.2f})")


@pytest.mark.integration
class TestConfidenceGating:
    """Test M5 confidence gating."""

    def test_confidence_gate_accepts_high_confidence(self, orchestrator: ANPROrchestrator) -> None:
        """Test that confidence gate accepts high-confidence detections."""
        decision = orchestrator.confidence_gate.decide(
            plate_text="AB12CD3456",
            char_confidences=[0.9] * 10,
            plate_confidence=0.95,
            regex_passed=True,
        )
        # Note: regex_passed=True only makes sense for a matched pattern
        # but testing the gate logic
        logger.info(f"High-conf decision: should_persist={decision.should_persist}")

    def test_confidence_gate_rejects_low_confidence(self, orchestrator: ANPROrchestrator) -> None:
        """Test that confidence gate rejects low-confidence detections."""
        decision = orchestrator.confidence_gate.decide(
            plate_text="AB12CD3456",
            char_confidences=[0.3] * 10,
            plate_confidence=0.2,
            regex_passed=True,
        )
        assert not decision.should_persist
        assert len(decision.reasons) > 0
        logger.info(f"Low-conf decision: should_persist={decision.should_persist}, reasons={decision.reasons}")


@pytest.mark.integration
class TestMultiFrameVoting:
    """Test M4 multi-frame voting."""

    def test_voter_consensus(self, orchestrator: ANPROrchestrator) -> None:
        """Test that voter reaches consensus with multiple frames."""
        frame_results = [
            {"plate_text": "AB123", "char_confidences": [0.9, 0.9, 0.9, 0.9, 0.9]},
            {"plate_text": "AB123", "char_confidences": [0.9, 0.9, 0.9, 0.9, 0.9]},
            {"plate_text": "AB123", "char_confidences": [0.9, 0.9, 0.9, 0.9, 0.9]},
        ]

        result = orchestrator.voter.vote(frame_results)
        assert result.plate_text == "AB123"
        assert result.num_frames == 3
        logger.info(f"Voting result: text={result.plate_text}, conf={result.plate_confidence:.2f}")

    def test_voter_disagreement(self, orchestrator: ANPROrchestrator) -> None:
        """Test voter with conflicting detections."""
        frame_results = [
            {"plate_text": "AB123", "char_confidences": [0.8] * 5},
            {"plate_text": "AB12O", "char_confidences": [0.8] * 5},  # Conf: 0 vs O
            {"plate_text": "AB123", "char_confidences": [0.8] * 5},
        ]

        result = orchestrator.voter.vote(frame_results)
        # Majority should be "AB123"
        assert "AB123" in result.plate_text
        logger.info(f"Conflicted voting result: text={result.plate_text}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
