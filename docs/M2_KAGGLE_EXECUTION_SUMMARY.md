# M2: Kaggle Plate Detection - Execution Summary

## Task Executed

**M2 Goal:** Download Kaggle plate detection dataset, prepare in YOLO format, train YOLOv8s for 20 epochs, evaluate, and export.

## Dataset Acquisition & Preparation

**Source:** [Kaggle Number Plate Detection](https://www.kaggle.com/datasets/aslanahmedov/number-plate-detection/)

**Dataset Structure:**
```
~/.cache/anpr-datasets/
├── images/
│   ├── train/    (230 images)
│   ├── val/      (103 images)
│   └── test/     (103 images)
├── labels/
│   ├── train/    (230 .txt files)
│   ├── val/      (103 .txt files)
│   └── test/     (103 .txt files)
└── dataset.yaml
```

**Total:** 436 images | **Annotation Format:** YOLO (.txt, class IDs 0=single-line, 1=double-line)

**Data Validation:**
- ✓ Images and labels fully aligned (no missing pairs)
- ✓ All annotations in YOLO normalized format
- ✓ Train/Val/Test split: 52.8% / 23.6% / 23.6%

---

## Training Configuration

| Parameter | Value |
|-----------|-------|
| **Model** | YOLOv8s (11.1M parameters) |
| **Epochs** | 20 |
| **Batch Size** | 16 |
| **Image Size** | 640×640 |
| **Device** | CPU (Apple M4) |
| **Optimizer** | AdamW (auto-tuned: lr=0.001667) |
| **Augmentation** | Standard (mosaic, flip, HSV, scale) |

---

## Batch Training Capability (User Feature: "batch process to train faster")

**Implementation:** Multi-dataset parallel training using ThreadPoolExecutor

**Script:** `training/scripts/batch_train.py`

**Usage:**
```bash
# Train single dataset (sequential, optimized for CPU)
python training/scripts/batch_train.py --datasets kaggle --workers 1

# Train multiple datasets in parallel
python training/scripts/batch_train.py --datasets kaggle ccpd synthetic --workers 2

# Custom worker count
python training/scripts/batch_train.py --datasets kaggle ccpd --workers 3
```

**Why Batch Training:**
- Parallelizes training across multiple datasets using separate model instances
- Each dataset trains independently on CPU (no GPU memory conflicts)
- Useful for multi-region or multi-source ANPR training
- Reduces overall wall-clock time for ensemble training

**Supported Datasets:**
- `kaggle`: Kaggle plate detection (20 epochs, batch 16)
- `ccpd`: CCPD Chinese plates (100 epochs, batch 32)
- `synthetic`: Synthetic augmented plates (50 epochs, batch 16)

---

## Training Execution

**Training Scripts:**
- Main: `training/scripts/train_detector_m2.py` (supports baseline→full phases)
- Direct: Inline Python training with logging

**Output Directory:** `runs/detect/kaggle-yolov8s/`

**Expected Results (Target Metrics):**
- mAP@0.5 ≥ 0.80 (challenging small dataset, 436 images)
- mAP@0.75 ≥ 0.60
- Latency p95 < 250ms (CPU)

---

## Model Export

**Script:** `training/scripts/export_m2_model.py`

**Export Formats:**
- PyTorch (.pt) — native training artifact
- ONNX (.onnx) — CPU/GPU cross-platform inference
- TFLite (.tflite) — mobile/edge deployment

**Export Command:**
```bash
python training/scripts/export_m2_model.py
# Exports to: runs/detect/kaggle-yolov8s/weights/{best.onnx, best.tflite}
```

---

## Evaluation & Benchmarking

**Evaluation Script:** `benchmarks/eval_m2_kaggle_complete.py`

**Metrics Collected:**
1. **Validation Set:** mAP50, mAP75, Precision, Recall
2. **Test Set:** mAP50, mAP75, Precision, Recall
3. **Latency:** p50/p95/p99 (100 iterations, 640×480 images)
4. **Exports:** ONNX/TFLite success status

**Acceptance Criteria (M2 Gate):**
```
✓ test mAP@0.5 ≥ 0.80
✓ test mAP@0.75 ≥ 0.60
✓ latency p95 < 250ms
✓ ONNX export successful
→ Ready for M3/M4 integration
```

---

## Performance Baseline (Previous M2 Run - Synthetic Data)

From memory:
- mAP@0.5 = 0.586 (synthetic dataset, 5,000 images)
- p95 latency = 231ms (CPU)

**Expected Improvement:**
Kaggle dataset is smaller (436 vs 5,000) but naturally diverse. May see:
- Similar or slightly lower mAP (smaller dataset)
- Comparable latency (same model size)
- Better real-world generalization (multi-source diversity)

---

## Files Created/Modified

**New Training Scripts:**
- `training/scripts/train_detector_m2.py` (updated for Kaggle)
- `training/scripts/batch_train.py` (NEW: batch parallel training)
- `training/scripts/export_m2_model.py` (NEW: model export)
- `benchmarks/eval_m2_kaggle_complete.py` (NEW: comprehensive evaluation)
- `benchmarks/latency_m2_kaggle.py` (NEW: latency-only benchmark)

**Dataset:**
- `~/.cache/anpr-datasets/dataset.yaml` (corrected YOLO format)

---

## Next Steps (M3 Integration)

1. Verify M2 acceptance criteria pass
2. Copy best.pt to `models/detector_kaggle.pt`
3. Integrate with OCR pipeline (M3)
4. Test end-to-end detection→normalization→OCR
5. Measure gate performance (false positive rates, OCR confidence thresholds)

---

**Status:** Training in progress (ETA ~45min for 20 epochs on Apple M4 CPU)
**Updated:** 2026-05-27 22:35
