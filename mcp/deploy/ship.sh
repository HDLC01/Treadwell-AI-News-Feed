#!/usr/bin/env bash
# Off-box deploy for the News Feed Connector (standalone MCP stack).
#
# The VPS is 1 core / 2 GB; building on it browns out every site. Build the
# image HERE, ship it over SSH, push the compose file (the VPS dir is NOT a git
# checkout), then load + restart (NO --build). Bringing the connector up/down
# never touches the running feed container.
#
# Prereqs: local Docker engine running; SSH key at ~/.ssh/treadwell_vps.
# Usage:   bash mcp/deploy/ship.sh   (run from the News Feed repo root)
set -euo pipefail

VPS_HOST="${VPS_HOST:-50.6.110.215}"
VPS_USER="${VPS_USER:-root}"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/treadwell_vps}"
APP_DIR="/opt/treadwell-newsfeed-connector"
IMAGE="treadwell-newsfeed-connector:latest"
COMPOSE="docker-compose.yml"
SSH=(ssh -i "$SSH_KEY" -o ConnectTimeout=20 "${VPS_USER}@${VPS_HOST}")

cd "$(dirname "$0")/.."   # -> the mcp/ build context

echo "==> Building $IMAGE locally (off the prod box)…"
docker build --platform linux/amd64 -t "$IMAGE" .

echo "==> Shipping image + compose over SSH…"
docker save "$IMAGE" | gzip | "${SSH[@]}" "cat > /tmp/connector.tar.gz"
scp -i "$SSH_KEY" "$COMPOSE" "${VPS_USER}@${VPS_HOST}:$APP_DIR/$COMPOSE.new"

echo "==> Load + restart on the VPS (NO build)…"
"${SSH[@]}" "set -euo pipefail
  cd $APP_DIR
  cp -f $COMPOSE $COMPOSE.bak 2>/dev/null || true
  mv -f $COMPOSE.new $COMPOSE
  gunzip -c /tmp/connector.tar.gz | docker load
  rm -f /tmp/connector.tar.gz
  docker compose up -d
  for i in \$(seq 1 24); do
    if curl -fsS http://localhost:8894/healthz >/dev/null; then echo '   connector healthy'; exit 0; fi
    sleep 5
  done
  echo '   post-deploy healthcheck failed'; exit 1
"
echo "==> Done — connector.wetreadwell.com is on the freshly-shipped image."
