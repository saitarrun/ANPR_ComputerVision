# M2: YOLOv8s Detector Fine-Tuning (5 days)

## Overview

Fine-tune YOLOv8s on multi-region plate datasets (CCPD + UFPR-ALPR + OpenALPR-EU + Roboflow) to achieve **mAP@0.5 ≥ 0.92** on held-out test set.

**Target:** 5-day sprint, daily milestones, gated by acceptance criteria.

---

## Acceptance Criteria (Gate for M3)

| Criterion | Target | Status |
|-----------|--------|--------|
| CCPD test mAP@0.5 | ≥0.92 | [ ] |
| CCPD test mAP@0.75 | ≥0.80 | [ ] |
| Cross-dataset: UFPR mAP@0.5 | ≥0.88 (tolerance: 4pt drop) | [ ] |
| Cross-dataset: OpenALPR-EU mAP@0.5 | ≥0.88 | [ ] |
| Latency p95 (640x480 inference) | <200ms | [ ] |
| ONNX export validates | Yes | [ ] |

---

## Data Preparation (Day 1)

### Step 1a: Obtain datasets

Download and extract to `~/.cache/anpr-datasets/`:

1. **CCPD** (250k): https://github.com/detectRecog/CCPD/releases
   - Extract to `~/.cache/anpr-datasets/CCPD2019/`
   - Subsets: `ccpd_base`, `ccpd_challenge`, `ccpd_weather`, `ccpd_night`

2. **UFPR-ALPR** (4.5k): https://web.inf.ufpr.br/vri/databases/ufpr-alpr/
   - Extract to `~/.cache/anpr-datasets/UFPR-ALPR/`

3. **OpenALPR-EU** (15k): https://github.com/openalpr/openalpr
   - Extract to `~/.cache/anpr-datasets/OpenALPR-EU/`

4. **Roboflow** (5k): https://roboflow.com (free tier, license plate dataset)
   - Extract to `~/.cache/anpr-datasets/Roboflow-LicensePlate/`

### Step 1b: Prepare splits

```bash
python training/data/prepare_splits.py --cache ~/.cache/anpr-datasets
```

### Step 1c: Create golden test sets

```bash
python benchmarks/golden_sets.py
```

---

## Training (Days 2-4)

### Phase 1: Baseline (Day 2)

```bash
python training/scripts/train_detector_m2.py --phase baseline
```

### Phase 2: Full Training (Days 3-4)

```bash
python training/scripts/train_detector_m2.py --phase full
```

### Both phases combined:

```bash
python training/scripts/train_detector_m2.py --phase all
```

---

## Evaluation (Day 5)

```bash
python benchmarks/eval_m2.py --set golden_in_small --model runs/detect/detector-v1/weights/best.pt
```

---

## Make Targets (Quick Reference)

```bash
make m2-setup       # Initialize golden sets
make m2-baseline    # Phase 1: baseline training
make m2-full        # Phase 2: full training
make m2-train       # Both phases
make m2-eval        # Evaluate on golden sets
make m2-mlflow      # View MLflow UI
```

---

**Status:** ⏳ In Progress (M2: 2026-05-27 → 2026-06-01)
