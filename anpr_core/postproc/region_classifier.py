"""Lightweight region classifier (IN/EU/US)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

logger = logging.getLogger(__name__)

# Region mapping
REGIONS = ["IN", "EU", "US"]
REGION_TO_IDX = {r: i for i, r in enumerate(REGIONS)}
IDX_TO_REGION = {i: r for r, i in REGION_TO_IDX.items()}


@dataclass
class RegionResult:
    """Region classification result."""

    region: str  # "IN", "EU", or "US"
    confidence: float
    scores: dict[str, float]  # All region scores


class RegionClassifierCNN(nn.Module):
    """Lightweight 3-class region classifier."""

    def __init__(self) -> None:
        super().__init__()

        self.conv = nn.Sequential(
            nn.Conv2d(3, 32, kernel_size=3, padding=1),
            nn.BatchNorm2d(32),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2, 2),
            nn.Conv2d(32, 64, kernel_size=3, padding=1),
            nn.BatchNorm2d(64),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2, 2),
        )

        self.fc = nn.Sequential(
            nn.Linear(64 * 30 * 30, 128),
            nn.ReLU(inplace=True),
            nn.Dropout(0.5),
            nn.Linear(128, len(REGIONS)),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: (batch, 3, 120, 120)

        Returns:
            (batch, 3) logits
        """
        x = self.conv(x)
        x = x.view(x.size(0), -1)
        x = self.fc(x)
        return x


class RegionClassifier:
    """Classify plate region (India, EU, US)."""

    def __init__(self, model_path: str | None = None, device: str = "cpu") -> None:
        """
        Args:
            model_path: Path to saved weights
            device: "cpu" or "cuda:0"
        """
        self.device = device
        self.model = RegionClassifierCNN().to(device)
        self.model.eval()

        if model_path and Path(model_path).exists():
            logger.info(f"Loading region classifier from {model_path}")
            state = torch.load(model_path, map_location=device)
            self.model.load_state_dict(state)
        else:
            logger.warning(f"Model not found at {model_path}; using random init")

    def classify(self, crop: np.ndarray) -> RegionResult:
        """
        Classify plate region.

        Args:
            crop: Plate crop (any size, will be resized)

        Returns:
            RegionResult with region + confidence
        """
        if crop.size == 0:
            return RegionResult(region="IN", confidence=0.0, scores={r: 0.0 for r in REGIONS})

        # Preprocess
        import cv2

        # Resize to 120×120
        crop_resized = cv2.resize(crop, (120, 120))
        # Normalize
        crop_norm = crop_resized.astype(np.float32) / 255.0
        # (H, W, C) → (C, H, W)
        crop_tensor = torch.from_numpy(crop_norm.transpose(2, 0, 1)).unsqueeze(0)
        crop_tensor = crop_tensor.to(self.device)

        # Inference
        with torch.no_grad():
            logits = self.model(crop_tensor)  # (1, 3)
            probs = F.softmax(logits, dim=-1)  # (1, 3)

        # Get prediction
        pred_idx = int(torch.argmax(probs[0]).item())
        pred_region = REGIONS[pred_idx]
        pred_conf = float(probs[0, pred_idx].item())

        # All scores
        scores = {REGIONS[i]: float(probs[0, i].item()) for i in range(len(REGIONS))}

        return RegionResult(region=pred_region, confidence=pred_conf, scores=scores)


__all__ = ["RegionClassifier", "RegionResult", "REGIONS"]
