#!/bin/bash
# Post-training M2 pipeline: evaluation, export, benchmarking, deployment

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$PROJECT_ROOT"

echo "======================================================================"
echo "M2 POST-TRAINING PIPELINE"
echo "======================================================================"
echo ""

# Configuration
MODEL_PATH="runs/detect/anpr/detector-ccpd/weights/best.pt"
EXPORT_DIR="models"
RESULTS_FILE="detector_results_m2.json"

# Step 1: Verify model exists
echo "Step 1: Verifying trained model..."
if [ ! -f "$MODEL_PATH" ]; then
    echo "ERROR: Model not found at $MODEL_PATH"
    exit 1
fi
echo "✓ Model found: $MODEL_PATH"
ls -lh "$MODEL_PATH"
echo ""

# Step 2: Export model
echo "Step 2: Exporting model to production formats..."
python training/scripts/train_detector_m2.py --phase full 2>&1 | grep -E "✓|✗|export|Export" || true
echo ""

# Step 3: Copy to production
echo "Step 3: Deploying to production..."
mkdir -p "$EXPORT_DIR"
cp "$MODEL_PATH" "$EXPORT_DIR/detector_prod.pt"
echo "✓ Copied to $EXPORT_DIR/detector_prod.pt"
ls -lh "$EXPORT_DIR/detector_prod.pt"
echo ""

# Step 4: Verify production model loads
echo "Step 4: Verifying production model..."
python -c "
from ultralytics import YOLO
try:
    model = YOLO('$EXPORT_DIR/detector_prod.pt')
    print(f'✓ Production model loaded successfully: {model.model_name}')
except Exception as e:
    print(f'✗ Failed to load production model: {e}')
    exit(1)
"
echo ""

# Step 5: Benchmark latency
echo "Step 5: Benchmarking inference latency..."
python training/scripts/benchmark_latency.py \
    --model "$MODEL_PATH" \
    --dataset ~/.cache/anpr-datasets \
    --num-runs 100
echo ""

# Summary
echo "======================================================================"
echo "M2 POST-TRAINING COMPLETE"
echo "======================================================================"
echo ""
echo "Key Artifacts:"
echo "  - Trained model: $MODEL_PATH"
echo "  - Production model: $EXPORT_DIR/detector_prod.pt"
echo "  - Training results: $RESULTS_FILE"
echo "  - Latency benchmark: benchmark_latency_m2.json"
echo ""
echo "Next steps:"
echo "  1. Review detector_results_m2.json for mAP metrics"
echo "  2. Check benchmark_latency_m2.json for latency SLA"
echo "  3. Restart API workers: make restart-api"
echo "  4. Run end-to-end tests: make test-int"
echo ""
