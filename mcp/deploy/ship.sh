#!/usr/bin/env bash
# Off-box deploy for the News Feed Connector (standalone MCP stack).
#
# The VPS is 1 core / 2 GB; building on it browns out every site. Build the
# image HERE, ship it over SSH, push the compose file (the VPS dir is NOT a git
# checkout), then load + restart (NO --build). Bringing the connector up/down
# never touches the running feed container.
#
# Prereqs: local Docker engine running; the `treadwell-vps` alias in ~/.ssh/config.
#          The alias supplies the host, port, user and key. It logs in as hanztwell,
#          and the box runs every command, scp and stdin as root via sudo.
# Usage:   bash mcp/deploy/ship.sh   (run from the News Feed repo root)
#          VPS_HOST alone names a Host entry from ~/.ssh/config. To aim at a raw
#          address instead, also set VPS_USER and SSH_KEY (no root@, no default key).
set -euo pipefail

VPS_HOST="${VPS_HOST:-treadwell-vps}"
VPS_USER="${VPS_USER:-}"
SSH_KEY="${SSH_KEY:-}"
APP_DIR="/opt/treadwell-newsfeed-connector"
IMAGE="treadwell-newsfeed-connector:latest"
COMPOSE="docker-compose.yml"
SSH_OPTS=(-o ConnectTimeout=20)
if [ -n "$SSH_KEY" ]; then SSH_OPTS+=(-i "$SSH_KEY"); fi
TARGET="${VPS_USER:+${VPS_USER}@}${VPS_HOST}"
SSH=(ssh "${SSH_OPTS[@]}" "$TARGET")

cd "$(dirname "$0")/.."   # -> the mcp/ build context

echo "==> Building $IMAGE locally (off the prod box)…"
docker build --platform linux/amd64 -t "$IMAGE" .

echo "==> Shipping image + compose over SSH…"
docker save "$IMAGE" | gzip | "${SSH[@]}" "cat > /tmp/connector.tar.gz"
scp "${SSH_OPTS[@]}" "$COMPOSE" "$TARGET:$APP_DIR/$COMPOSE.new"

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
