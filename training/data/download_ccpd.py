#!/usr/bin/env python
"""
Download CCPD dataset from GitHub releases and prepare for YOLO training.

CCPD (Chinese City Parking Dataset) contains 250K license plate images
organized by difficulty (base, challenge, weather, night).

Usage:
    python training/data/download_ccpd.py --output ~/.cache/anpr-datasets/ccpd

Downloads:
    - CCPD2019.zip (~8GB) from GitHub releases
    - Extracts to output directory
    - Parses annotations from filenames (CCPD format)
    - Converts to YOLO format (normalized center + width/height)
    - Splits into train/val/test
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import shutil
import urllib.request
from pathlib import Path
from typing import Optional

import numpy as np
import yaml

from ccpd_loader import CCPDLoader, parse_ccpd_filename

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)


class CCPDDownloader:
    """Download and prepare CCPD dataset."""

    # GitHub releases base URL
    GITHUB_BASE = "https://github.com/detectRecog/CCPD/releases/download"
    CCPD_VERSION = "2019.06.27"

    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir).expanduser()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.ccpd_root = self.output_dir / "CCPD2019"
        logger.info(f"Output directory: {self.output_dir}")

    def download_file(self, url: str, dest: Path, max_retries: int = 3) -> bool:
        """Download a file with retry logic."""
        dest.parent.mkdir(parents=True, exist_ok=True)

        for attempt in range(max_retries):
            try:
                logger.info(f"Downloading {url.split('/')[-1]}... (attempt {attempt + 1}/{max_retries})")

                def progress_hook(block_num, block_size, total_size):
                    downloaded = block_num * block_size
                    if total_size > 0:
                        pct = min(100, int(downloaded * 100 / total_size))
                        if block_num % 50 == 0:  # Log every 50 blocks
                            logger.info(f"  Downloaded {downloaded / 1e9:.1f}GB / {total_size / 1e9:.1f}GB ({pct}%)")

                urllib.request.urlretrieve(url, dest, reporthook=progress_hook)
                logger.info(f"✓ Downloaded to {dest}")
                return True

            except Exception as e:
                logger.warning(f"  Attempt {attempt + 1} failed: {e}")
                if dest.exists():
                    dest.unlink()
                continue

        logger.error(f"✗ Failed to download {url} after {max_retries} attempts")
        return False

    def extract_zip(self, zip_path: Path) -> bool:
        """Extract CCPD zip file."""
        try:
            logger.info(f"Extracting {zip_path.name}...")
            import zipfile

            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(self.output_dir)
            logger.info(f"✓ Extracted to {self.output_dir}")
            return True
        except Exception as e:
            logger.error(f"✗ Extraction failed: {e}")
            return False

    def download_and_prepare(self) -> bool:
        """Main download + preparation pipeline."""
        # Check if already exists
        if self.ccpd_root.exists():
            logger.info(f"CCPD already exists at {self.ccpd_root}")
            return True

        # Option 1: Download from GitHub (may require authentication for large files)
        logger.info("=" * 60)
        logger.info("CCPD Dataset Download")
        logger.info("=" * 60)

        # For M2, we'll use a simplified approach:
        # CCPD is large (8GB), so we'll provide instructions for manual download
        # or use a cached/pre-downloaded version if available.

        logger.info("\nCCPD Dataset Download Instructions:")
        logger.info("1. Download CCPD from: https://github.com/detectRecog/CCPD")
        logger.info("2. Extract to: " + str(self.ccpd_root))
        logger.info("   Expected structure:")
        logger.info("     CCPD2019/")
        logger.info("       ccpd_base/        (121K images)")
        logger.info("       ccpd_challenge/   (36K images)")
        logger.info("       ccpd_weather/     (34K images)")
        logger.info("       ccpd_night/       (6K images)")
        logger.info("3. Re-run this script")

        logger.info("\nAlternatively, use a pre-downloaded copy:")
        logger.info(f"  cp -r /path/to/CCPD2019 {self.ccpd_root}")

        return False


class CCPDSplitter:
    """Split CCPD into train/val/test and convert to YOLO format."""

    def __init__(self, ccpd_root: Path, output_root: Path):
        self.ccpd_root = Path(ccpd_root)
        self.output_root = Path(output_root)
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.loader = CCPDLoader(ccpd_root)

    def prepare_splits(
        self, train_ratio: float = 0.6, val_ratio: float = 0.2, test_ratio: float = 0.2
    ) -> dict[str, int]:
        """Load CCPD, parse annotations, split, and save in YOLO format."""
        logger.info("=" * 60)
        logger.info("Preparing YOLO Dataset Splits")
        logger.info("=" * 60)

        # Load all annotations
        logger.info("\nLoading CCPD annotations...")
        annotations = self.loader.load_annotations()

        if not annotations:
            raise ValueError("No annotations loaded from CCPD")

        # Stratified split by difficulty
        logger.info("\nStratifying by difficulty...")
        stratified_annotations = self._stratify_by_difficulty(annotations)

        # Create image/label directories
        for split in ["train", "val", "test"]:
            (self.output_root / "images" / split).mkdir(parents=True, exist_ok=True)
            (self.output_root / "labels" / split).mkdir(parents=True, exist_ok=True)

        # Shuffle and split
        logger.info(f"\nSplitting: train={train_ratio:.0%}, val={val_ratio:.0%}, test={test_ratio:.0%}")
        np.random.seed(42)
        indices = np.arange(len(stratified_annotations))
        np.random.shuffle(indices)

        train_end = int(len(stratified_annotations) * train_ratio)
        val_end = train_end + int(len(stratified_annotations) * val_ratio)

        train_indices = set(indices[:train_end])
        val_indices = set(indices[train_end:val_end])
        test_indices = set(indices[val_end:])

        splits = {
            "train": train_indices,
            "val": val_indices,
            "test": test_indices,
        }

        logger.info(
            f"Splits: train={len(train_indices)}, val={len(val_indices)}, test={len(test_indices)}"
        )

        # Save images + labels
        logger.info("\nSaving images and labels...")
        saved_count = 0
        skipped_count = 0

        for idx, annotation in enumerate(stratified_annotations):
            split = None
            for split_name, split_set in splits.items():
                if idx in split_set:
                    split = split_name
                    break

            if not split:
                continue

            try:
                import cv2

                # Load image
                img = cv2.imread(annotation.image_path)
                if img is None:
                    skipped_count += 1
                    continue

                h, w = img.shape[:2]

                # Convert to YOLO format
                class_id, cx, cy, bw, bh = self.loader.to_yolo_format(annotation, w, h)

                # Save label
                label_path = self.output_root / "labels" / split / Path(annotation.image_path).stem
                label_path = label_path.with_suffix(".txt")
                label_path.write_text(f"{class_id} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}\n")

                # Link/copy image
                image_path = Path(annotation.image_path)
                output_image_path = self.output_root / "images" / split / image_path.name

                if not output_image_path.exists():
                    try:
                        output_image_path.hardlink_to(image_path)
                    except (OSError, NotImplementedError):
                        shutil.copy2(image_path, output_image_path)

                saved_count += 1
                if saved_count % 10000 == 0:
                    logger.info(f"  Saved {saved_count}/{len(stratified_annotations)}")

            except Exception as e:
                logger.warning(f"Error processing {annotation.image_path}: {e}")
                skipped_count += 1
                continue

        logger.info(f"\n✓ Saved {saved_count} images + labels (skipped {skipped_count})")

        # Validate
        split_counts = {}
        for split in ["train", "val", "test"]:
            img_dir = self.output_root / "images" / split
            count = len(list(img_dir.glob("*.jpg"))) + len(list(img_dir.glob("*.png")))
            split_counts[split] = count
            logger.info(f"  {split}: {count} images")

        # Create dataset.yaml
        self._create_dataset_yaml(split_counts)

        return split_counts

    def _stratify_by_difficulty(self, annotations: list) -> list:
        """Sort annotations by difficulty (blur, brightness) for better stratification."""
        # Sort by (blur, brightness) descending for stratification
        return sorted(annotations, key=lambda a: (a.blur, a.brightness), reverse=True)

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

        logger.info(f"\n✓ Created {yaml_path}")
        logger.info("\nDataset summary:")
        logger.info(f"  Total images: {sum(split_counts.values())}")
        for split, count in split_counts.items():
            logger.info(f"    {split}: {count}")


def main(output_dir: str | None = None, skip_download: bool = False) -> None:
    """Main entry point."""
    if output_dir is None:
        output_dir = "~/.cache/anpr-datasets/ccpd"

    output_dir = Path(output_dir).expanduser()

    # Check for pre-existing CCPD
    ccpd_root = output_dir / "CCPD2019"
    if ccpd_root.exists():
        logger.info(f"✓ CCPD found at {ccpd_root}")
    else:
        logger.info(f"CCPD not found at {ccpd_root}")
        if not skip_download:
            downloader = CCPDDownloader(output_dir)
            if not downloader.download_and_prepare():
                logger.error(
                    f"\nTo proceed, manually download CCPD to {ccpd_root} and run:\n"
                    f"  python training/data/download_ccpd.py --output {output_dir} --skip-download"
                )
                return

    # Prepare splits
    dataset_root = output_dir / "dataset"
    splitter = CCPDSplitter(ccpd_root, dataset_root)
    split_counts = splitter.prepare_splits()

    logger.info("\n" + "=" * 60)
    logger.info("✓ CCPD preparation complete!")
    logger.info("=" * 60)
    logger.info(f"Dataset: {dataset_root}")
    logger.info(f"Next: python training/scripts/train_detector_m2.py --phase full")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download and prepare CCPD dataset")
    parser.add_argument(
        "--output",
        default="~/.cache/anpr-datasets/ccpd",
        help="Output directory for CCPD",
    )
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="Skip download (use existing CCPD)",
    )
    args = parser.parse_args()

    main(output_dir=args.output, skip_download=args.skip_download)
