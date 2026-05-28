#!/usr/bin/env python
"""
Latency benchmark for M2 Kaggle detector.
Measures p50/p95/p99 inference latency on CPU.
"""

import logging
import time
from pathlib import Path

import numpy as np
from ultralytics import YOLO

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def benchmark_model(model_path: str, num_iterations: int = 100, imgsz: tuple[int, int] = (640, 480)) -> dict[str, float]:
    """Benchmark model latency."""
    logger.info(f"Loading model: {model_path}")
    model = YOLO(model_path)

    logger.info("Warming up (5 iterations)...")
    for _ in range(5):
        img = np.random.randint(0, 255, (*imgsz, 3), dtype=np.uint8)
        _ = model(img, verbose=False)

    logger.info(f"Benchmarking latency ({num_iterations} iterations)...")
    latencies: list[float] = []

    for i in range(num_iterations):
        img = np.random.randint(0, 255, (*imgsz, 3), dtype=np.uint8)
        t_start = time.perf_counter()
        _ = model(img, verbose=False)
        t_end = time.perf_counter()
        latency_ms = (t_end - t_start) * 1000
        latencies.append(latency_ms)

        if (i + 1) % 25 == 0:
            logger.info(f"  {i+1}/{num_iterations} iterations...")

    latencies_array = np.array(latencies)

    metrics = {
        "p50_ms": float(np.percentile(latencies_array, 50)),
        "p95_ms": float(np.percentile(latencies_array, 95)),
        "p99_ms": float(np.percentile(latencies_array, 99)),
        "mean_ms": float(np.mean(latencies_array)),
        "std_ms": float(np.std(latencies_array)),
    }

    logger.info("\nLatency Results (CPU):")
    logger.info(f"  p50: {metrics['p50_ms']:.1f}ms")
    logger.info(f"  p95: {metrics['p95_ms']:.1f}ms")
    logger.info(f"  p99: {metrics['p99_ms']:.1f}ms")
    logger.info(f"  mean: {metrics['mean_ms']:.1f}ms (±{metrics['std_ms']:.1f}ms)")

    return metrics

if __name__ == "__main__":
    model_path = "runs/detect/kaggle-plate-detection/weights/best.pt"
    if Path(model_path).exists():
        metrics = benchmark_model(model_path, num_iterations=100)
    else:
        logger.error(f"Model not found: {model_path}")
