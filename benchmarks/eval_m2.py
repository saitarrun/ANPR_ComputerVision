#!/usr/bin/env python
"""
M2 Evaluation: Detector accuracy + latency gates.
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path
from typing import Optional

import numpy as np
from ultralytics import YOLO

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


class M2EvaluationHarness:
    def __init__(self, detector_model: str = "runs/detect/detector-v1/weights/best.pt"):
        self.detector_model = detector_model
        self.detector = None
        self.load_detector()

    def load_detector(self) -> None:
        if not Path(self.detector_model).exists():
            logger.warning(f"Model not found: {self.detector_model}")
            self.detector = YOLO("yolov8s.pt")
        else:
            logger.info(f"Loading detector: {self.detector_model}")
            self.detector = YOLO(self.detector_model)

    def evaluate_detector(self, dataset_yaml: str, dataset_name: str = "test_set") -> dict[str, float]:
        logger.info(f"\nEvaluating detector on {dataset_name}...")

        try:
            results = self.detector.val(data=dataset_yaml)
            metrics = {
                f"{dataset_name}_mAP50": float(results.box.map50),
                f"{dataset_name}_mAP75": float(results.box.map75),
                f"{dataset_name}_precision": float(results.box.mp),
                f"{dataset_name}_recall": float(results.box.mr),
            }

            logger.info(f"  mAP@0.5: {metrics[f'{dataset_name}_mAP50']:.4f}")
            logger.info(f"  mAP@0.75: {metrics[f'{dataset_name}_mAP75']:.4f}")

            return metrics

        except Exception as e:
            logger.error(f"Evaluation failed: {e}")
            return {}

    def benchmark_latency(self, num_iterations: int = 100, image_size: tuple[int, int] = (640, 480)) -> dict[str, float]:
        logger.info(f"\nBenchmarking latency ({num_iterations} iterations)...")

        latencies = []
        for i in range(num_iterations):
            img = np.random.randint(0, 255, (*image_size, 3), dtype=np.uint8)

            t_start = time.perf_counter()
            _ = self.detector(img, verbose=False)
            t_end = time.perf_counter()

            latency_ms = (t_end - t_start) * 1000
            latencies.append(latency_ms)

        latencies = np.array(latencies)

        metrics = {
            "latency_p50_ms": float(np.percentile(latencies, 50)),
            "latency_p95_ms": float(np.percentile(latencies, 95)),
            "latency_p99_ms": float(np.percentile(latencies, 99)),
            "latency_mean_ms": float(np.mean(latencies)),
        }

        logger.info(f"  p50: {metrics['latency_p50_ms']:.1f}ms, p95: {metrics['latency_p95_ms']:.1f}ms")

        return metrics

    def get_golden_set_path(self, set_name: str) -> Optional[str]:
        golden_root = Path("data/golden-sets")

        paths = {
            "golden_in_small": golden_root / "india_small" / "dataset.yaml",
            "golden_eu": golden_root / "eu" / "dataset.yaml",
            "golden_us": golden_root / "us" / "dataset.yaml",
            "golden_full": golden_root / "full" / "dataset.yaml",
        }

        if set_name not in paths:
            logger.warning(f"Unknown golden set: {set_name}")
            return None

        path = paths[set_name]
        if not path.exists():
            logger.warning(f"Golden set not found: {path}")
            return None

        return str(path)


def check_m2_acceptance_criteria(results: dict) -> bool:
    logger.info("\n" + "=" * 70)
    logger.info("M2 ACCEPTANCE CRITERIA")
    logger.info("=" * 70)

    criteria = {
        "test_set mAP@0.5 ≥ 0.92": results.get("test_set_mAP50", 0) >= 0.92,
        "test_set mAP@0.75 ≥ 0.80": results.get("test_set_mAP75", 0) >= 0.80,
        "Latency p95 < 200ms": results.get("latency_p95_ms", 999) < 200,
        "ONNX export": results.get("onnx_export", False),
    }

    all_passed = True
    for criterion, passed in criteria.items():
        status = "✓" if passed else "✗"
        logger.info(f"  {status} {criterion}")
        if not passed:
            all_passed = False

    return all_passed


def main(model: str = "runs/detect/detector-v1/weights/best.pt", golden_set: str = "golden_in_small", output_file: str = "eval_m2_results.json", quick: bool = False) -> None:
    logger.info("=" * 70)
    logger.info("M2 EVALUATION: Detector Fine-Tuning")
    logger.info("=" * 70)

    harness = M2EvaluationHarness(detector_model=model)

    results = {"model": model, "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")}

    golden_path = harness.get_golden_set_path(golden_set)
    if golden_path:
        metrics = harness.evaluate_detector(golden_path, dataset_name="test_set")
        results.update(metrics)

    num_iters = 20 if quick else 100
    latency_metrics = harness.benchmark_latency(num_iterations=num_iters)
    results.update(latency_metrics)

    results["onnx_export"] = Path("models/best.onnx").exists()
    all_passed = check_m2_acceptance_criteria(results)
    results["m2_acceptance_passed"] = all_passed

    output_path = Path(output_file)
    output_path.write_text(json.dumps(results, indent=2))

    logger.info(f"\n✓ Results saved to {output_file}")

    if all_passed:
        logger.info("\n✓✓✓ M2 ACCEPTANCE PASSED - Ready for M3")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="M2 Evaluation")
    parser.add_argument("--model", default="runs/detect/detector-v1/weights/best.pt")
    parser.add_argument("--set", default="golden_in_small")
    parser.add_argument("--output", default="eval_m2_results.json")
    parser.add_argument("--quick", action="store_true")
    args = parser.parse_args()

    main(model=args.model, golden_set=args.set, output_file=args.output, quick=args.quick)
