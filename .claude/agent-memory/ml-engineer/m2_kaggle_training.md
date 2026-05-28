---
name: m2_kaggle_training
description: M2 Kaggle plate detection training pipeline - 20 epochs, batch processing support
metadata:
  type: project
---

## M2 Kaggle Plate Detection Training

**Dataset:** Aslan Ahmedov's Number Plate Detection (Kaggle)
- **Size:** 436 images total
  - Train: 230 images (52.8%)
  - Val: 103 images (23.6%)
  - Test: 103 images (23.6%)
- **Format:** YOLO (class IDs 0=single-line, 1=double-line)
- **Location:** `/Users/saitarrunpitta/.cache/anpr-datasets/`

**Training Configuration:**
- **Model:** YOLOv8s (11.1M parameters)
- **Epochs:** 20
- **Batch Size:** 16 (CPU, Apple M4)
- **Image Size:** 640×640
- **Optimizer:** AdamW (auto-tuned)
- **Device:** CPU (no GPU available on M4)

**Training Scripts:**
- Main trainer: `/Users/saitarrunpitta/Projects/ComputerVision Project/training/scripts/train_detector_m2.py`
- Batch trainer: `/Users/saitarrunpitta/Projects/ComputerVision Project/training/scripts/batch_train.py` (for multi-dataset parallel training)
- Export script: `/Users/saitarrunpitta/Projects/ComputerVision Project/training/scripts/export_m2_model.py`

**Output Location:**
- Training dir: `runs/detect/runs/detect/kaggle-plate-detection/`
- Best model: `weights/best.pt`
- Weights file: ~43MB

**Why:** Batch training enables parallel multi-dataset training using ThreadPoolExecutor (useful for future CCPD + synthetic hybrid training).

**How to apply:** Use `python training/scripts/batch_train.py --datasets kaggle ccpd --workers 2` for concurrent training of multiple datasets on CPU.
