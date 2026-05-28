#!/usr/bin/env python
"""
Batch training script for efficient multi-dataset training.
Processes multiple datasets in parallel using concurrent training runs.

Usage:
    python training/scripts/batch_train.py --datasets kaggle ccpd synthetic
"""

import argparse
import logging
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

DATASET_CONFIGS = {
    "kaggle": {
        "yaml": "/Users/saitarrunpitta/.cache/anpr-datasets/dataset.yaml",
        "epochs": 20,
        "batch": 16,
        "name": "kaggle-plate-detection",
    },
    "ccpd": {
        "yaml": "~/.cache/anpr-datasets/ccpd/dataset.yaml",
        "epochs": 100,
        "batch": 32,
        "name": "ccpd-detector",
    },
    "synthetic": {
        "yaml": "data/synthetic-dataset/dataset.yaml",
        "epochs": 50,
        "batch": 16,
        "name": "synthetic-detector",
    },
}


def train_single_dataset(dataset_name: str, config: dict[str, str | int]) -> dict[str, str]:
    """Train on a single dataset."""
    logger.info(f"\n{'='*70}")
    logger.info(f"Training on {dataset_name.upper()}")
    logger.info(f"  YAML: {config['yaml']}")
    logger.info(f"  Epochs: {config['epochs']}, Batch: {config['batch']}")
    logger.info(f"{'='*70}")

    cmd = [
        "python3", "-c",
        f"""
from ultralytics import YOLO
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

yaml_path = Path("{config['yaml']}").expanduser()
if not yaml_path.exists():
    raise FileNotFoundError(f"Dataset not found: {{yaml_path}}")

model = YOLO("yolov8s.pt")
results = model.train(
    data=str(yaml_path),
    epochs={config['epochs']},
    imgsz=640,
    batch={config['batch']},
    device="cpu",
    patience=5,
    save=True,
    project="runs/detect",
    name="{config['name']}",
    verbose=False,
)

logger.info(f"✓ Training complete for {dataset_name}")
"""
    ]

    try:
        # ruff: noqa: S603 - cmd is hardcoded, not untrusted input
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=7200, check=False)
        if result.returncode == 0:
            logger.info(f"✓ {dataset_name.upper()} training passed")
            return {"dataset": dataset_name, "status": "success"}
        logger.error(f"✗ {dataset_name.upper()} training failed")
        logger.error(result.stderr)
        return {"dataset": dataset_name, "status": "failed"}
    except subprocess.TimeoutExpired:
        logger.error(f"✗ {dataset_name.upper()} training timed out (>2h)")
        return {"dataset": dataset_name, "status": "timeout"}
    except Exception as e:
        logger.error(f"✗ {dataset_name.upper()} training error: {e}")
        return {"dataset": dataset_name, "status": "error"}


def main(datasets: list[str], max_workers: int = 2) -> None:
    """Train multiple datasets in parallel."""
    logger.info(f"\nBatch training {len(datasets)} dataset(s) with {max_workers} workers")

    results: dict[str, dict[str, str]] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(train_single_dataset, ds, DATASET_CONFIGS[ds]): ds
            for ds in datasets
            if ds in DATASET_CONFIGS
        }

        for future in as_completed(futures):
            dataset = futures[future]
            try:
                result = future.result()
                results[dataset] = result
            except Exception as e:
                logger.error(f"Batch training error for {dataset}: {e}")
                results[dataset] = {"status": "exception", "error": str(e)}

    logger.info(f"\n{'='*70}")
    logger.info("BATCH TRAINING RESULTS")
    logger.info(f"{'='*70}")
    for ds, result in results.items():
        status_icon = "✓" if result["status"] == "success" else "✗"
        logger.info(f"  {status_icon} {ds}: {result['status']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Batch train multiple datasets")
    parser.add_argument("--datasets", nargs="+", default=["kaggle"], help="Datasets to train")
    parser.add_argument("--workers", type=int, default=2, help="Max parallel workers")
    args = parser.parse_args()

    main(args.datasets, max_workers=args.workers)
