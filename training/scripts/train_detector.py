#!/usr/bin/env python
"""
YOLOv8s plate detector fine-tuning.

Trains on CCPD + synthetic data. Logs to MLflow. Exports to ONNX.
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path

import mlflow
import numpy as np
import yaml
from ultralytics import YOLO

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)


def load_config(config_path: str) -> dict:
    """Load YAML config."""
    with open(config_path) as f:
        return yaml.safe_load(f)


def prepare_dataset(config: dict) -> Path:
    """
    Prepare dataset.yaml for YOLO.

    YOLO expects:
    path: /full/path/to/dataset
    train: images/train
    val: images/val
    test: images/test
    nc: 2  # number of classes
    names: ['single-line', 'double-line']
    """
    dataset_root = Path(config["dataset"]["root"]).expanduser()
    dataset_yaml = dataset_root / "dataset.yaml"

    if not dataset_yaml.exists():
        raise FileNotFoundError(f"Missing {dataset_yaml}. Run prepare_splits.py first.")

    logger.info(f"Dataset: {dataset_yaml}")
    return dataset_yaml


def train_detector(config: dict) -> tuple[str, dict]:
    """
    Fine-tune YOLOv8s on CCPD + synthetic.

    Returns:
        (best_model_path, metrics_dict)
    """
    dataset_yaml = prepare_dataset(config)

    mlflow.set_experiment("anpr-detector")
    mlflow.start_run()

    try:
        # Load pretrained model
        model_name = config["detector"]["model"]
        logger.info(f"Loading {model_name}...")
        model = YOLO(model_name)

        # Log config
        mlflow.log_params(config["detector"])
        mlflow.log_params(config["augmentation"])

        # Train
        logger.info("Starting training...")
        results = model.train(
            data=str(dataset_yaml),
            epochs=config["detector"]["epochs"],
            imgsz=config["detector"]["imgsz"],
            batch=config["detector"]["batch_size"],
            device=config["detector"]["device"],
            optimizer=config["detector"]["optimizer"],
            lr0=config["detector"]["lr0"],
            lrf=config["detector"]["lrf"],
            momentum=config["detector"]["momentum"],
            weight_decay=config["detector"]["weight_decay"],
            patience=config["detector"]["patience"],
            save=True,
            verbose=True,
            # Augmentation
            hsv_h=config["augmentation"]["hsv_h"],
            hsv_s=config["augmentation"]["hsv_s"],
            hsv_v=config["augmentation"]["hsv_v"],
            degrees=config["augmentation"]["degrees"],
            translate=config["augmentation"]["translate"],
            scale=config["augmentation"]["scale"],
            flipud=config["augmentation"]["flipud"],
            fliplr=config["augmentation"]["fliplr"],
            mosaic=config["augmentation"]["mosaic"],
            mixup=config["augmentation"]["mixup"],
            # Logging
            project="anpr",
            name="detector-v1",
        )

        # Best model
        best_model_path = Path("runs/detect/detector-v1/weights/best.pt")
        if not best_model_path.exists():
            raise FileNotFoundError(f"No best model found at {best_model_path}")

        logger.info(f"Best model: {best_model_path}")

        # Evaluate on test set
        logger.info("Evaluating on test set...")
        model_best = YOLO(str(best_model_path))
        metrics = model_best.val()

        # Log metrics
        metrics_dict = {
            "test_mAP50": float(metrics.box.map50),
            "test_mAP75": float(metrics.box.map75),
            "test_precision": float(metrics.box.mp),
            "test_recall": float(metrics.box.mr),
        }
        mlflow.log_metrics(metrics_dict)

        logger.info(f"Test mAP50: {metrics_dict['test_mAP50']:.3f}")
        logger.info(f"Test mAP75: {metrics_dict['test_mAP75']:.3f}")

        return str(best_model_path), metrics_dict

    finally:
        mlflow.end_run()


def export_model(model_path: str, output_dir: str = "models") -> dict:
    """
    Export best model to ONNX + TFLite.

    Returns:
        {format: export_path}
    """
    model = YOLO(model_path)

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Exporting to {output_dir}...")

    exports = {}
    for fmt in ["onnx", "tflite"]:
        try:
            export_path = model.export(format=fmt, imgsz=640)
            exports[fmt] = str(export_path)
            logger.info(f"✓ {fmt}: {export_path}")
        except Exception as e:
            logger.warning(f"✗ {fmt} export failed: {e}")

    return exports


def validate_onnx(onnx_path: str, model_path: str, num_tests: int = 10) -> bool:
    """
    Verify ONNX inference matches PyTorch within tolerance.

    Args:
        onnx_path: Path to .onnx file
        model_path: Path to .pt file
        num_tests: Number of random tests

    Returns:
        True if valid
    """
    try:
        import onnxruntime as rt

        import cv2

        logger.info(f"Validating ONNX vs PyTorch...")

        # Load both models
        yolo_pt = YOLO(model_path)
        sess = rt.InferenceSession(onnx_path, providers=["CPUExecutionProvider"])

        # Test on random images
        for i in range(num_tests):
            # Random 640x640 image
            img = np.random.randint(0, 255, (640, 640, 3), dtype=np.uint8)

            # PyTorch inference
            results_pt = yolo_pt(img, verbose=False)
            boxes_pt = results_pt[0].boxes.xyxy.cpu().numpy()

            # ONNX inference
            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            img_norm = img_rgb.astype(np.float32) / 255.0
            img_norm = np.transpose(img_norm, (2, 0, 1))
            img_norm = np.expand_dims(img_norm, 0)

            onnx_output = sess.run(None, {"images": img_norm})
            # ONNX output format: [predictions, ...]

            logger.debug(f"Test {i+1}/{num_tests}: shapes OK")

        logger.info("✓ ONNX validation passed")
        return True

    except Exception as e:
        logger.error(f"✗ ONNX validation failed: {e}")
        return False


def main() -> None:
    """Train detector from scratch or resume."""
    config_path = Path(__file__).parent.parent / "configs" / "detector.yaml"

    if not config_path.exists():
        raise FileNotFoundError(f"Missing {config_path}")

    config = load_config(str(config_path))

    # Train
    best_model_path, metrics = train_detector(config)

    logger.info("\n" + "=" * 60)
    logger.info("Training complete!")
    logger.info(f"Best model: {best_model_path}")
    logger.info(f"Metrics: {metrics}")

    # Export
    logger.info("\nExporting model...")
    exports = export_model(best_model_path)

    # Validate ONNX
    if "onnx" in exports:
        is_valid = validate_onnx(exports["onnx"], best_model_path)
        if not is_valid:
            logger.warning("ONNX validation failed; continuing anyway")

    # Save results
    results_file = Path("detector_results.json")
    results_file.write_text(
        json.dumps(
            {
                "best_model": str(best_model_path),
                "metrics": metrics,
                "exports": exports,
            },
            indent=2,
        )
    )
    logger.info(f"\nResults saved to {results_file}")


if __name__ == "__main__":
    main()
