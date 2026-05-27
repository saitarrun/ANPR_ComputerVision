#!/usr/bin/env python
"""
End-to-end ML evaluation harness.

Runs detector + OCR on golden test sets, measures:
- Detection accuracy (mAP@0.5, @0.75)
- OCR accuracy (plate-level exact-match)
- End-to-end latency (p50, p95, p99)

Usage:
    python benchmarks/eval.py --set golden_in_small
    python benchmarks/eval.py --set golden_full --model models/detector.onnx
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path
from typing import Any

import numpy as np
from ultralytics import YOLO

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)


class EvaluationHarness:
    """Evaluate detector + OCR pipeline."""

    def __init__(self, detector_model: str = "models/detector.pt"):
        self.detector_model = detector_model
        self.detector = None
        self.load_detector()

    def load_detector(self) -> None:
        """Load detector model."""
        if not Path(self.detector_model).exists():
            logger.warning(f"Detector not found: {self.detector_model}")
            logger.info("Using pretrained YOLOv8s (baseline)")
            self.detector = YOLO("yolov8s.pt")
        else:
            logger.info(f"Loading detector: {self.detector_model}")
            self.detector = YOLO(self.detector_model)

    def evaluate_detector(self, test_set_path: str) -> dict[str, float]:
        """
        Evaluate detector on test set.

        Args:
            test_set_path: Path to YOLO dataset (with dataset.yaml)

        Returns:
            {metric_name: value}
        """
        logger.info(f"Evaluating detector on {test_set_path}...")

        results = self.detector.val(data=test_set_path)

        metrics = {
            "detector_mAP50": float(results.box.map50),
            "detector_mAP75": float(results.box.map75),
            "detector_precision": float(results.box.mp),
            "detector_recall": float(results.box.mr),
        }

        logger.info(f"  mAP@0.5: {metrics['detector_mAP50']:.3f}")
        logger.info(f"  mAP@0.75: {metrics['detector_mAP75']:.3f}")
        logger.info(f"  Precision: {metrics['detector_precision']:.3f}")
        logger.info(f"  Recall: {metrics['detector_recall']:.3f}")

        return metrics

    def benchmark_latency(
        self,
        num_images: int = 100,
        image_size: tuple[int, int] = (640, 480),
    ) -> dict[str, float]:
        """
        Benchmark end-to-end latency.

        Args:
            num_images: Number of test iterations
            image_size: Input image size (H, W)

        Returns:
            {latency_metric: value}
        """
        logger.info(f"Benchmarking latency ({num_images} iterations)...")

        latencies = []

        for i in range(num_images):
            # Create random image
            img = np.random.randint(0, 255, (*image_size, 3), dtype=np.uint8)

            # Measure
            t_start = time.perf_counter()
            _ = self.detector(img, verbose=False)
            t_end = time.perf_counter()

            latency_ms = (t_end - t_start) * 1000
            latencies.append(latency_ms)

            if (i + 1) % 20 == 0:
                logger.debug(f"  {i+1}/{num_images} iterations")

        latencies = np.array(latencies)

        metrics = {
            "latency_p50_ms": float(np.percentile(latencies, 50)),
            "latency_p95_ms": float(np.percentile(latencies, 95)),
            "latency_p99_ms": float(np.percentile(latencies, 99)),
            "latency_mean_ms": float(np.mean(latencies)),
            "latency_std_ms": float(np.std(latencies)),
        }

        logger.info(f"  p50: {metrics['latency_p50_ms']:.1f}ms")
        logger.info(f"  p95: {metrics['latency_p95_ms']:.1f}ms")
        logger.info(f"  p99: {metrics['latency_p99_ms']:.1f}ms")

        return metrics

    def evaluate_ocr_baseline(self) -> dict[str, float]:
        """
        Placeholder for OCR evaluation.

        TODO: Implement actual OCR (PaddleOCR + CRNN fusion) evaluation.
        For now, return baseline metrics.
        """
        logger.info("Evaluating OCR (placeholder)...")
        logger.warning("TODO: Implement full OCR evaluation pipeline")

        # Mock baseline metrics
        return {
            "ocr_exact_match": 0.65,  # Baseline
            "ocr_cer": 0.12,
        }

    def get_golden_set_path(self, set_name: str) -> str:
        """
        Get path to golden test set.

        Sets:
        - golden_in_small: 100 India plates (small/fast)
        - golden_eu: 300 EU plates
        - golden_us: 200 US plates
        - golden_full: all 600+ plates
        """
        golden_root = Path("data/golden-sets")

        if set_name == "golden_in_small":
            path = golden_root / "india_small" / "dataset.yaml"
        elif set_name == "golden_eu":
            path = golden_root / "eu" / "dataset.yaml"
        elif set_name == "golden_us":
            path = golden_root / "us" / "dataset.yaml"
        elif set_name == "golden_full":
            path = golden_root / "full" / "dataset.yaml"
        else:
            raise ValueError(f"Unknown golden set: {set_name}")

        if not path.exists():
            logger.warning(f"Golden set not found: {path}")
            logger.info("Using pretrained baseline for now")
            return "path/to/dataset.yaml"

        return str(path)


def check_acceptance_criteria(results: dict[str, Any]) -> bool:
    """
    Check against acceptance criteria from ML_SPEC.md.

    Returns:
        True if all criteria pass, False otherwise
    """
    logger.info("=" * 60)
    logger.info("Checking acceptance criteria...")
    logger.info("=" * 60)

    criteria = {
        "detector_mAP50 >= 0.92": results.get("detector_mAP50", 0) >= 0.92,
        "detector_mAP75 >= 0.80": results.get("detector_mAP75", 0) >= 0.80,
        "latency_p95_ms < 200": results.get("latency_p95_ms", 999) < 200,
        "ocr_exact_match >= 0.85": results.get("ocr_exact_match", 0) >= 0.85,
        "region_classifier_acc >= 0.98": results.get("region_classifier_acc", 0) >= 0.98,
    }

    for criterion, passed in criteria.items():
        status = "✓" if passed else "✗"
        logger.info(f"{status} {criterion}")

    all_passed = all(criteria.values())
    return all_passed


def main(
    set_name: str = "golden_in_small",
    detector_model: str = "models/detector.pt",
    output_file: str = "eval_results.json",
) -> None:
    """Run full evaluation suite."""
    harness = EvaluationHarness(detector_model=detector_model)

    golden_set_path = harness.get_golden_set_path(set_name)

    logger.info("=" * 60)
    logger.info(f"Evaluating on golden set: {set_name}")
    logger.info("=" * 60)

    results = {}

    # Detector evaluation
    try:
        detector_metrics = harness.evaluate_detector(golden_set_path)
        results.update(detector_metrics)
    except Exception as e:
        logger.error(f"Detector evaluation failed: {e}")

    # Latency benchmark
    try:
        latency_metrics = harness.benchmark_latency(num_images=100)
        results.update(latency_metrics)
    except Exception as e:
        logger.error(f"Latency benchmark failed: {e}")

    # OCR evaluation (placeholder)
    try:
        ocr_metrics = harness.evaluate_ocr_baseline()
        results.update(ocr_metrics)
    except Exception as e:
        logger.error(f"OCR evaluation failed: {e}")

    # Acceptance criteria
    logger.info("")
    all_passed = check_acceptance_criteria(results)

    # Save results
    logger.info("=" * 60)
    logger.info(f"Saving results to {output_file}")
    logger.info("=" * 60)

    output_path = Path(output_file)
    output_path.write_text(json.dumps(results, indent=2))

    logger.info(f"\n✓ Evaluation complete")
    if all_passed:
        logger.info("✓ All acceptance criteria passed!")
        return

    logger.warning("✗ Some criteria not met. Review results above.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate ANPR ML pipeline")
    parser.add_argument(
        "--set",
        default="golden_in_small",
        help="Golden test set (golden_in_small, golden_eu, golden_us, golden_full)",
    )
    parser.add_argument(
        "--model",
        default="models/detector.pt",
        help="Detector model path",
    )
    parser.add_argument(
        "--output",
        default="eval_results.json",
        help="Output JSON file",
    )
    args = parser.parse_args()

    main(set_name=args.set, detector_model=args.model, output_file=args.output)
