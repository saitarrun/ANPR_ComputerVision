"""Custom CRNN+CTC recognition backend."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

logger = logging.getLogger(__name__)

# Charset: 0-9, A-Z, hyphen
CHARSET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ-"
CHAR_TO_IDX = {c: i for i, c in enumerate(CHARSET)}
IDX_TO_CHAR = {i: c for c, i in CHAR_TO_IDX.items()}


@dataclass
class OCRResult:
    """Single character recognition result."""

    char: str
    confidence: float


class CRNN(nn.Module):
    """
    CRNN architecture: Conv → RNN → CTC.

    - Conv: Extract spatial features
    - RNN (LSTM): Model temporal dependencies
    - CTC: Align to variable-length sequences (no forced char alignment)
    """

    def __init__(self, num_classes: int = len(CHARSET)) -> None:
        super().__init__()

        # Convolutional feature extraction
        self.conv = nn.Sequential(
            # Input: 3 x H x W
            nn.Conv2d(3, 32, kernel_size=3, padding=1),
            nn.BatchNorm2d(32),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2, 2),  # → 32 x H/2 x W/2
            nn.Conv2d(32, 64, kernel_size=3, padding=1),
            nn.BatchNorm2d(64),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2, 2),  # → 64 x H/4 x W/4
            nn.Conv2d(64, 128, kernel_size=3, padding=1),
            nn.BatchNorm2d(128),
            nn.ReLU(inplace=True),
            nn.MaxPool2d((2, 1), (2, 1)),  # → 128 x H/8 x W/4
            nn.Conv2d(128, 256, kernel_size=3, padding=1),
            nn.BatchNorm2d(256),
            nn.ReLU(inplace=True),
            nn.MaxPool2d((2, 1), (2, 1)),  # → 256 x H/16 x W/4
        )

        # RNN: bidirectional LSTM
        # Input: (seq_len, batch, 256)
        self.rnn = nn.LSTM(256, 256, num_layers=2, bidirectional=True, batch_first=True)

        # Output: linear layer
        self.fc = nn.Linear(512, num_classes)  # 256*2 (bidirectional)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Forward pass.

        Args:
            x: (batch, 3, H, W)

        Returns:
            (batch, seq_len, num_classes) logits
        """
        # Conv → (batch, 256, h, w)
        x = self.conv(x)

        # Reshape for RNN: (batch, seq_len, features)
        # seq_len = width after pooling, features = 256 channels
        batch, channels, height, width = x.size()
        x = x.permute(0, 3, 1, 2)  # (batch, width, channels, height)
        x = x.contiguous().view(batch, width, channels * height)

        # RNN
        x, _ = self.rnn(x)  # (batch, seq_len, 512)

        # Output layer
        x = self.fc(x)  # (batch, seq_len, num_classes)

        return x


class CRNNBackend:
    """Custom CRNN recognition backend."""

    def __init__(self, model_path: str | None = None, device: str = "cpu") -> None:
        """
        Args:
            model_path: Path to saved model weights
            device: 'cpu' or 'cuda:0'
        """
        self.device = device
        self.model = CRNN(num_classes=len(CHARSET)).to(device)
        self.model.eval()

        if model_path and Path(model_path).exists():
            logger.info(f"Loading CRNN from {model_path}")
            state = torch.load(model_path, map_location=device)
            self.model.load_state_dict(state)
        else:
            logger.warning(f"Model not found at {model_path}; using random init (pre-train first)")

    def recognize(self, crop: np.ndarray) -> list[OCRResult]:
        """
        Recognize characters in plate crop.

        Args:
            crop: BGR image, normalized 200x60 or similar

        Returns:
            List of OCRResult (char, confidence) in reading order
        """
        if crop.size == 0:
            return []

        # Preprocess
        # Convert BGR → RGB
        crop_rgb = crop[:, :, ::-1]
        # Normalize: [0, 255] → [0, 1]
        crop_norm = crop_rgb.astype(np.float32) / 255.0
        # Resize to standard 32x128 (CRNN expects H=32)
        import cv2
        h, w = 32, 128
        crop_resized = cv2.resize(crop_norm, (w, h))
        # Transpose to (3, H, W)
        crop_tensor = torch.from_numpy(crop_resized.transpose(2, 0, 1)).unsqueeze(0)
        crop_tensor = crop_tensor.to(self.device)

        # Inference
        with torch.no_grad():
            logits = self.model(crop_tensor)  # (1, seq_len, num_classes)

        # Convert logits to char-level predictions
        # logits: (1, seq_len, num_classes)
        probs = F.softmax(logits, dim=-1)  # (1, seq_len, num_classes)
        conf, pred_idx = torch.max(probs, dim=-1)  # (1, seq_len)

        results = []
        for i in range(pred_idx.size(1)):
            idx = int(pred_idx[0, i].item())
            confidence = float(conf[0, i].item())

            if idx < len(CHARSET):
                char = CHARSET[idx]
                results.append(OCRResult(char=char, confidence=confidence))

        # Filter out padding (index 0, often blank)
        # results = [r for r in results if r.char != CHARSET[0]]

        return results

    def __repr__(self) -> str:
        return "CRNN+CTC"
