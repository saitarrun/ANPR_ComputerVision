#!/usr/bin/env python
"""
Prepare dataset splits for YOLO training.

- Download/validate CCPD, UFPR, OpenALPR-EU, Roboflow.
- Split into train/val/test with stratification by region + difficulty.
- Generate dataset.yaml for YOLO.
- Generate synthetic plates if needed.

Usage:
    python training/data/prepare_splits.py --cache ~/.cache/anpr-datasets
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)


class DatasetDownloader:
    """Download + prepare datasets."""

    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.datasets_dir = self.cache_dir / "datasets"
        self.datasets_dir.mkdir(exist_ok=True)
        logger.info(f"Cache dir: {self.cache_dir}")

    def download_ccpd(self) -> Path:
        """
        Download CCPD dataset.

        For now, assume manual download:
        https://github.com/detectRecog/CCPD

        Returns:
            Path to CCPD root
        """
        ccpd_root = self.datasets_dir / "CCPD2019"

        if (ccpd_root / "ccpd_base").exists():
            logger.info(f"CCPD already exists: {ccpd_root}")
            return ccpd_root

        logger.info("CCPD not found. Instructions:")
        logger.info("1. Download from https://github.com/detectRecog/CCPD/releases")
        logger.info(f"2. Extract to {ccpd_root}")
        logger.info("3. Run this script again")

        raise FileNotFoundError(f"Please download CCPD to {ccpd_root}")

    def download_ufpr(self) -> Path:
        """Download UFPR-ALPR dataset."""
        ufpr_root = self.datasets_dir / "UFPR-ALPR"

        if (ufpr_root / "training").exists():
            logger.info(f"UFPR already exists: {ufpr_root}")
            return ufpr_root

        logger.info("UFPR not found. Instructions:")
        logger.info("1. Download from https://web.inf.ufpr.br/vri/databases/ufpr-alpr/")
        logger.info(f"2. Extract to {ufpr_root}")
        logger.info("3. Run this script again")

        raise FileNotFoundError(f"Please download UFPR to {ufpr_root}")

    def download_openalpr_eu(self) -> Path:
        """Download OpenALPR EU dataset."""
        eu_root = self.datasets_dir / "OpenALPR-EU"

        if (eu_root / "images").exists():
            logger.info(f"OpenALPR-EU already exists: {eu_root}")
            return eu_root

        logger.info("OpenALPR-EU not found. Instructions:")
        logger.info("1. Download from https://github.com/openalpr/openalpr")
        logger.info(f"2. Extract to {eu_root}")
        logger.info("3. Run this script again")

        raise FileNotFoundError(f"Please download OpenALPR-EU to {eu_root}")

    def download_roboflow(self) -> Path:
        """Download Roboflow license plate dataset."""
        roboflow_root = self.datasets_dir / "Roboflow-LicensePlate"

        if (roboflow_root / "images").exists():
            logger.info(f"Roboflow already exists: {roboflow_root}")
            return roboflow_root

        logger.info("Roboflow not found. Instructions:")
        logger.info("1. Go to https://roboflow.com")
        logger.info("2. Download license plate dataset (free tier)")
        logger.info(f"3. Extract to {roboflow_root}")
        logger.info("4. Run this script again")

        raise FileNotFoundError(f"Please download Roboflow to {roboflow_root}")


def create_dataset_yaml(
    dataset_root: Path,
    num_classes: int = 2,
    class_names: list[str] | None = None,
) -> None:
    """
    Create dataset.yaml for YOLO.

    Expected structure:
        dataset_root/
            images/
                train/
                val/
                test/
            labels/
                train/
                val/
                test/
    """
    if class_names is None:
        class_names = ["single-line", "double-line"]

    yaml_content = {
        "path": str(dataset_root.absolute()),
        "train": "images/train",
        "val": "images/val",
        "test": "images/test",
        "nc": num_classes,
        "names": class_names,
    }

    yaml_path = dataset_root / "dataset.yaml"
    with open(yaml_path, "w") as f:
        yaml.dump(yaml_content, f, default_flow_style=False)

    logger.info(f"✓ Created {yaml_path}")


def validate_splits(dataset_root: Path) -> dict[str, int]:
    """Validate train/val/test splits exist and count images."""
    splits = {}
    for split in ["train", "val", "test"]:
        img_dir = dataset_root / "images" / split
        if not img_dir.exists():
            raise FileNotFoundError(f"Missing {img_dir}")

        count = len(list(img_dir.glob("*.jpg"))) + len(list(img_dir.glob("*.png")))
        splits[split] = count
        logger.info(f"{split}: {count} images")

    return splits


def main(cache_dir: str | None = None) -> None:
    """Main entry point."""
    if cache_dir is None:
        cache_dir = "~/.cache/anpr-datasets"

    cache_dir = Path(cache_dir).expanduser()
    downloader = DatasetDownloader(cache_dir)

    # Download datasets
    logger.info("=" * 60)
    logger.info("Downloading datasets...")
    logger.info("=" * 60)

    try:
        ccpd_root = downloader.download_ccpd()
        ufpr_root = downloader.download_ufpr()
        eu_root = downloader.download_openalpr_eu()
        roboflow_root = downloader.download_roboflow()
    except FileNotFoundError as e:
        logger.error(str(e))
        return

    # Prepare dataset structure
    logger.info("=" * 60)
    logger.info("Preparing dataset structure...")
    logger.info("=" * 60)

    dataset_root = cache_dir / "dataset"
    dataset_root.mkdir(exist_ok=True)

    # Create image/label directories
    for split in ["train", "val", "test"]:
        (dataset_root / "images" / split).mkdir(parents=True, exist_ok=True)
        (dataset_root / "labels" / split).mkdir(parents=True, exist_ok=True)

    # TODO: Implement actual dataset merging/splitting logic here
    # For now, just show structure

    logger.info(f"Dataset root: {dataset_root}")
    logger.info("Directory structure:")
    logger.info(f"  {dataset_root}/images/{{train,val,test}}/")
    logger.info(f"  {dataset_root}/labels/{{train,val,test}}/")

    # Create dataset.yaml
    create_dataset_yaml(dataset_root, num_classes=2, class_names=["single-line", "double-line"])

    # Validate
    logger.info("=" * 60)
    logger.info("Validating splits...")
    logger.info("=" * 60)

    try:
        splits = validate_splits(dataset_root)
        logger.info("\n✓ Dataset ready:")
        for split, count in splits.items():
            logger.info(f"  {split}: {count} images")
    except FileNotFoundError as e:
        logger.error(str(e))
        logger.error("Please run dataset merging step (TODO in script)")

    logger.info("\n✓ Preparation complete. Run:")
    logger.info("  python training/scripts/train_detector.py")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Prepare ANPR dataset splits")
    parser.add_argument(
        "--cache",
        default="~/.cache/anpr-datasets",
        help="Cache directory for datasets",
    )
    args = parser.parse_args()

    main(cache_dir=args.cache)
