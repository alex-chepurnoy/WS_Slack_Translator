#!/usr/bin/env bash
set -euo pipefail

REPO="achepw0wz/wowza-webhook-to-slack"
IMAGE_BASE="wowza-webhook-to-slack"

echo "Logging in to Docker Hub (repo: $REPO)" >&2
docker login

echo "Building local image (tag: $REPO:latest)" >&2
docker build -t "$REPO:latest" .

echo "Tagging production variant ($REPO:prod)" >&2
docker tag "$REPO:latest" "$REPO:prod"

echo "Pushing latest tag" >&2
docker push "$REPO:latest"

echo "Pushing prod tag" >&2
docker push "$REPO:prod"

echo "Done. Available tags: latest, prod" >&2
