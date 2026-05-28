#!/usr/bin/env python
"""
M2 Complete Evaluation: Kaggle Detector accuracy + latency + export.
Runs after training completes.
"""

import json
import logging
import time
from pathlib import Path

import numpy as np
from ultralytics import YOLO

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

class M2KaggleEvaluation:
    def __init__(self):
        self.model_path = Path("runs/detect/runs/detect/kaggle-plate-detection/weights/best.pt")
        self.dataset_yaml = Path("/Users/saitarrunpitta/.cache/anpr-datasets/dataset.yaml")
        self.model = None
    def load_model(self):
        if not self.model_path.exists():
            logger.error(f"Model not found: {self.model_path}")
            return False
        logger.info(f"Loading model: {self.model_path}")
        self.model = YOLO(str(self.model_path))
        return True

    def validate(self) -> dict:
        """Validate on val set."""
        if not self.model:
            return {}

        logger.info("\nValidating on validation set...")
        try:
            results = self.model.val(data=str(self.dataset_yaml), split='val')
            metrics = {
                "val_mAP50": float(results.box.map50),
                "val_mAP75": float(results.box.map75),
                "val_mAP": float(results.box.map),
                "val_precision": float(results.box.mp),
                "val_recall": float(results.box.mr),
            }
            logger.info(f"  mAP@0.5: {metrics['val_mAP50']:.4f}")
            logger.info(f"  mAP@0.75: {metrics['val_mAP75']:.4f}")
            logger.info(f"  Precision: {metrics['val_precision']:.4f}")
            logger.info(f"  Recall: {metrics['val_recall']:.4f}")
            return metrics
        except Exception as e:
            logger.error(f"Validation failed: {e}")
            return {}

    def test(self) -> dict:
        """Test on test set."""
        if not self.model:
            return {}

        logger.info("\nTesting on test set...")
        try:
            results = self.model.val(data=str(self.dataset_yaml), split='test')
            metrics = {
                "test_mAP50": float(results.box.map50),
                "test_mAP75": float(results.box.map75),
                "test_mAP": float(results.box.map),
                "test_precision": float(results.box.mp),
                "test_recall": float(results.box.mr),
            }
            logger.info(f"  mAP@0.5: {metrics['test_mAP50']:.4f}")
            logger.info(f"  mAP@0.75: {metrics['test_mAP75']:.4f}")
            logger.info(f"  Precision: {metrics['test_precision']:.4f}")
            logger.info(f"  Recall: {metrics['test_recall']:.4f}")
            return metrics
        except Exception as e:
            logger.error(f"Testing failed: {e}")
            return {}

    def benchmark_latency(self, num_iterations: int = 100) -> dict:
        """Benchmark inference latency."""
        if not self.model:
            return {}

        logger.info(f"\nBenchmarking latency ({num_iterations} iterations on CPU)...")

        # Warmup
        for _ in range(5):
            img = np.random.randint(0, 255, (640, 480, 3), dtype=np.uint8)
            _ = self.model(img, verbose=False)

        latencies = []
        for i in range(num_iterations):
            img = np.random.randint(0, 255, (640, 480, 3), dtype=np.uint8)
            t_start = time.perf_counter()
            _ = self.model(img, verbose=False)
            t_end = time.perf_counter()
            latency_ms = (t_end - t_start) * 1000
            latencies.append(latency_ms)

            if (i + 1) % 25 == 0:
                logger.info(f"  {i+1}/{num_iterations} iterations...")

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
        logger.info(f"  mean: {metrics['latency_mean_ms']:.1f}ms (±{metrics['latency_std_ms']:.1f}ms)")

        return metrics

    def export_model(self) -> dict:
        """Export to ONNX and TFLite."""
        if not self.model:
            return {}

        logger.info("\nExporting model...")
        exports = {}

        for fmt in ["onnx", "tflite"]:
            try:
                logger.info(f"  Exporting {fmt.upper()}...")
                export_path = self.model.export(format=fmt, imgsz=640)
                exports[fmt] = str(export_path)
                logger.info(f"    ✓ {export_path}")
            except Exception as e:
                logger.warning(f"    ✗ {fmt} export failed: {e}")

        return exports

    def check_acceptance_criteria(self, results: dict) -> bool:
        """Check M2 acceptance criteria."""
        logger.info("\n" + "="*70)
        logger.info("M2 ACCEPTANCE CRITERIA (Kaggle Dataset)")
        logger.info("="*70)

        criteria = {
            "test mAP@0.5 ≥ 0.80": results.get("test_mAP50", 0) >= 0.80,
            "test mAP@0.75 ≥ 0.60": results.get("test_mAP75", 0) >= 0.60,
            "latency p95 < 250ms": results.get("latency_p95_ms", 999) < 250,
            "ONNX export": "onnx" in results.get("exports", {}),
        }

        all_passed = True
        for criterion, passed in criteria.items():
            status = "✓" if passed else "✗"
            logger.info(f"  {status} {criterion}")
            if not passed:
                all_passed = False

        return all_passed


def main():
    logger.info("="*70)
    logger.info("M2 KAGGLE PLATE DETECTION - COMPLETE EVALUATION")
    logger.info("="*70)

    evaluator = M2KaggleEvaluation()

    if not evaluator.load_model():
        logger.error("Failed to load model")
        return

    results = {
        "model": str(evaluator.model_path),
        "dataset": "Kaggle Number Plate Detection",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "image_count": 436,
        "splits": {"train": 230, "val": 103, "test": 103},
    }

    # Validation
    val_metrics = evaluator.validate()
    results.update(val_metrics)

    # Test
    test_metrics = evaluator.test()
    results.update(test_metrics)

    # Latency benchmark
    latency_metrics = evaluator.benchmark_latency(num_iterations=100)
    results.update(latency_metrics)

    # Export
    exports = evaluator.export_model()
    results["exports"] = exports

    # Acceptance check
    all_passed = evaluator.check_acceptance_criteria(results)
    results["m2_acceptance_passed"] = all_passed

    # Save results
    output_file = Path("eval_m2_kaggle_results.json")
    output_file.write_text(json.dumps(results, indent=2))
    logger.info(f"\n✓ Results saved to {output_file}")

    if all_passed:
        logger.info("\n✓✓✓ M2 ACCEPTANCE PASSED - Ready for M3/M4 integration")
    else:
        logger.warning("\n✗ M2 Acceptance criteria not fully met")


if __name__ == "__main__":
    main()
