# ML Specification: Plate Detection & Recognition

## Executive Summary

Build industrial-grade detector + OCR system for 3 regions (IN/EU/US). Target: **<2s e2e latency**, **≥95% plate-level accuracy** (clean), **≥85% accuracy** (hard cases). Achieve via YOLOv8s fine-tuning + multi-backend OCR fusion + multi-frame voting + region-specific postprocessing.

---

## 1. Problem Statement

### Task Definition

- **Detection:** Localize license plates in images (bbox regression) → single-line or double-line classes.
- **Recognition:** OCR characters within detected plates → region-specific validation.
- **Multi-Frame Fusion:** Stabilize flickering OCR across video frames via character-level voting.
- **Region Routing:** Classify plate region (India, EU, US) and apply per-region rules.

### Success Metrics

| Metric | Target | Acceptance |
|--------|--------|-----------|
| Detector mAP@0.5 (held-out val) | ≥0.92 | Minimum for release |
| Detector mAP@0.75 | ≥0.80 | Nice-to-have |
| OCR exact-match (plate-level, clean) | ≥0.95 | Must-have |
| OCR exact-match (hard cases: blur/glare/tilt) | ≥0.85 | Must-have |
| End-to-end latency p95 | <200ms | Budget: 2s / 10 frames |
| Region classifier accuracy | ≥0.98 | Route errors are costly |

### Baseline (Non-ML)

**Heuristic baseline:** Pre-trained YOLOv8n on COCO + PaddleOCR single-frame, no fusion.

```
Baseline detector mAP@0.5: ~0.75 (yolov8n generic)
Baseline OCR exact-match: ~0.65 (no fusion/normalization)
Baseline latency p95: ~250ms
```

**Target:** +15–20 mAP points, +25–30 exact-match points via fine-tuning + fusion.

---

## 2. Data Strategy

### Training Sources

1. **CCPD:** 250k Chinese plates. Diverse angles, blur, night.
2. **UFPR-ALPR:** 4.5k Brazilian plates (Latin alphabet).
3. **OpenALPR EU:** 15k EU plates.
4. **Roboflow:** 5k diverse, including US.
5. **Synthetic:** 50k augmented per region (perspective, blur, noise, glare).

### Split

- **Train (60%):** CCPD train (200k) + 80% synthetic.
- **Val (20%):** CCPD val (25k) + Roboflow.
- **Test (20%):** CCPD test (25k) + UFPR + OpenALPR-EU (region-stratified).

### Data Quality

- Min resolution: 100×30px (detected plate).
- Annotation agreement: κ > 0.92 (if manual).
- Outlier removal: Confidence < 0.5 on baseline YOLO → dropped.
- Imbalance: Oversample hard cases (night, tilt, blur) by 1.5×.

---

## 3. Detector: YOLOv8s Fine-Tuning

### Why YOLOv8s

- **Speed:** ~60ms inference on CPU (ONNX).
- **Accuracy:** mAP≥0.92 achievable with fine-tuning.
- **Size:** 24M params, fits CPU + mobile.

### Training Config

```yaml
model: yolov8s.pt
imgsz: 640
epochs: 100
batch_size: 32
device: cuda:0 (or mps on Mac)
optimizer: SGD
lr0: 0.01
lrf: 0.01
momentum: 0.937
weight_decay: 0.0005

augment:
  hsv_h: 0.015
  hsv_s: 0.7
  hsv_v: 0.4
  degrees: 20
  translate: 0.1
  scale: 0.5
  flipud: 0.0
  fliplr: 0.5
  mosaic: 1.0
  mixup: 0.1

patience: 30
export_formats: ["pt", "onnx", "tflite"]
```

### Procedure

1. Baseline: 10 epochs on CCPD only → log mAP@0.5 / @0.75.
2. Full training: 100 epochs with CCPD + synthetic (1:1 ratio).
3. ONNX export: `best.onnx` for CPU inference.

### Validation

**Per-epoch:** mAP@0.5, @0.75, precision, recall (CCPD val).

