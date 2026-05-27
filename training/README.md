# Training: Detector & OCR Fine-Tuning

Complete ML pipeline for plate detection + OCR recognition.

## Quick Start (M2: Detector Fine-Tuning)

### 1. Prepare Data

```bash
# Download datasets (manual: see script for instructions)
python training/data/prepare_splits.py --cache ~/.cache/anpr-datasets
```

This downloads:
- **CCPD:** 250k Chinese plates (primary training data)
- **UFPR-ALPR:** 4.5k Brazilian plates (cross-dataset validation)
- **OpenALPR-EU:** 15k EU plates (region diversity)
- **Roboflow:** 5k diverse plates (hard cases)

Creates structure:
```
~/.cache/anpr-datasets/
  dataset/
    images/{train, val, test}/
    labels/{train, val, test}/
    dataset.yaml
```

### 2. Train Detector (M2)

```bash
python training/scripts/train_detector.py
```

- Fine-tunes YOLOv8s on CCPD + synthetic.
- Logs to MLflow (`mlruns/` directory).
- Exports to ONNX (CPU inference).
- Target: **mAP@0.5 ≥ 0.92** (CCPD test).

**Expected time:** 3–5 hours on GPU (MacBook M1: ~8 hours).

**Output:**
```
runs/detect/detector-v1/weights/best.pt  # Best checkpoint
models/best.onnx                         # CPU inference
detector_results.json                    # Metrics + exports
```

### 3. Evaluate (M2 Acceptance)

```bash
python benchmarks/eval.py --set golden_in_small --model runs/detect/detector-v1/weights/best.pt
```

**Acceptance Criteria:**
- ✓ CCPD test mAP@0.5 ≥ 0.92
- ✓ UFPR test mAP@0.5 ≥ 0.88 (cross-dataset)
- ✓ ONNX inference <100ms on CPU
- ✓ MLflow tracking complete

---

## M3: OCR + Quality + Geometry (5 days)

```bash
python training/scripts/train_ocr.py
python training/scripts/train_geometry.py
python training/scripts/train_quality_gate.py
```

**Key modules:**
- `anpr_core/ocr/paddle_backend.py` — PaddleOCR wrapper
- `anpr_core/ocr/crnn_backend.py` — Custom CRNN+CTC
- `anpr_core/ocr/fuser.py` — Character-level confidence fusion
- `anpr_core/detect/normalize.py` — Perspective transform
- `anpr_core/quality/` — Blur/glare/occlusion gating

**Target:** Plate-level exact-match ≥0.90 (clean), ≥0.85 (hard).

---

## M4: Tracking & Multi-Frame Voting (3 days)

```bash
python training/scripts/train_tracker.py
```

**Key modules:**
- `anpr_core/tracking/bytetrack_wrapper.py` — ByteTrack integration
- `anpr_core/pipeline/voter.py` — Character-level voting

**Expected gain:** +10–15% on video vs single-frame.

---

## M5: Region Classifier + Postproc (4 days)

```bash
python training/scripts/train_region_classifier.py
```

**Key modules:**
- `anpr_core/postproc/region_classifier.py` — 3-class classifier (IN/EU/US)
- `anpr_core/postproc/regions/{in, eu, us}.py` — Per-region regex + confusion maps
- `anpr_core/postproc/gate.py` — Confidence gating

**Target:** ≥98% region classification accuracy.

---

## Config Files

### `configs/detector.yaml`

YOLOv8s training configuration. Edit hyperparams here:
- `epochs`, `batch_size`, `lr0`, `momentum`
- Augmentation: `degrees`, `translate`, `scale`, `hsv_*`

### `configs/ocr.yaml`

OCR backend configuration (PaddleOCR + CRNN).

### `configs/region_classifier.yaml`

Region classifier training config.

---

## MLflow Tracking

View training metrics:

```bash
mlflow ui
# → http://localhost:5000
```

Features:
- Parameter logging (LR, batch size, augmentation)
- Metric tracking (mAP, loss, validation accuracy)
- Model versioning + staging (Production, Staging)
- Git commit hash + Python environment tracking

---

## Integration with Inference

Once trained, models are:
1. **Registered in MLflow** — version + stage tracking
2. **Exported to ONNX** — CPU inference (`models/best.onnx`)
3. **Used by FastAPI** — `api/detection_service.py` loads + runs inference

```python
from anpr_core.detect import YOLODetector
from anpr_core.ocr import OCRFuser

detector = YOLODetector(model="models/best.onnx")
ocr = OCRFuser()

results = detector.detect(image)
for detection in results:
    crop = image[detection.bbox]
    plate_text = ocr.recognize(crop)
```

---

## DVC for Dataset Versioning

Track dataset versions + reproducibility:

```bash
# Initialize DVC (one-time)
dvc init

# Track golden sets
dvc add data/golden-sets/
git add data/golden-sets.dvc .gitignore

# Push to remote (S3, Google Drive, etc.)
dvc remote add -d myremote s3://my-bucket/anpr
dvc push
```

In CI/CD, reproduce exact dataset:
```bash
dvc pull  # Restore exact golden sets
python benchmarks/eval.py
```

---

## Troubleshooting

### OOM (Out of Memory)

Reduce batch size in `configs/detector.yaml`:
```yaml
batch_size: 16  # from 32
```

### Slow GPU

Ensure using GPU device:
```yaml
device: cuda:0  # or mps (Apple Silicon)
```

Check:
```bash
python -c "from ultralytics import YOLO; m = YOLO('yolov8s.pt'); print(m.device)"
```

### Validation mAP drops

Signs of overfitting. Try:
1. Increase augmentation (`mixup: 0.2`, `degrees: 25`)
2. Increase patience → early stop later
3. Add more synthetic data
4. Reduce learning rate

### ONNX export fails

Ensure dependencies:
```bash
uv pip install onnx onnxruntime
```

Then retry:
```python
from ultralytics import YOLO
m = YOLO("runs/detect/detector-v1/weights/best.pt")
m.export(format="onnx")
```

---

## References

- **YOLOv8:** https://docs.ultralytics.com/
- **PaddleOCR:** https://github.com/PaddlePaddle/PaddleOCR
- **CCPD Dataset:** https://github.com/detectRecog/CCPD
- **Albumentations:** https://albumentations.ai/
- **MLflow:** https://mlflow.org/

---

**Next:** Run `python training/data/prepare_splits.py` to download datasets.
