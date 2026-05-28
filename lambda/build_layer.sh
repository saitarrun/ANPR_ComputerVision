#!/bin/bash
# Build script for Lambda layer with dependencies
# Usage: bash lambda/build_layer.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
LAYER_DIR="${PROJECT_ROOT}/terraform/modules/lambda_rotate/.terraform/lambda-layer-build"
OUTPUT_ZIP="${PROJECT_ROOT}/terraform/modules/lambda_rotate/.terraform/lambda-layer.zip"

echo "Building Lambda layer with dependencies..."
echo "Project root: $PROJECT_ROOT"
echo "Layer directory: $LAYER_DIR"

# Clean up previous build
rm -rf "$LAYER_DIR"
mkdir -p "$LAYER_DIR/python/lib/python3.11/site-packages"

# Install dependencies
echo "Installing Python dependencies..."
pip install -r "$SCRIPT_DIR/requirements.txt" \
  --target "$LAYER_DIR/python/lib/python3.11/site-packages/" \
  --no-cache-dir \
  --quiet

# Verify installations
echo "Verifying installations..."
python3 -c "import psycopg2; print('✓ psycopg2 installed')" || exit 1
echo "✓ boto3 included in Lambda runtime"

# Create zip archive
echo "Creating zip archive..."
cd "$LAYER_DIR"
zip -r "$OUTPUT_ZIP" python/ > /dev/null 2>&1
cd - > /dev/null

echo "✓ Lambda layer built successfully: $OUTPUT_ZIP"
echo "Size: $(du -h "$OUTPUT_ZIP" | cut -f1)"