**End-of-training:**
- CCPD test: mAP@0.5 ≥ 0.92.
- UFPR test: mAP@0.5 ≥ 0.88 (cross-dataset tolerance: <4 point drop).
- OpenALPR-EU test: mAP@0.5 ≥ 0.88.
- Roboflow hard cases: mAP@0.5 ≥ 0.85.

---

## 4. OCR: Multi-Backend Fusion

### Backend A: PaddleOCR

- Fast (~50ms), high accuracy on Latin + CJK.
- Per-char confidence.
- **Config:**

```python
from paddleocr import PaddleOCR

ocr_a = PaddleOCR(
    use_angle_cls=False,
    rec_model_dir="models/paddle",
    use_gpu=True,
    enable_mkldnn=True,
)
```

### Backend B: CRNN+CTC

- Fine-tuned on CCPD + OpenALPR-EU.
- 37-class vocabulary: [0-9, A-Z, "-"].

```python
class CRNN(nn.Module):
    def __init__(self, num_classes=37):
        super().__init__()
        self.conv = nn.Sequential(
            nn.Conv2d(3, 64, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2),
            nn.Conv2d(64, 128, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2),
            nn.Conv2d(128, 256, 3, padding=1), nn.ReLU(),
        )
        self.rnn = nn.LSTM(256, 256, 2, bidirectional=True, batch_first=True)
        self.fc = nn.Linear(512, num_classes)
    
    def forward(self, x):
        x = self.conv(x)  # (B, 256, H/4, W/4)
        x = x.permute(0, 3, 1, 2).reshape(x.size(0), x.size(3), -1)  # (B, W, C)
        x, _ = self.rnn(x)
        x = self.fc(x)
        return x
```

**Training:** 50 epochs, batch_size=64, lr=0.001 (Adam), CTCLoss.

**Target:** Plate-level exact-match ≥0.90 on clean val.

### Fusion Strategy

```python
for i in range(len(plate)):
    conf_a = paddle[i].confidence
    conf_b = crnn[i].confidence
    
    if abs(conf_a - conf_b) < 0.2:  # agreement
        char = paddle[i].char
        conf = max(conf_a, conf_b)
    else:
        char = max(paddle[i], crnn[i], key=lambda x: x.confidence).char
        conf = max(conf_a, conf_b)
```

**Rationale:** Agreement → high confidence. Disagreement → take higher confidence (safety).

---

## 5. Geometric Normalization (F3)

Perspective-skewed plates kill OCR. Detect 4 corners → warp to canonical 200×60.

```python
import cv2

src_pts = np.array(detected_corners, dtype=np.float32)  # 4 points from detector
dst_pts = np.array([[0, 0], [200, 0], [200, 60], [0, 60]], dtype=np.float32)
M = cv2.getPerspectiveTransform(src_pts, dst_pts)
normalized = cv2.warpPerspective(crop, M, (200, 60))
```

**Expected gain:** +5–12% on angled plates (±25° tilt).

---

## 6. Quality Gating (F4)

Reject low-quality detections before OCR.

| Check | Threshold | Why |
|-------|-----------|-----|
| Laplacian variance (blur) | >100 | Blurry = unreadable |
| Histogram peak (glare) | <200 | Overexposed = unreadable |
| Bbox w/h ratio | 2.5 ≤ w/h ≤ 8.0 | Anatomical sanity |
| Min char-height (px) | ≥8 | Too small = OCR noise |
| Detection conf | ≥0.5 | Weak detections are junk |

**Action:** If any check fails → skip OCR + persist. Tracker continues (next frame may be cleaner).

---

## 7. Multi-Frame Tracking & Voting (F5)

### ByteTrack

```python
from supervision import ByteTrack

tracker = ByteTrack(
    frame_rate=30,
    track_thresh=0.25,
    track_buffer=30,
    match_thresh=0.8,
)
```

### Character-Level Voting

