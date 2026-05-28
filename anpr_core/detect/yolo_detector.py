"""YOLOv8 license plate detector wrapper.

M2 Production Detector (2026-05-27):
- Model: YOLOv8s fine-tuned on synthetic license plates
- Status: ✓ Exported to ONNX + PyTorch formats
- Baseline Performance: mAP@0.5=0.586 (synthetic), p95=154ms (CPU)
- Next: Fine-tune on CCPD (250K images) to reach mAP@0.5≥0.92 gate

Usage in pipeline:
    detector = YOLODetector(model_path="models/detector_prod.pt")
    detections = detector.detect(frame)  # Returns list[Detection]
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from ultralytics import YOLO

logger = logging.getLogger(__name__)


@dataclass
class Detection:
    """Single detection result."""

    x1: float
    y1: float
    x2: float
    y2: float
    conf: float
    class_id: int
    class_name: str

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        return (self.x1, self.y1, self.x2, self.y2)

    @property
    def width(self) -> float:
        return self.x2 - self.x1

    @property
    def height(self) -> float:
        return self.y2 - self.y1


def _resolve_device() -> str:
    """Resolve device: mps (Apple M-series) → cuda (NVIDIA) → cpu."""
    try:
        import torch
        if torch.backends.mps.is_available():
            return "mps"
        elif torch.cuda.is_available():
            return "cuda:0"
    except Exception:
        pass
    return "cpu"


class YOLODetector:
    """Wrapper around YOLO for license plate detection.

    Loads production-ready detector from models/ directory.
    Falls back to general YOLOv8s if production model not found.
    """

    # Production model paths (priority order)
    PRODUCTION_MODELS = [
        Path(__file__).parent.parent.parent / "models" / "detector_prod.pt",  # M2 fine-tuned
        Path(__file__).parent.parent.parent / "models" / "detector_prod.onnx",  # ONNX export
    ]

    def __init__(
        self,
        model_path: str | None = None,
        device: str = "auto",
        conf: float = 0.25,
        imgsz: int = 640,
    ) -> None:
        """
        Args:
            model_path: Path to model. If None, auto-loads from PRODUCTION_MODELS or falls back to yolov8s.
            device: auto | cpu | cuda:0 | mps
            conf: Confidence threshold for detections
            imgsz: Input image size for model
        """
        self.conf = conf
        self.imgsz = imgsz

        # Resolve model path
        if model_path is None:
            model_path = self._find_production_model()
        else:
            model_path = Path(model_path)

        self.model_name = str(model_path)

        # Auto-detect device if needed
        if device == "auto":
            device = _resolve_device()

        logger.info(f"Loading detector from {model_path} on device {device}")
        self.model = YOLO(str(model_path))
        self.model.to(device)
        logger.info(f"✓ Detector ready: {Path(self.model_name).name}")

    @staticmethod
    def _find_production_model() -> str:
        """Find production model, fall back to general YOLO if not found."""
        for path in YOLODetector.PRODUCTION_MODELS:
            if path.exists():
                logger.info(f"Found production model: {path}")
                return str(path)

        logger.warning(
            "No production model found. Using general YOLOv8s "
            "(expect 0 detections on license plates)"
        )
        return "yolov8s.pt"

    def detect(self, image: np.ndarray) -> list[Detection]:
        """Detect license plates in image.

        Args:
            image: BGR numpy array (H, W, 3)

        Returns:
            List of Detection objects with bbox, confidence, class info
        """
        results = self.model(image, conf=self.conf, imgsz=self.imgsz, verbose=False)

        detections = []
        for result in results:
            if result.boxes is None:
                continue
            for box in result.boxes:
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                conf = float(box.conf[0].cpu().numpy())
                class_id = int(box.cls[0].cpu().numpy())
                class_name = result.names.get(class_id, f"class-{class_id}")

                detections.append(
                    Detection(
                        x1=float(x1),
                        y1=float(y1),
                        x2=float(x2),
                        y2=float(y2),
                        conf=conf,
                        class_id=class_id,
                        class_name=class_name,
                    )
                )

        return detections
