"""YOLOv8 plate detector wrapper."""

from __future__ import annotations

import logging
from dataclasses import dataclass

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


class YOLODetector:
    """Wrapper around YOLO for plate detection."""

    def __init__(
        self,
        model: str = "yolov8s.pt",
        device: str = "auto",
        conf: float = 0.25,
        imgsz: int = 640,
    ) -> None:
        """
        Args:
            model: Model name or path (e.g., yolov8s.pt)
            device: auto | cpu | cuda:0 | mps
            conf: Confidence threshold
            imgsz: Input image size
        """
        self.model_name = model
        self.conf = conf
        self.imgsz = imgsz

        logger.info(f"Loading YOLOv8 {model} on device {device}")
        self.model = YOLO(model)
        self.model.to(device)
        logger.info(f"Model loaded: {model}")

    def detect(self, image: np.ndarray) -> list[Detection]:
        """Detect plates in image.

        Args:
            image: BGR numpy array (H, W, 3)

        Returns:
            List of Detection objects
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
