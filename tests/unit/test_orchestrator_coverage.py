"""Unit tests for anpr_core.pipeline.orchestrator.

Covers process_frame branches (empty input, detector/OCR/tracking failures,
quality-gate rejection, region/postproc paths, voting, confidence gate) with
mocked subcomponents — no model weights, no GPU.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
from anpr_core.pipeline import orchestrator as orch_module
from anpr_core.pipeline.orchestrator import ANPROrchestrator


def _img(h: int = 100, w: int = 200) -> np.ndarray:
    return np.zeros((h, w, 3), dtype=np.uint8)


def _detection(bbox: tuple = (10, 10, 60, 40), conf: float = 0.9) -> SimpleNamespace:
    return SimpleNamespace(bbox=bbox, conf=conf)


def _quality(passes: bool = True) -> SimpleNamespace:
    return SimpleNamespace(passes_gate=passes, quality_score=0.95, issues=[])


def _ocr(text: str = "MH12AB1234") -> SimpleNamespace:
    return SimpleNamespace(
        plate_text=text,
        char_confidences=[0.9] * max(len(text), 1),
        plate_confidence=0.9,
    )


def _tracked(track_id: int = 7) -> SimpleNamespace:
    return SimpleNamespace(track_id=track_id, bbox=(10, 10, 60, 40), confidence=0.9)


def _region(name: str = "IN") -> SimpleNamespace:
    return SimpleNamespace(region=name, confidence=0.99, scores={})


def _postproc(text: str = "MH12AB1234", valid: bool = True) -> SimpleNamespace:
    return SimpleNamespace(plate_text=text, is_valid=valid, fixes_applied=["0->O"])


def _gate(persist: bool = True) -> SimpleNamespace:
    return SimpleNamespace(should_persist=persist, reasons=[] if persist else ["low_conf"])


def _voted(text: str = "VOTED12") -> SimpleNamespace:
    return SimpleNamespace(
        plate_text=text,
        char_confidences=[0.95] * len(text),
        plate_confidence=0.95,
    )


def _orch(**kw) -> ANPROrchestrator:
    """Build an orchestrator with mocked subcomponents (no heavy __init__)."""
    orch = ANPROrchestrator.__new__(ANPROrchestrator)
    orch.detector = kw.get("detector", MagicMock())
    orch.quality_gate = kw.get("quality_gate", MagicMock())
    orch.ocr_fuser = kw.get("ocr_fuser", MagicMock())
    orch.tracker = kw.get("tracker", MagicMock())
    orch.voter = kw.get("voter", MagicMock())
    orch.region_classifier = kw.get("region_classifier", MagicMock())
    orch.postproc_india = kw.get("postproc_india", MagicMock())
    orch.postproc_eu = kw.get("postproc_eu", MagicMock())
    orch.postproc_us = kw.get("postproc_us", MagicMock())
    orch.confidence_gate = kw.get("confidence_gate", MagicMock())
    orch.frame_counter = 0
    return orch


def _full_pass_orch(**kw) -> ANPROrchestrator:
    """Orchestrator wired for a complete successful frame."""
    detector = MagicMock()
    detector.detect.return_value = [_detection()]
    quality = MagicMock()
    quality.assess.return_value = _quality(True)
    ocr = MagicMock()
    ocr.recognize.return_value = _ocr()
    tracker = MagicMock()
    tracker.update.return_value = {7: _tracked(7)}
    tracker.get_track_history.return_value = []
    region = MagicMock()
    region.classify.return_value = _region("IN")
    postproc = MagicMock()
    postproc.postprocess.return_value = _postproc()
    gate = MagicMock()
    gate.decide.return_value = _gate(True)
    orch = _orch(
        detector=detector,
        quality_gate=quality,
        ocr_fuser=ocr,
        tracker=tracker,
        region_classifier=region,
        postproc_india=postproc,
        confidence_gate=gate,
    )
    for name, value in kw.items():
        setattr(orch, name, value)
    return orch


class TestProcessFrameEdgeCases:
    def test_none_image_returns_empty_output(self):
        orch = _orch()
        out = orch.process_frame(None)
        assert out.num_raw_detections == 0
        assert out.num_persisted == 0
        assert out.image_shape == (0, 0, 0)
        assert out.detections == []

    def test_zero_size_image_returns_empty_output(self):
        orch = _orch()
        out = orch.process_frame(np.zeros((0, 0, 3), dtype=np.uint8))
        assert out.num_raw_detections == 0
        assert out.image_shape == (0, 0, 3)

    def test_frame_id_auto_increments(self):
        orch = _orch()
        out1 = orch.process_frame(None)
        out2 = orch.process_frame(None)
        assert (out1.frame_id, out2.frame_id) == (0, 1)

    def test_explicit_frame_id_kept(self):
        orch = _orch()
        out = orch.process_frame(None, frame_id=42, timestamp=1.5)
        assert out.frame_id == 42
        assert out.timestamp == 1.5

    def test_detector_exception_returns_empty_output(self):
        detector = MagicMock()
        detector.detect.side_effect = RuntimeError("cuda oom")
        orch = _orch(detector=detector)
        out = orch.process_frame(_img(), frame_id=5)
        assert out.frame_id == 5
        assert out.num_raw_detections == 0
        assert out.image_shape == (100, 200, 3)

    def test_no_detections_stage(self):
        detector = MagicMock()
        detector.detect.return_value = []
        orch = _orch(detector=detector)
        out = orch.process_frame(_img())
        assert out.stats["stage"] == "no_detections"
        assert out.num_raw_detections == 0


class TestQualityGatePaths:
    def test_invalid_bbox_after_clamp_is_skipped(self):
        # Bbox far outside a 100x200 image clamps to an empty box.
        detector = MagicMock()
        detector.detect.return_value = [_detection(bbox=(1000, 1000, 2000, 2000))]
        orch = _orch(detector=detector)
        out = orch.process_frame(_img())
        assert out.num_raw_detections == 1
        assert out.stats["stage"] == "failed_quality_gate"

    def test_quality_rejection_stage(self):
        detector = MagicMock()
        detector.detect.return_value = [_detection()]
        quality = MagicMock()
        quality.assess.return_value = _quality(False)
        orch = _orch(detector=detector, quality_gate=quality)
        out = orch.process_frame(_img())
        assert out.num_passed_quality == 0
        assert out.stats["stage"] == "failed_quality_gate"

    def test_normalization_error_falls_back_to_crop(self, monkeypatch):
        def _boom(*args, **kwargs):
            raise RuntimeError("no corners")

        monkeypatch.setattr(orch_module, "detect_corners_from_bbox", _boom)
        orch = _full_pass_orch()
        out = orch.process_frame(_img())
        assert out.num_passed_quality == 1
        assert out.stats["stage"] == "completed"


class TestOcrAndTrackingPaths:
    def test_ocr_exception_uses_empty_fallback(self):
        ocr = MagicMock()
        ocr.recognize.side_effect = RuntimeError("paddle crashed")
        orch = _full_pass_orch(ocr_fuser=ocr)
        out = orch.process_frame(_img())
        # Pipeline still completes; empty OCR text flows through.
        assert out.stats["stage"] == "completed"
        assert out.num_tracked == 1

    def test_tracking_exception_yields_no_tracks(self):
        tracker = MagicMock()
        tracker.update.side_effect = RuntimeError("tracker died")
        orch = _full_pass_orch(tracker=tracker)
        out = orch.process_frame(_img())
        assert out.num_tracked == 0
        assert out.detections == []
        assert out.stats["stage"] == "completed"


class TestRegionPostprocVotingPaths:
    def test_region_classifier_exception_defaults_to_in(self):
        region = MagicMock()
        region.classify.side_effect = RuntimeError("no weights")
        orch = _full_pass_orch(region_classifier=region)
        out = orch.process_frame(_img())
        assert out.detections[0].region == "IN"

    def test_voting_path_uses_voted_text(self):
        tracker = MagicMock()
        tracker.update.return_value = {7: _tracked(7)}
        tracker.get_track_history.return_value = [object(), object(), object()]
        voter = MagicMock()
        voter.vote.return_value = _voted("VOTED12")
        postproc = MagicMock()
        postproc.postprocess.return_value = _postproc(text="VOTED12", valid=True)
        orch = _full_pass_orch(tracker=tracker, voter=voter, postproc_india=postproc)
        out = orch.process_frame(_img())
        voter.vote.assert_called_once()
        assert out.detections[0].plate_text == "VOTED12"

    def test_voting_exception_keeps_ocr_text(self):
        tracker = MagicMock()
        tracker.update.return_value = {7: _tracked(7)}
        tracker.get_track_history.return_value = [object(), object(), object()]
        voter = MagicMock()
        voter.vote.side_effect = RuntimeError("vote failed")
        postproc = MagicMock()
        postproc.postprocess.return_value = _postproc(text="MH12AB1234", valid=True)
        orch = _full_pass_orch(tracker=tracker, voter=voter, postproc_india=postproc)
        out = orch.process_frame(_img())
        assert out.detections[0].plate_text == "MH12AB1234"

    def test_eu_region_branch(self):
        region = MagicMock()
        region.classify.return_value = _region("EU")
        eu = MagicMock()
        eu.postprocess.return_value = _postproc(text="AB123CDE", valid=True)
        orch = _full_pass_orch(region_classifier=region, postproc_eu=eu)
        out = orch.process_frame(_img())
        eu.postprocess.assert_called_once()
        assert out.detections[0].region == "EU"
        assert out.detections[0].plate_text == "AB123CDE"

    def test_us_region_branch(self):
        region = MagicMock()
        region.classify.return_value = _region("US")
        us = MagicMock()
        us.postprocess.return_value = _postproc(text="ABC1234", valid=True)
        orch = _full_pass_orch(region_classifier=region, postproc_us=us)
        out = orch.process_frame(_img())
        us.postprocess.assert_called_once()
        assert out.detections[0].region == "US"

    def test_eu_postproc_exception_keeps_text(self):
        region = MagicMock()
        region.classify.return_value = _region("EU")
        eu = MagicMock()
        eu.postprocess.side_effect = RuntimeError("eu regex exploded")
        orch = _full_pass_orch(region_classifier=region, postproc_eu=eu)
        out = orch.process_frame(_img())
        assert out.detections[0].region == "EU"
        assert out.detections[0].plate_text == "MH12AB1234"

    def test_us_postproc_exception_keeps_text(self):
        region = MagicMock()
        region.classify.return_value = _region("US")
        us = MagicMock()
        us.postprocess.side_effect = RuntimeError("us regex exploded")
        orch = _full_pass_orch(region_classifier=region, postproc_us=us)
        out = orch.process_frame(_img())
        assert out.detections[0].region == "US"
        assert out.detections[0].plate_text == "MH12AB1234"

    def test_postproc_exception_keeps_text(self):
        postproc = MagicMock()
        postproc.postprocess.side_effect = RuntimeError("regex exploded")
        orch = _full_pass_orch(postproc_india=postproc)
        out = orch.process_frame(_img())
        assert out.detections[0].plate_text == "MH12AB1234"

    def test_postproc_invalid_keeps_ocr_text(self):
        postproc = MagicMock()
        postproc.postprocess.return_value = _postproc(text="GARBAGE", valid=False)
        orch = _full_pass_orch(postproc_india=postproc)
        out = orch.process_frame(_img())
        assert out.detections[0].plate_text == "MH12AB1234"
        assert out.detections[0].postproc_fixes == ["0->O"]

    def test_unknown_region_skips_postproc(self):
        region = MagicMock()
        region.classify.return_value = _region("XX")
        orch = _full_pass_orch(region_classifier=region)
        out = orch.process_frame(_img())
        assert out.detections[0].region == "XX"
        assert out.detections[0].plate_text == "MH12AB1234"


class TestConfidenceGatePaths:
    def test_full_pass_persists(self):
        orch = _full_pass_orch()
        out = orch.process_frame(_img(), frame_id=9)
        assert out.num_raw_detections == 1
        assert out.num_passed_quality == 1
        assert out.num_tracked == 1
        assert out.num_persisted == 1
        det = out.detections[0]
        assert det.frame_id == 9
        assert det.track_id == 7
        assert det.plate_text == "MH12AB1234"
        assert det.region == "IN"
        assert det.should_persist is True
        assert det.is_low_quality is False
        assert out.stats["stage"] == "completed"
        assert out.stats["persisted"] == 1

    def test_gate_reject_records_reasons(self):
        gate = MagicMock()
        gate.decide.return_value = _gate(False)
        orch = _full_pass_orch(confidence_gate=gate)
        out = orch.process_frame(_img())
        assert out.num_persisted == 0
        assert out.detections[0].should_persist is False
        assert out.detections[0].reject_reasons == ["low_conf"]

    def test_reset_tracking_delegates(self):
        tracker = MagicMock()
        orch = _orch(tracker=tracker)
        orch.reset_tracking()
        tracker.reset.assert_called_once_with()

    def test_multiple_detections_all_processed(self):
        detector = MagicMock()
        detector.detect.return_value = [
            _detection(),
            _detection(bbox=(70, 10, 120, 40)),
        ]
        quality = MagicMock()
        quality.assess.return_value = _quality(True)
        ocr = MagicMock()
        ocr.recognize.return_value = _ocr()
        tracker = MagicMock()
        tracker.update.return_value = {7: _tracked(7), 8: _tracked(8)}
        tracker.get_track_history.return_value = []
        region = MagicMock()
        region.classify.return_value = _region("IN")
        postproc = MagicMock()
        postproc.postprocess.return_value = _postproc()
        gate = MagicMock()
        gate.decide.return_value = _gate(True)
        orch = _orch(
            detector=detector,
            quality_gate=quality,
            ocr_fuser=ocr,
            tracker=tracker,
            region_classifier=region,
            postproc_india=postproc,
            confidence_gate=gate,
        )
        out = orch.process_frame(_img())
        assert out.num_raw_detections == 2
        assert out.num_tracked == 2
        assert out.num_persisted == 2
        assert [d.track_id for d in out.detections] == [7, 8]


def test_pipeline_output_defaults():
    from anpr_core.pipeline.orchestrator import PipelineOutput

    out = PipelineOutput(
        frame_id=1,
        timestamp=0.0,
        image_shape=(10, 10, 3),
        num_raw_detections=0,
        num_passed_quality=0,
        num_tracked=0,
        num_persisted=0,
    )
    assert out.detections == []
    assert out.stats == {}


def test_orchestrator_module_all_exports():
    assert set(orch_module.__all__) == {
        "ANPROrchestrator",
        "PipelineDetection",
        "PipelineOutput",
    }
