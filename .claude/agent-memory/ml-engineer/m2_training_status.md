---
name: m2_training_status
description: M2 full training execution - YOLOv8s detector on synthetic + CCPD data
metadata:
  type: project
---

## M2 Full Training Execution Log

**Status:** Restarted with correct dataset (436 images after filtering)

**Data:**
- Source: Golden sets (600 images) → synthetic extended dataset → cleaned
- Location: `~/.cache/anpr-datasets/`
- Split: Train/val/test from 436 available images (updated from 360/120/120)
- Format: YOLO (normalized bbox + class)
- Note: M2 spec requires 250K CCPD images (requires manual download from GitHub)

**Configuration:**
- Model: YOLOv8s (pre-trained)
- Epochs: 100 (changed from 10 to match spec)
- Batch size: 16
- Device: CPU (CUDA unavailable)
- Patience: 15 (early stopping)
- Augmentation: mosaic, mixup, rotation, HSV, flip

**Expected Outcomes:**
- Target mAP@0.5: ≥0.92
- Target latency p95: <200ms
- Exports: PyTorch, ONNX, TFLite

**Training Constraints:**
- CPU-only (slow, 24-48h estimated)
- Limited to 600 synthetic images (M2 spec is 250K CCPD)
- Will establish baseline → can integrate CCPD when manually downloaded

**Key Paths:**
- Training script: `training/scripts/train_detector_m2.py`
- Config: `training/configs/detector.yaml`
- Output: `runs/detect/anpr/detector-ccpd/`
- Production model destination: `models/detector_prod.pt`