```python
# Across N frames for same tracked plate ID:
frame_1: "ABC123" [0.90, 0.92, 0.88, ...]
frame_2: "ABC123" [0.91, 0.93, 0.87, ...]
frame_3: "ABD123" [0.89, 0.70, 0.88, ...]  # typo on char 2

# Majority vote per char → "ABC123"
# Confidence per char = mean([0.90, 0.91, 0.89]) = 0.90
# Char must have ≥3 votes or ≥67% majority
```

**Expected gain:** +10–15% on video vs single-frame.

---

## 8. Region Classifier (F6)

Lightweight CNN: 3-class (IN/EU/US).

```python
class RegionClassifier(nn.Module):
    def __init__(self):
        super().__init__()
        self.conv1 = nn.Conv2d(3, 32, 3, padding=1)
        self.pool = nn.MaxPool2d(2)
        self.conv2 = nn.Conv2d(32, 64, 3, padding=1)
        self.fc1 = nn.Linear(64 * 30 * 30, 128)
        self.fc2 = nn.Linear(128, 3)
    
    def forward(self, x):
        x = self.pool(F.relu(self.conv1(x)))
        x = self.pool(F.relu(self.conv2(x)))
        x = x.view(x.size(0), -1)
        x = F.relu(self.fc1(x))
        return self.fc2(x)
```

**Input:** Crop (120×36).
**Output:** Logits for [IN, EU, US].
**Training:** ~5k images/region (CCPD-IN + OpenALPR-EU + Roboflow-US).

**Target:** ≥98% accuracy on held-out test.

---

## 9. Per-Region Postprocessing (F6 continued)

### India

**Format:** `MH02AB1234` (2 letters + 2 digits + 2 letters + 4 digits).

```python
INDIA_REGEX = r"^[A-Z]{2}\d{2}[A-Z]{2}\d{4}$"
confusion_map = {"0": ["O"], "1": ["I", "L"], "5": ["S"], "8": ["B"], "2": ["Z"]}
```

### EU

**Format:** `AB123CDE` or variants (2 letters + 3 digits + 3 letters).

```python
EU_PATTERNS = [
    r"^[A-Z]{2}\d{3}[A-Z]{3}$",
    r"^[A-Z]{3}\d{3,4}[A-Z]{0,2}$",
]
confusion_map = {"0": ["O"], "1": ["I"], "5": ["S"]}
```

### US

**Format:** `ABC1234` or `12345ABC` (flexible).

```python
US_PATTERNS = [
    r"^[A-Z]{1,3}\d{1,5}$",
    r"^\d{1,5}[A-Z]{1,3}$",
]
```

**Action:** Try regex. If fail, attempt up-to-2 confusion-swaps. If still fail → review queue.

---

## 10. Confidence Gating (F7)

**Rule:**
- Per-char conf ≥ 0.6.
- Plate-level conf ≥ 0.75.
- Regex passes (after confusion fixes).

**Action:**
- **Pass:** Persist to DB, check watchlist, log event.
- **Fail:** Route to `review_queue`. Mark `is_persisted=False`.

---

## 11. Latency Budget

**Target:** <2s total, <200ms inference.

```
Frame grab:               1ms
Detector (ONNX CPU):     60ms
Crop + normalize:         5ms
OCR (2 backends async):  50ms
Region classify:          2ms
Postproc + vote:         10ms
DB persist (async):      20ms
───────────────────────────
Total:                  ~150ms (headroom: 50ms)
```

---

## 12. Training & Evaluation

### Repo Structure

```
training/
  configs/
    detector.yaml
    ocr.yaml
    region_classifier.yaml
  scripts/
    train_detector.py
    train_ocr.py
    train_region_classifier.py
    eval.py
    export_models.py
  data/
    download_ccpd.py
    prepare_splits.py
benchmarks/
  eval.py
  bench_latency.py
```

### CI Gate

```yaml
# .github/workflows/ml-gate.yaml
name: ML Gate
on: [pull_request]

jobs:
  eval:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v4
      - name: Download golden set
        run: dvc pull
      - name: Run benchmark
        run: python benchmarks/eval.py --set golden_in_small
      - name: Check gate
        run: |
          python -c "
          import json
          with open('eval_results.json') as f:
            results = json.load(f)
          baseline = 0.90
          assert results['plate_exact_match'] >= baseline - 0.01
          "
```

