#!/usr/bin/env python
"""
Benchmark inference latency for trained YOLOv8 detector.

Measures p50, p95, p99 latency on a representative batch of images.

Usage:
    python training/scripts/benchmark_latency.py --model runs/detect/anpr/detector-ccpd-2/weights/best.pt
    python training/scripts/benchmark_latency.py --model models/detector_prod.pt --num-runs 100
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path

import numpy as np
from ultralytics import YOLO

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")


def load_test_images(dataset_path: Path, num_images: int = 50) -> list[str]:
    """Load test image paths from dataset."""
    test_dir = dataset_path / "images" / "test"
    if not test_dir.exists():
        raise FileNotFoundError(f"Test directory not found: {test_dir}")

    images = list(test_dir.glob("*.jpg")) + list(test_dir.glob("*.png"))
    if len(images) < num_images:
        logger.warning(f"Only {len(images)} images found, using all available")
        return [str(img) for img in images]

    return [str(img) for img in images[:num_images]]


def benchmark_latency(
    model_path: str,
    test_images: list[str],
    warmup_runs: int = 5,
    num_runs: int = 100,
    imgsz: int = 640,
) -> dict[str, float]:
    """Benchmark inference latency."""
    logger.info("\n" + "=" * 70)
    logger.info("LATENCY BENCHMARKING")
    logger.info("=" * 70)

    model = YOLO(model_path)
    logger.info(f"Model loaded: {model_path}")
    logger.info(f"Image size: {imgsz}x{imgsz}")
    logger.info(f"Test images: {len(test_images)}")

    # Warmup
    logger.info(f"\nWarmup: {warmup_runs} runs...")
    for i in range(warmup_runs):
        _ = model.predict(test_images[i % len(test_images)], imgsz=imgsz, verbose=False)

    # Benchmark
    logger.info(f"Benchmark: {num_runs} runs...")
    latencies: list[float] = []

    for i in range(num_runs):
        img_path = test_images[i % len(test_images)]
        start = time.perf_counter()
        _ = model.predict(img_path, imgsz=imgsz, verbose=False)
        elapsed = (time.perf_counter() - start) * 1000  # ms
        latencies.append(elapsed)

        if (i + 1) % 20 == 0:
            logger.info(f"  {i+1}/{num_runs} runs completed")

    latencies_array = np.array(latencies)

    metrics = {
        "p50": float(np.percentile(latencies_array, 50)),
        "p75": float(np.percentile(latencies_array, 75)),
        "p95": float(np.percentile(latencies_array, 95)),
        "p99": float(np.percentile(latencies_array, 99)),
        "mean": float(np.mean(latencies_array)),
        "std": float(np.std(latencies_array)),
        "min": float(np.min(latencies_array)),
        "max": float(np.max(latencies_array)),
    }

    logger.info("\nLatency Metrics (ms):")
    logger.info(f"  p50:  {metrics['p50']:.2f}")
    logger.info(f"  p75:  {metrics['p75']:.2f}")
    logger.info(f"  p95:  {metrics['p95']:.2f}")
    logger.info(f"  p99:  {metrics['p99']:.2f}")
    logger.info(f"  mean: {metrics['mean']:.2f}")
    logger.info(f"  std:  {metrics['std']:.2f}")
    logger.info(f"  min:  {metrics['min']:.2f}")
    logger.info(f"  max:  {metrics['max']:.2f}")

    return metrics


def main(
    model_path: str,
    dataset_path: str = "~/.cache/anpr-datasets",
    warmup_runs: int = 5,
    num_runs: int = 100,
    imgsz: int = 640,
) -> None:
    dataset_path_obj = Path(dataset_path).expanduser()

    if not dataset_path_obj.exists():
        raise FileNotFoundError(f"Dataset path not found: {dataset_path_obj}")

    test_images = load_test_images(dataset_path_obj)

    metrics = benchmark_latency(
        model_path=model_path,
        test_images=test_images,
        warmup_runs=warmup_runs,
        num_runs=num_runs,
        imgsz=imgsz,
    )

    # Save results
    results_file = Path("benchmark_latency_m2.json")
    results_file.write_text(json.dumps(metrics, indent=2))
    logger.info(f"\n✓ Results saved to {results_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Benchmark M2 detector latency")
    parser.add_argument("--model", required=True, help="Path to model weights")
    parser.add_argument("--dataset", default="~/.cache/anpr-datasets", help="Dataset path")
    parser.add_argument("--warmup-runs", type=int, default=5, help="Warmup runs")
    parser.add_argument("--num-runs", type=int, default=100, help="Benchmark runs")
    parser.add_argument("--imgsz", type=int, default=640, help="Input image size")
    args = parser.parse_args()

    main(
        model_path=args.model,
        dataset_path=args.dataset,
        warmup_runs=args.warmup_runs,
        num_runs=args.num_runs,
        imgsz=args.imgsz,
    )
