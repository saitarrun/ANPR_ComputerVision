"""
CCPD dataset loader: parse filenames, convert to YOLO format.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class PlateAnnotation:
    """Parsed CCPD annotation."""
    image_path: str
    x1: int
    y1: int
    x2: int
    y2: int
    plate_num: str
    tilt: int
    blur: int
    brightness: int
    vehicle_type: int
    chars: str


def parse_ccpd_filename(image_path: Path) -> Optional[PlateAnnotation]:
    """Parse CCPD filename format: 02-95_113-154&383_386&473..."""
    try:
        stem = image_path.stem
        parts = stem.split("-")

        if len(parts) < 4:
            return None

        bbox_part = parts[2]
        bbox_coords = bbox_part.split("_")
        if len(bbox_coords) < 2:
            return None

        x1_y1 = bbox_coords[0].split("&")
        x2_y2 = bbox_coords[1].split("&")

        x1, y1 = int(x1_y1[0]), int(x1_y1[1])
        x2, y2 = int(x2_y2[0]), int(x2_y2[1])

        plate_num = parts[1]

        attr_part = parts[-1]
        attrs = attr_part.split("_")
        tilt = int(attrs[0]) if len(attrs) > 0 else 0
        blur = int(attrs[1]) if len(attrs) > 1 else 0
        brightness = int(attrs[2]) if len(attrs) > 2 else 0
        vehicle_type = int(attrs[3]) if len(attrs) > 3 else 0

        return PlateAnnotation(
            image_path=str(image_path),
            x1=x1, y1=y1, x2=x2, y2=y2,
            plate_num=plate_num,
            tilt=tilt, blur=blur, brightness=brightness, vehicle_type=vehicle_type,
            chars=plate_num,
        )

    except (ValueError, IndexError) as e:
        logger.warning(f"Failed to parse {image_path.name}: {e}")
        return None


class CCPDLoader:
    def __init__(self, ccpd_root: Path):
        self.ccpd_root = Path(ccpd_root)
        if not self.ccpd_root.exists():
            raise FileNotFoundError(f"CCPD root not found: {ccpd_root}")
        logger.info(f"CCPD root: {self.ccpd_root}")

    def get_all_images(self) -> list[Path]:
        images = []
        for subset in ["ccpd_base", "ccpd_challenge", "ccpd_weather", "ccpd_night"]:
            subset_path = self.ccpd_root / subset
            if subset_path.exists():
                subset_images = list(subset_path.glob("*.jpg")) + list(subset_path.glob("*.png"))
                logger.info(f"  {subset}: {len(subset_images)} images")
                images.extend(subset_images)
        logger.info(f"Total CCPD images: {len(images)}")
        return images

    def load_annotations(self) -> list[PlateAnnotation]:
        images = self.get_all_images()
        annotations = []
        for i, image_path in enumerate(images):
            annotation = parse_ccpd_filename(image_path)
            if annotation:
                annotations.append(annotation)
            if (i + 1) % 10000 == 0:
                logger.info(f"  Parsed {i+1}/{len(images)}")
        logger.info(f"Successfully parsed {len(annotations)} annotations")
        return annotations

    def to_yolo_format(self, annotation: PlateAnnotation, image_width: int, image_height: int) -> tuple:
        width = annotation.x2 - annotation.x1
        height = annotation.y2 - annotation.y1
        aspect_ratio = width / height if height > 0 else 0
        class_id = 1 if aspect_ratio > 2.0 else 0

        center_x = (annotation.x1 + annotation.x2) / 2 / image_width
        center_y = (annotation.y1 + annotation.y2) / 2 / image_height
        norm_width = width / image_width
        norm_height = height / image_height

        return class_id, center_x, center_y, norm_width, norm_height

    def save_yolo_split(self, annotations: list[PlateAnnotation], output_root: Path, train_ratio: float = 0.6, val_ratio: float = 0.2, test_ratio: float = 0.2) -> None:
        output_root = Path(output_root)
        output_root.mkdir(parents=True, exist_ok=True)

        for split in ["train", "val", "test"]:
            (output_root / "images" / split).mkdir(parents=True, exist_ok=True)
            (output_root / "labels" / split).mkdir(parents=True, exist_ok=True)

        np.random.seed(42)
        indices = np.arange(len(annotations))
        np.random.shuffle(indices)

        train_end = int(len(annotations) * train_ratio)
        val_end = train_end + int(len(annotations) * val_ratio)

        train_indices = set(indices[:train_end])
        val_indices = set(indices[train_end:val_end])
        test_indices = set(indices[val_end:])

        logger.info(f"Saving to {output_root}: train={len(train_indices)}, val={len(val_indices)}, test={len(test_indices)}")

        splits = {"train": train_indices, "val": val_indices, "test": test_indices}

        saved_count = 0
        for idx, annotation in enumerate(annotations):
            split = None
            for split_name, split_set in splits.items():
                if idx in split_set:
                    split = split_name
                    break

            if not split:
                continue

            image_path = Path(annotation.image_path)
            label_path = output_root / "labels" / split / image_path.stem
            label_path = label_path.with_suffix(".txt")

            try:
                import cv2
                img = cv2.imread(annotation.image_path)
                if img is None:
                    logger.warning(f"Failed to load {annotation.image_path}")
                    continue
                h, w = img.shape[:2]
            except Exception as e:
                logger.warning(f"Error loading {annotation.image_path}: {e}")
                continue

            class_id, cx, cy, bw, bh = self.to_yolo_format(annotation, w, h)
            label_path.write_text(f"{class_id} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}\n")

            output_image_path = output_root / "images" / split / image_path.name
            if not output_image_path.exists():
                try:
                    output_image_path.hardlink_to(image_path)
                except (OSError, NotImplementedError):
                    import shutil
                    shutil.copy(image_path, output_image_path)

            saved_count += 1
            if saved_count % 5000 == 0:
                logger.info(f"  Saved {saved_count}/{len(annotations)}")

        logger.info(f"✓ Saved {saved_count} images + labels")
