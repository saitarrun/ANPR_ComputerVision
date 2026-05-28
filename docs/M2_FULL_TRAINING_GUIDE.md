# M2 Full Training: 250K CCPD → mAP≥0.92

**Timeline:** 24–48h (depends on GPU availability and CCPD download)
**Success Criteria:** mAP@0.5 ≥ 0.92, latency p95 <200ms

## Phase 1: Download CCPD Dataset (1–2h)

### Option A: Manual Download (Recommended for fastest M2 execution)

CCPD (Chinese City Parking Dataset) is ~8GB and best downloaded manually:

```bash
# 1. Download CCPD2019.zip from GitHub releases:
#    https://github.com/detectRecog/CCPD/releases/tag/2019.06.27
#    File: CCPD2019.zip (~8GB)
#    Save to: ~/Downloads/CCPD2019.zip

# 2. Extract to cache directory:
mkdir -p ~/.cache/anpr-datasets/ccpd
unzip ~/Downloads/CCPD2019.zip -d ~/.cache/anpr-datasets/ccpd

# 3. Verify structure:
ls ~/.cache/anpr-datasets/ccpd/CCPD2019/
# Should show: ccpd_base/, ccpd_challenge/, ccpd_weather/, ccpd_night/

# 4. Count images:
find ~/.cache/anpr-datasets/ccpd/CCPD2019 -name "*.jpg" | wc -l
# Expected: ~250,000 images
```

### Option B: Automated Download (if GitHub API available)

```bash
python training/data/download_ccpd.py --output ~/.cache/anpr-datasets/ccpd
```

Note: Large file downloads may timeout. Manual download is more reliable.

## Phase 2: Prepare Dataset Splits (30 min)

Once CCPD is extracted:

```bash
# Parse CCPD annotations, create train/val/test splits
python training/data/download_ccpd.py --output ~/.cache/anpr-datasets/ccpd --skip-download

# This will:
# - Load all CCPD images (250K)
# - Parse bounding boxes from filenames
# - Create YOLO format (normalized center + width/height)
# - Split: 60% train (150K), 20% val (50K), 20% test (50K)
# - Create dataset.yaml
# - Output: ~/.cache/anpr-datasets/ccpd/dataset/
```

Verify dataset preparation:

```bash
ls -lh ~/.cache/anpr-datasets/ccpd/dataset/
ls ~/.cache/anpr-datasets/ccpd/dataset/images/{train,val,test} | wc -l
# Expected: 150K train, 50K val, 50K test
```

## Phase 3: Train Detector (24–48h on GPU)

### Hardware Note

- **GPU (recommended):** CUDA/Metal GPU → 24–48h, p95 latency ~50–80ms
- **CPU (slow):** → 72–120h, p95 latency ~200ms

### GPU Setup (if CUDA available)

```bash
# Check GPU availability:
python -c "from ultralytics import YOLO; m = YOLO('yolov8s.pt'); print(m.device)"
# Should show: cuda:0 or similar

# If no GPU, the script will fall back to CPU (slower)
```

### Run Full Training

```bash
# Start 100-epoch training:
make m2-full
# or:
python training/scripts/train_detector_m2.py --phase full

# This will:
# - Load YOLOv8s pretrained weights
# - Train on 250K CCPD images
# - 100 epochs with augmentation (mosaic, mixup, color/geometry transforms)
# - Validate on 50K val set every epoch
# - Early stopping if no improvement after 30 epochs
# - Save best model to: runs/detect/anpr/detector-ccpd/weights/best.pt
```

### Monitor Training

```bash
# Watch training progress:
tail -f runs/detect/anpr/detector-ccpd/results.csv

# Expected metrics per epoch:
# - box loss (regression): 0.1 → 0.05
# - cls loss (classification): 0.2 → 0.1
# - mAP@0.5: 0.55 → 0.92+
# - mAP@0.75: 0.35 → 0.70+
```

## Phase 4: Evaluate on Golden Sets (20 min)

Once training completes:

```bash
# Evaluate on golden sets (separate from training set):
make m2-eval

# or:
python benchmarks/eval_m2.py --set golden_in_small

# Expected output:
# india_small (50 synthetic): mAP@0.5 = X.XXX
# eu (150 synthetic): mAP@0.5 = X.XXX
# us (100 synthetic): mAP@0.5 = X.XXX
# full (300 synthetic): mAP@0.5 = X.XXX
```

## Phase 5: Export Model (5 min)

Model export happens automatically during training, but verify:

```bash
# Check exports:
ls -lh runs/detect/anpr/detector-ccpd/weights/
# Should include: best.pt, last.pt

# Copy to production directory:
cp runs/detect/anpr/detector-ccpd/weights/best.pt models/detector_prod.pt

# Verify model loads:
python -c "from ultralytics import YOLO; m = YOLO('models/detector_prod.pt'); print(f'✓ Loaded {m.model_name}')"
```

## Success Criteria

- [ ] CCPD downloaded: 250K images in `~/.cache/anpr-datasets/ccpd/CCPD2019/`
- [ ] Dataset splits created: 150K train, 50K val, 50K test
- [ ] Training completed: 100 epochs
- [ ] **mAP@0.5 ≥ 0.92** ✓ (main gate)
- [ ] **mAP@0.75 ≥ 0.70** (secondary gate)
- [ ] **p95 latency <200ms** (on GPU: ~50–80ms)
- [ ] Model exported: `models/detector_prod.pt`
- [ ] Model loads without error

## Troubleshooting

### CCPD Download Fails

```bash
# Try partial download with wget/aria2:
aria2c -x 16 https://github.com/detectRecog/CCPD/releases/download/2019.06.27/CCPD2019.zip

# Or use a torrent/mirror if available
```

### Out of GPU Memory

Reduce batch size in `training/configs/detector.yaml`:

```yaml
detector:
  batch_size: 16  # Default 32
```

Then retry:

```bash
make m2-full
```

### Training Too Slow on CPU

Switch to GPU:

```yaml
detector:
  device: cuda:0  # Force CUDA
```

Or use a cloud GPU (Colab, AWS, GCP) for faster iteration.

### Model Accuracy Below Target

Common causes:

1. **CCPD not fully extracted** → verify 250K images present
2. **GPU out of memory** → reduce batch size
3. **Learning rate too high** → adjust `lr0` in detector.yaml
4. **Insufficient epochs** → ensure 100 epochs completed (check early stopping)

**Action:** Re-run with longer patience:

```yaml
detector:
  patience: 50  # Increase from 30
```

## Next Steps (M3+)

Once M2 completes with mAP≥0.92:

1. **M3 (Concurrent with M2):** OCR pipeline (PaddleOCR, TensorFlow)
2. **M4 (Dependent on M3):** Multi-backend ensemble (detection + OCR)
3. **M5 (Dependent on M4):** Real-time inference + tracking (ByteTrack)
4. **M7+ (Backend):** API deployment + WebSocket streaming

M2 training runs independently. M3–M5 can proceed in parallel without waiting.

---

**Questions?**
- Check `M2_BASELINE_REPORT.md` for baseline metrics
- Review `ML_SPEC.md` for full acceptance criteria
- See `DEMO.md` for end-to-end system walkthrough
