#!/usr/bin/env python
"""
M2: YOLOv8s Detector Fine-Tuning (5 days).

Trains on CCPD + synthetic data.
- Phase 1: Baseline (10 epochs on CCPD only)
- Phase 2: Full training (100 epochs with augmentation)

Usage:
    python training/scripts/train_detector_m2.py --phase baseline
    python training/scripts/train_detector_m2.py --phase full
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import mlflow
import yaml
from ultralytics import YOLO

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")


def load_config(config_path: str) -> dict:
    with open(config_path) as f:
        return yaml.safe_load(f)


def prepare_dataset(config: dict) -> Path:
    dataset_root = Path(config["dataset"]["root"]).expanduser()
    dataset_yaml = dataset_root / "dataset.yaml"
    if not dataset_yaml.exists():
        raise FileNotFoundError(f"Missing {dataset_yaml}")
    logger.info(f"Dataset: {dataset_yaml}")
    return dataset_yaml


def baseline_training(model: YOLO, dataset_yaml: Path, config: dict) -> tuple[str, dict]:
    logger.info("\n" + "=" * 70)
    logger.info("BASELINE TRAINING (Phase 1: 10 epochs)")
    logger.info("=" * 70)

    mlflow.set_tag("phase", "baseline")

    results = model.train(
        data=str(dataset_yaml),
        epochs=10,
        imgsz=config["detector"]["imgsz"],
        batch=config["detector"]["batch_size"],
        device=config["detector"]["device"],
        patience=5,
        save=True,
        project="anpr",
        name="detector-baseline",
    )

    baseline_model_path = Path("runs/detect/detector-baseline/weights/best.pt")
    if not baseline_model_path.exists():
        raise FileNotFoundError(f"No baseline model found")

    logger.info(f"✓ Baseline model: {baseline_model_path}")

    model_baseline = YOLO(str(baseline_model_path))
    metrics_baseline = model_baseline.val()

    baseline_metrics = {
        "baseline_mAP50": float(metrics_baseline.box.map50),
        "baseline_mAP75": float(metrics_baseline.box.map75),
    }

    logger.info(f"  mAP@0.5: {baseline_metrics['baseline_mAP50']:.4f}")
    mlflow.log_metrics(baseline_metrics)

    return str(baseline_model_path), baseline_metrics


def full_training(model: YOLO, dataset_yaml: Path, config: dict, baseline_metrics: dict) -> tuple[str, dict]:
    logger.info("\n" + "=" * 70)
    logger.info("FULL TRAINING (Phase 2: 100 epochs with augmentation)")
    logger.info("=" * 70)

    mlflow.set_tag("phase", "full")

    results = model.train(
        data=str(dataset_yaml),
        epochs=config["detector"]["epochs"],
        imgsz=config["detector"]["imgsz"],
        batch=config["detector"]["batch_size"],
        device=config["detector"]["device"],
        patience=config["detector"]["patience"],
        save=True,
        **{k: v for k, v in config["augmentation"].items()},
        project="anpr",
        name="detector-v1",
    )

    best_model_path = Path("runs/detect/detector-v1/weights/best.pt")
    if not best_model_path.exists():
        raise FileNotFoundError(f"No best model found")

    logger.info(f"✓ Best model: {best_model_path}")

    model_best = YOLO(str(best_model_path))
    metrics = model_best.val()

    metrics_dict = {
        "test_mAP50": float(metrics.box.map50),
        "test_mAP75": float(metrics.box.map75),
    }

    logger.info(f"  mAP@0.5: {metrics_dict['test_mAP50']:.4f}")
    logger.info(f"  Improvement: +{(metrics_dict['test_mAP50'] - baseline_metrics.get('baseline_mAP50', 0)):.4f}")

    mlflow.log_metrics(metrics_dict)

    return str(best_model_path), metrics_dict


def export_model(model_path: str, output_dir: str = "models") -> dict:
    model = YOLO(model_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"\nExporting to {output_dir}...")

    exports = {}
    for fmt in ["onnx", "tflite"]:
        try:
            export_path = model.export(format=fmt, imgsz=640)
            exports[fmt] = str(export_path)
            logger.info(f"  ✓ {fmt}: {export_path}")
        except Exception as e:
            logger.warning(f"  ✗ {fmt} export failed: {e}")

    return exports


def main(phase: str = "full", config_path: str | None = None) -> None:
    if config_path is None:
        config_path = str(Path(__file__).parent.parent / "configs" / "detector.yaml")

    config = load_config(config_path)
    dataset_yaml = prepare_dataset(config)

    mlflow.set_experiment("anpr-detector-m2")
    mlflow.start_run()

    try:
        model_name = config["detector"]["model"]
        logger.info(f"Loading {model_name}...")
        model = YOLO(model_name)

        baseline_metrics = {}
        best_model_path = None
        full_metrics = {}

        if phase in ["baseline", "all"]:
            baseline_model_path, baseline_metrics = baseline_training(model, dataset_yaml, config)

        if phase in ["full", "all"]:
            model = YOLO(config["detector"]["model"])
            best_model_path, full_metrics = full_training(model, dataset_yaml, config, baseline_metrics)

            exports = export_model(best_model_path)
            full_metrics["exports"] = exports

            if full_metrics.get("test_mAP50", 0) >= 0.92:
                logger.info("\n✓ mAP@0.5 ≥ 0.92 (acceptance criteria MET)")
                mlflow.log_metric("m2_acceptance", 1.0)
            else:
                logger.warning("\n✗ mAP@0.5 < 0.92 (below target)")
                mlflow.log_metric("m2_acceptance", 0.0)

            results_file = Path("detector_results_m2.json")
            results_file.write_text(json.dumps({"best_model": str(best_model_path), "baseline_metrics": baseline_metrics, "full_metrics": full_metrics, "exports": exports}, indent=2))
            logger.info(f"\n✓ Results saved to {results_file}")

    finally:
        mlflow.end_run()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="M2: YOLOv8s detector fine-tuning")
    parser.add_argument("--phase", choices=["baseline", "full", "all"], default="full")
    parser.add_argument("--config", help="Config YAML path")
    args = parser.parse_args()
    main(phase=args.phase, config_path=args.config)
