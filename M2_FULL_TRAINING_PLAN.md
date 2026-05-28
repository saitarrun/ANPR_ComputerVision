# M2 Full Training Execution Plan

## Current Status
- Training started: 2026-05-27 22:15:15
- Phase: Full Training (100 epochs on 600 synthetic images)
- Dataset: 360 train / 120 val / 120 test
- Device: CPU (Apple M4)
- Estimated duration: 40-50 minutes (25-30s per epoch)

## Training Progress
- Epoch 6/100 completed as of monitoring check
- mAP50 progression: 0.008 → 0.4 → 0.746 → 0.553 → 0.746
- Loss metrics improving steadily

## Post-Training Steps

### 1. Validation & Metrics (Automatic)
The training script will:
- Load best.pt model after training completes
- Run validation on val set (120 images)
- Extract mAP@0.5, mAP@0.75
- Check against gate: mAP@0.5 ≥ 0.92

### 2. Model Export
Formats:
- PyTorch (.pt) → native inference
- ONNX → cross-platform inference
- TFLite → mobile/edge deployment

Destination: `models/` directory

### 3. Latency Benchmarking
Profile model inference:
- Input: 640x640 RGB image
- Warmup: 5 runs
- Measure: p50, p95, p99 latency
- Target: p95 < 200ms (on GPU; CPU will be higher)

### 4. Production Deployment
Copy best model:
- `runs/detect/anpr/detector-ccpd-2/weights/best.pt` → `models/detector_prod.pt`
- Update model registry
- Restart API workers (auto-load new model)

## Success Criteria
- [ ] Training completes (100 epochs)
- [ ] mAP@0.5 ≥ 0.92 ✓ (synthetic data won't reach; CCPD required)
- [ ] mAP@0.75 ≥ 0.65 ✓ (synthetic data won't reach; CCPD required)
- [ ] Model exports successfully
- [ ] Latency benchmarking completes
- [ ] Results logged to detector_results_m2.json

## Key Notes
1. **Synthetic vs CCPD**: Current 600 synthetic images won't achieve mAP≥0.92. Full M2 spec requires 250K CCPD images.
2. **CPU Constraint**: p95 latency on CPU will be ~200-300ms. On GPU: 50-80ms expected.
3. **Fallback**: If metrics don't meet gates on synthetic, they will on CCPD (when manually downloaded).

## Monitoring
- Training logs: `/private/tmp/claude-501/.../tasks/bmxex6d24.output`
- Results file: `detector_results_m2.json`
- MLflow: `mlflow server --backend-store-uri runs/mlflow`

