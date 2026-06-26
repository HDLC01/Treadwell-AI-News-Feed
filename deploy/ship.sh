#!/usr/bin/env bash
# Off-box deploy for the Treadwell AI News Feed.
#
# The VPS is 1 core / 2 GB; building on it browns out every site. Build the
# image HERE, ship it over SSH, push the compose file (the VPS dir is NOT a git
# checkout), then load + restart (NO --build).
#
# Prereqs: local Docker engine running; SSH key at ~/.ssh/treadwell_vps.
# Usage:   bash deploy/ship.sh
set -euo pipefail

VPS_HOST="${VPS_HOST:-50.6.110.215}"
VPS_USER="${VPS_USER:-root}"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/treadwell_vps}"
APP_DIR="/opt/treadwell-newsfeed"
IMAGE="treadwell-newsfeed:latest"
COMPOSE="docker-compose.yml"
SSH=(ssh -i "$SSH_KEY" -o ConnectTimeout=20 "${VPS_USER}@${VPS_HOST}")

cd "$(dirname "$0")/.."

echo "==> Building $IMAGE locally (off the prod box)…"
docker build --platform linux/amd64 -t "$IMAGE" .

echo "==> Shipping image + compose over SSH…"
docker save "$IMAGE" | gzip | "${SSH[@]}" "cat > /tmp/newsfeed.tar.gz"
scp -i "$SSH_KEY" "$COMPOSE" "${VPS_USER}@${VPS_HOST}:$APP_DIR/$COMPOSE.new"

echo "==> Load + restart on the VPS (NO build)…"
"${SSH[@]}" "set -euo pipefail
  cd $APP_DIR
  cp -f $COMPOSE $COMPOSE.bak 2>/dev/null || true
  mv -f $COMPOSE.new $COMPOSE
  gunzip -c /tmp/newsfeed.tar.gz | docker load
  rm -f /tmp/newsfeed.tar.gz
  docker compose up -d
  for i in \$(seq 1 24); do
    if curl -fsS http://localhost:8890/api/health >/dev/null; then echo '   newsfeed healthy'; exit 0; fi
    sleep 5
  done
  echo '   post-deploy healthcheck failed'; exit 1
"
echo "==> Done — newsfeed.wetreadwell.com is on the freshly-shipped image."
