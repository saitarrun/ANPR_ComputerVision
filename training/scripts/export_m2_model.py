#!/usr/bin/env python
"""
Export M2 trained model to ONNX and TFLite formats.
"""

import logging
import sys
from pathlib import Path

from ultralytics import YOLO

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def export_model(model_path: str, output_dir: str = "models") -> bool:
    """Export model to multiple formats."""
    model_path_obj = Path(model_path)
    if not model_path_obj.exists():
        logger.error(f"Model not found: {model_path_obj}")
        return False

    output_dir_obj = Path(output_dir)
    output_dir_obj.mkdir(parents=True, exist_ok=True)

    logger.info(f"Loading model: {model_path_obj}")
    model = YOLO(str(model_path_obj))

    logger.info(f"\nExporting to {output_dir_obj}...")

    exports = {}
    for fmt in ["onnx", "tflite"]:
        try:
            logger.info(f"  Exporting {fmt.upper()}...")
            export_path = model.export(format=fmt, imgsz=640)
            exports[fmt] = str(export_path)
            logger.info(f"    ✓ {fmt}: {export_path}")
        except Exception as e:
            logger.warning(f"    ✗ {fmt} export failed: {e}")

    logger.info("\n✓ Export complete")
    return len(exports) > 0

if __name__ == "__main__":
    model_path = "runs/detect/kaggle-plate-detection/weights/best.pt"
    success = export_model(model_path)
    sys.exit(0 if success else 1)
