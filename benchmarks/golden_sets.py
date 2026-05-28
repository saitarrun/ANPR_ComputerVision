"""
Golden test set infrastructure for M2 evaluation.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


class GoldenSetBuilder:
    def __init__(self, golden_root: Path = None):
        if golden_root is None:
            golden_root = Path("data/golden-sets")
        self.golden_root = Path(golden_root)
        self.golden_root.mkdir(parents=True, exist_ok=True)

    def create_empty_golden_set(self, set_name: str, description: str, target_size: int = 50) -> Path:
        set_dir = self.golden_root / set_name
        set_dir.mkdir(parents=True, exist_ok=True)

        (set_dir / "images").mkdir(exist_ok=True)
        (set_dir / "labels").mkdir(exist_ok=True)

        metadata = {
            "name": set_name,
            "description": description,
            "target_size": target_size,
            "region": self._infer_region(set_name),
        }

        metadata_file = set_dir / "metadata.json"
        metadata_file.write_text(json.dumps(metadata, indent=2))

        dataset_yaml = {
            "path": str(set_dir.absolute()),
            "train": "images",
            "val": "images",
            "test": "images",
            "nc": 2,
            "names": ["single-line", "double-line"],
        }

        yaml_file = set_dir / "dataset.yaml"
        yaml_file.write_text(yaml.dump(dataset_yaml, default_flow_style=False))

        logger.info(f"✓ Created golden set: {set_name} at {set_dir}")
        return set_dir

    def _infer_region(self, set_name: str) -> str:
        if "india" in set_name or "in" in set_name:
            return "IN"
        elif "eu" in set_name:
            return "EU"
        elif "us" in set_name:
            return "US"
        else:
            return "MIXED"

    def create_all_golden_sets(self) -> dict[str, Path]:
        sets = {
            "india_small": ("India plates (50 samples): angled, blur, night", 50),
            "eu": ("EU plates (150 samples): weather, tilt, glare", 150),
            "us": ("US plates (100 samples): motion blur, poor lighting", 100),
            "full": ("All golden samples (600+)", 600),
        }

        paths = {}
        for set_name, (description, target_size) in sets.items():
            path = self.create_empty_golden_set(set_name, description, target_size)
            paths[set_name] = path

        logger.info(f"\n✓ Created {len(paths)} golden sets")
        return paths


def setup_golden_sets() -> None:
    logging.basicConfig(level=logging.INFO)
    builder = GoldenSetBuilder()
    builder.create_all_golden_sets()


if __name__ == "__main__":
    setup_golden_sets()