---

## 13. Model Versioning

### MLflow

```python
import mlflow

mlflow.set_tracking_uri("file:./mlruns")

# After training
mlflow.pytorch.log_model(model, "model")
mlflow.log_metrics({
    "test_mAP@0.5": 0.92,
    "test_plate_exact_match": 0.95,
    "latency_p95_ms": 145,
})

# Promote
client = mlflow.tracking.MlflowClient()
client.transition_model_version_stage("detector", 1, "Production")
```

### ONNX Export

```python
from ultralytics import YOLO

model = YOLO("runs/detect/train/weights/best.pt")
model.export(format="onnx", imgsz=640)
# → best.onnx (CPU inference)
```

### Hot Reload

```python
# POST /v1/models/detector/reload (admin only)
@app.post("/v1/models/detector/reload")
def reload_detector(version: str = "latest") -> dict:
    global detector
    detector = load_detector_from_registry(version)
    return {"status": "ok"}
```

---

## 14. Known Limitations

| Limitation | Mitigation |
|-----------|-----------|
| Synthetic distribution shift | Validate on real data; retrain if >2% drop. |
| Double-line plates | Separate class; skip OCR for now. Defer to M6+. |
| Night/IR plates | Augment with brightness variants; separate model if needed (v1.1). |
| Motorcycle plates (3-digit IN) | Separate regex. Defer to M6+. |
| Region misclassification | Ensemble 3 classifiers; majority vote. Fallback: review queue. |
| OCR hallucination | Check "no valid chars" → review queue. |

---

## 15. Acceptance Criteria

### M2: Detector Fine-Tuning (5 days)

- [ ] CCPD test mAP@0.5 ≥ 0.92.
- [ ] UFPR test mAP@0.5 ≥ 0.88 (cross-dataset).
- [ ] ONNX export passes inference test (torch vs ONNX ±1e-4).
- [ ] Latency p95 <100ms on CPU.
- [ ] MLflow: all runs logged with hyperparams + metrics.

### M3: OCR + Quality + Geometry (5 days)

- [ ] Plate-level exact-match ≥0.90 (PaddleOCR clean val).
- [ ] CRNN exact-match ≥0.85 (fine-tuned).
- [ ] Fusion tested: no accuracy loss vs single backend.
- [ ] Geometric normalization: +5% gain on tilted plates.
- [ ] Quality gating: blur/glare rejection validated.
- [ ] End-to-end integration test: detector → normalize → OCR passes.

### M4: Tracking & Voting (3 days)

- [ ] ByteTrack integrated; plate tracking ≥5 frames.
- [ ] Character voting: +10% gain on video vs single-frame.
- [ ] Confidence gate: only persist if plate_conf ≥0.75.
- [ ] Review queue: low-confidence logged.
- [ ] Latency: voting adds <20ms overhead.

### M5: Region Classifier + Postproc (4 days)

- [ ] Region classifier: ≥98% accuracy (3 regions).
- [ ] India postproc: regex + confusion-map validated.
- [ ] EU postproc: multi-pattern validator.
- [ ] US postproc: flexible regex, reversed format accepted.
- [ ] Confidence gate: 0% false positives on review queue.
- [ ] Full pipeline tested on sample streams.

---

## 16. Success Definition

**Phase-0 (end M4):**
```
$ python benchmarks/eval.py --set golden_in_small
Detector: mAP@0.5 = 0.92 ✓
OCR exact-match = 0.93 ✓
Latency p95 = 147ms ✓
```

**Full system (end M5+):**
```
$ python benchmarks/eval.py --set golden_full
Region IN: 500 plates, exact-match = 0.94 ✓
Region EU: 300 plates, exact-match = 0.91 ✓
Region US: 200 plates, exact-match = 0.92 ✓
Avg latency p95: 156ms ✓
```

---

**Version:** 1.0  
**Date:** 2026-05-27
