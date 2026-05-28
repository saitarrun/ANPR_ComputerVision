#!/usr/bin/env python
"""
Create extended dataset for M2 training.

This script supports two modes:
1. Synthetic-extended (for validation): duplicates golden sets → synthetic train/val/test
2. CCPD-integrated (production): loads real CCPD + merges with synthetic data

For M2 production, use CCPD. For testing the pipeline, use synthetic-extended.

Usage:
    # Synthetic (validation):
    python training/data/create_extended_dataset.py --mode synthetic

    # CCPD (production, requires manual download):
    python training/data/create_extended_dataset.py --mode ccpd --ccpd-root ~/.cache/anpr-datasets/ccpd/CCPD2019
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
from pathlib import Path
from typing import Optional

import numpy as np
import yaml

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)


class SyntheticDatasetBuilder:
    """Build synthetic dataset from golden sets for pipeline validation."""

    def __init__(self, output_root: Path):
        self.output_root = Path(output_root)
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.golden_root = Path("data/golden-sets")

    def build_synthetic_splits(self) -> dict[str, int]:
        """Copy golden sets → train/val/test splits for validation."""
        logger.info("=" * 60)
        logger.info("Building Synthetic Dataset")
        logger.info("=" * 60)

        if not self.golden_root.exists():
            raise FileNotFoundError(f"Golden sets not found: {self.golden_root}")

        # Create directory structure
        for split in ["train", "val", "test"]:
            (self.output_root / "images" / split).mkdir(parents=True, exist_ok=True)
            (self.output_root / "labels" / split).mkdir(parents=True, exist_ok=True)

        # Collect all golden sets
        golden_sets = [
            self.golden_root / "india_small",
            self.golden_root / "eu",
            self.golden_root / "us",
            self.golden_root / "full",
        ]

        split_counts = {split: 0 for split in ["train", "val", "test"]}
        splits = {"train": [], "val": [], "test": []}

        # Gather all images and labels
        all_images = []
        for golden_set in golden_sets:
            if not golden_set.exists():
                logger.warning(f"Golden set not found: {golden_set}")
                continue

            img_dir = golden_set / "images"
            label_dir = golden_set / "labels"

            if img_dir.exists():
                all_images.extend(list(img_dir.glob("*.jpg")) + list(img_dir.glob("*.png")))

        if not all_images:
            raise ValueError("No images found in golden sets")

        logger.info(f"Found {len(all_images)} golden set images")

        # Stratify and split
        np.random.seed(42)
        indices = np.arange(len(all_images))
        np.random.shuffle(indices)

        train_end = int(len(all_images) * 0.6)
        val_end = train_end + int(len(all_images) * 0.2)

        train_indices = set(indices[:train_end])
        val_indices = set(indices[train_end:val_end])
        test_indices = set(indices[val_end:])

        # Copy images and labels
        logger.info("Copying images and labels...")
        for idx, img_path in enumerate(all_images):
            # Determine split
            split = None
            if idx in train_indices:
                split = "train"
            elif idx in val_indices:
                split = "val"
            else:
                split = "test"

            # Find corresponding label
            label_path = None
            for golden_set in golden_sets:
                candidate = golden_set / "labels" / img_path.stem
                candidate = candidate.with_suffix(".txt")
                if candidate.exists():
                    label_path = candidate
                    break

            if not label_path or not label_path.exists():
                logger.warning(f"No label for {img_path.name}")
                continue

            # Copy image
            output_img = self.output_root / "images" / split / img_path.name
            if not output_img.exists():
                try:
                    output_img.hardlink_to(img_path)
                except (OSError, NotImplementedError):
                    shutil.copy2(img_path, output_img)

            # Copy label
            output_label = self.output_root / "labels" / split / label_path.name
            if not output_label.exists():
                shutil.copy2(label_path, output_label)

            split_counts[split] += 1
            if (idx + 1) % 50 == 0:
                logger.info(f"  Copied {idx + 1}/{len(all_images)}")

        logger.info(f"✓ Copied {sum(split_counts.values())} images")

        # Create dataset.yaml
        self._create_dataset_yaml(split_counts)

        return split_counts

    def _create_dataset_yaml(self, split_counts: dict) -> None:
        """Create dataset.yaml for YOLO."""
        yaml_content = {
            "path": str(self.output_root.absolute()),
            "train": "images/train",
            "val": "images/val",
            "test": "images/test",
            "nc": 2,
            "names": ["single-line", "double-line"],
        }

        yaml_path = self.output_root / "dataset.yaml"
        with open(yaml_path, "w") as f:
            yaml.dump(yaml_content, f, default_flow_style=False)

        logger.info(f"✓ Created {yaml_path}")
        logger.info("\nDataset summary:")
        total = sum(split_counts.values())
        for split, count in split_counts.items():
            pct = 100 * count / total if total > 0 else 0
            logger.info(f"  {split}: {count} ({pct:.0f}%)")


class CCPDDatasetBuilder:
    """Build dataset from CCPD (production)."""

    def __init__(self, ccpd_root: Path, output_root: Path):
        self.ccpd_root = Path(ccpd_root)
        self.output_root = Path(output_root)

        if not self.ccpd_root.exists():
            raise FileNotFoundError(f"CCPD not found: {ccpd_root}")

        self.output_root.mkdir(parents=True, exist_ok=True)

    def build_ccpd_splits(self) -> dict[str, int]:
        """Load CCPD, parse, and create splits."""
        logger.info("=" * 60)
        logger.info("Building CCPD Dataset")
        logger.info("=" * 60)

        # Import CCPD loader
        from ccpd_loader import CCPDLoader

        loader = CCPDLoader(self.ccpd_root)

        # Load annotations
        logger.info("\nLoading CCPD annotations...")
        annotations = loader.load_annotations()

        if not annotations:
            raise ValueError("No CCPD annotations loaded")

        # Create splits
        for split in ["train", "val", "test"]:
            (self.output_root / "images" / split).mkdir(parents=True, exist_ok=True)
            (self.output_root / "labels" / split).mkdir(parents=True, exist_ok=True)

        # Stratify and split
        logger.info(f"\nCreating splits (60/20/20)...")
        np.random.seed(42)
        indices = np.arange(len(annotations))
        np.random.shuffle(indices)

        train_end = int(len(annotations) * 0.6)
        val_end = train_end + int(len(annotations) * 0.2)

        train_indices = set(indices[:train_end])
        val_indices = set(indices[train_end:val_end])
        test_indices = set(indices[val_end:])

        splits = {
            "train": train_indices,
            "val": val_indices,
            "test": test_indices,
        }

        # Save
        logger.info("Saving images and labels...")
        split_counts = {split: 0 for split in splits}
        skipped = 0

        for idx, annotation in enumerate(annotations):
            split = None
            for split_name, split_set in splits.items():
                if idx in split_set:
                    split = split_name
                    break

            if not split:
                continue

            try:
                import cv2

                img = cv2.imread(annotation.image_path)
                if img is None:
                    skipped += 1
                    continue

                h, w = img.shape[:2]

                # Convert to YOLO
                class_id, cx, cy, bw, bh = loader.to_yolo_format(annotation, w, h)

                # Save label
                label_path = self.output_root / "labels" / split / Path(annotation.image_path).stem
                label_path = label_path.with_suffix(".txt")
                label_path.write_text(f"{class_id} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}\n")

                # Link image
                img_path = Path(annotation.image_path)
                output_img = self.output_root / "images" / split / img_path.name

                if not output_img.exists():
                    try:
                        output_img.hardlink_to(img_path)
                    except (OSError, NotImplementedError):
                        shutil.copy2(img_path, output_img)

                split_counts[split] += 1

                if (idx + 1) % 10000 == 0:
                    logger.info(f"  Processed {idx + 1}/{len(annotations)}")

            except Exception as e:
                logger.warning(f"Error processing {annotation.image_path}: {e}")
                skipped += 1
                continue

        logger.info(f"✓ Saved {sum(split_counts.values())} images (skipped {skipped})")

        # Create dataset.yaml
        self._create_dataset_yaml(split_counts)

        return split_counts

    def _create_dataset_yaml(self, split_counts: dict) -> None:
        """Create dataset.yaml."""
        yaml_content = {
            "path": str(self.output_root.absolute()),
            "train": "images/train",
            "val": "images/val",
            "test": "images/test",
            "nc": 2,
            "names": ["single-line", "double-line"],
        }

        yaml_path = self.output_root / "dataset.yaml"
        with open(yaml_path, "w") as f:
            yaml.dump(yaml_content, f, default_flow_style=False)

        logger.info(f"✓ Created {yaml_path}")
        logger.info("\nDataset summary:")
        total = sum(split_counts.values())
        for split, count in split_counts.items():
            pct = 100 * count / total if total > 0 else 0
            logger.info(f"  {split}: {count} ({pct:.0f}%)")


def main(mode: str = "synthetic", output_dir: Optional[str] = None, ccpd_root: Optional[str] = None) -> None:
    """Main entry point."""
    if output_dir is None:
        output_dir = "~/.cache/anpr-datasets/dataset"

    output_dir = Path(output_dir).expanduser()

    if mode == "synthetic":
        logger.info("MODE: Synthetic (validation/pipeline test)")
        logger.info("Note: For M2 production, use CCPD mode with real data")

        builder = SyntheticDatasetBuilder(output_dir)
        split_counts = builder.build_synthetic_splits()

    elif mode == "ccpd":
        if ccpd_root is None:
            ccpd_root = "~/.cache/anpr-datasets/ccpd/CCPD2019"

        ccpd_root = Path(ccpd_root).expanduser()
        logger.info("MODE: CCPD (production)")

        builder = CCPDDatasetBuilder(ccpd_root, output_dir)
        split_counts = builder.build_ccpd_splits()

    else:
        raise ValueError(f"Unknown mode: {mode}")

    logger.info("\n" + "=" * 60)
    logger.info("✓ Dataset preparation complete!")
    logger.info("=" * 60)
    logger.info(f"Dataset: {output_dir}")
    logger.info(f"Next: python training/scripts/train_detector_m2.py --phase full")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Prepare dataset for M2 training")
    parser.add_argument(
        "--mode",
        choices=["synthetic", "ccpd"],
        default="synthetic",
        help="Dataset mode: synthetic (validation) or ccpd (production)",
    )
    parser.add_argument(
        "--output",
        default="~/.cache/anpr-datasets/dataset",
        help="Output directory for dataset",
    )
    parser.add_argument(
        "--ccpd-root",
        default="~/.cache/anpr-datasets/ccpd/CCPD2019",
        help="CCPD root directory (for ccpd mode)",
    )
    args = parser.parse_args()

    main(mode=args.mode, output_dir=args.output, ccpd_root=args.ccpd_root)
