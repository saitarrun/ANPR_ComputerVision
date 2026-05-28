#!/usr/bin/env bash

set -euo pipefail

# ANPR Docker build and push script for CI/CD
# Usage: ./scripts/docker-build.sh [OPTIONS]
#
# OPTIONS:
#   --registry REGISTRY    Docker registry (default: docker.io)
#   --image IMAGE          Image name (default: anpr-backend)
#   --tag TAG              Image tag (default: git commit hash)
#   --push                 Push to registry after build
#   --no-cache             Skip Docker layer cache
#   --dry-run              Show commands without executing

REGISTRY="${REGISTRY:-docker.io}"
IMAGE="${IMAGE:-anpr-backend}"
TAG="${TAG:-}"
PUSH=false
NO_CACHE=""
DRY_RUN=false

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --registry) REGISTRY="$2"; shift 2 ;;
    --image) IMAGE="$2"; shift 2 ;;
    --tag) TAG="$2"; shift 2 ;;
    --push) PUSH=true; shift ;;
    --no-cache) NO_CACHE="--no-cache"; shift ;;
    --dry-run) DRY_RUN=true; shift ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

# Determine tag: git commit hash by default, or explicit tag
if [[ -z "$TAG" ]]; then
  TAG=$(git rev-parse --short HEAD)
  # Add -dirty suffix if working tree has uncommitted changes
  if ! git diff-index --quiet HEAD --; then
    TAG="${TAG}-dirty"
  fi
fi

FULL_IMAGE="${REGISTRY}/${IMAGE}:${TAG}"
FULL_IMAGE_LATEST="${REGISTRY}/${IMAGE}:latest"

echo "Build Configuration"
echo "==================="
echo "Registry:     $REGISTRY"
echo "Image:        $IMAGE"
echo "Tag:          $TAG"
echo "Full image:   $FULL_IMAGE"
echo "Push:         $PUSH"
echo "No cache:     $([ -z "$NO_CACHE" ] && echo 'false' || echo 'true')"
echo ""

# Build
BUILD_CMD="docker build -t $FULL_IMAGE -t $FULL_IMAGE_LATEST -f Dockerfile . $NO_CACHE"

if [[ "$DRY_RUN" == "true" ]]; then
  echo "[DRY RUN] $BUILD_CMD"
else
  echo "Building Docker image..."
  eval "$BUILD_CMD"
  echo "✓ Build successful: $FULL_IMAGE"
fi

# Push (optional)
if [[ "$PUSH" == "true" ]]; then
  PUSH_CMD="docker push $FULL_IMAGE && docker push $FULL_IMAGE_LATEST"
  
  if [[ "$DRY_RUN" == "true" ]]; then
    echo "[DRY RUN] $PUSH_CMD"
  else
    echo "Pushing to registry..."
    eval "$PUSH_CMD"
    echo "✓ Push successful"
  fi
fi

# Output image reference for downstream CI/CD
echo ""
echo "Image Reference"
echo "==============="
echo "$FULL_IMAGE"
