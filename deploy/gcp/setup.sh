#!/usr/bin/env bash
# Provisions this Debian 12 VM to run the IsMiseEanna Garmin MCP server
# behind Caddy (automatic HTTPS via Let's Encrypt) as a systemd service.
#
# Run as root on a fresh VM:
#   sudo ./setup.sh <public-hostname> [git-ref]
#
# <public-hostname> is what clients will connect to, e.g. an sslip.io
# hostname derived from this VM's static external IP: 34.71.12.9 becomes
# 34-71-12-9.sslip.io. It must match MCP_RESOURCE_URL and the resource
# indicator registered in WorkOS.
#
# Safe to re-run: it only creates /etc/ismiseeanna-mcp.env on the first run
# (never overwrites a real, already-edited one), and otherwise just
# re-syncs code/config and restarts services.
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Run this as root (sudo ./setup.sh <hostname> [git-ref])" >&2
  exit 1
fi

HOSTNAME_ARG="${1:?Usage: $0 <public-hostname> [git-ref]}"
GIT_REF="${2:-main}"
REPO_URL="https://github.com/EndaMurr/IsMiseEanna.git"
APP_DIR=/opt/ismiseeanna-mcp
DATA_DIR=/var/lib/ismiseeanna-mcp
APP_USER=ismiseeanna
ENV_FILE=/etc/ismiseeanna-mcp.env

echo "==> Installing Caddy (reverse proxy + automatic HTTPS)"
apt-get update -qq
apt-get install -y -qq debian-keyring debian-archive-keyring apt-transport-https curl git
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
  | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
  | tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null
chmod o+r /usr/share/keyrings/caddy-stable-archive-keyring.gpg
chmod o+r /etc/apt/sources.list.d/caddy-stable.list
apt-get update -qq
apt-get install -y -qq caddy

echo "==> Installing uv"
if [ ! -x /root/.local/bin/uv ]; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
UV_BIN=/root/.local/bin/uv

echo "==> Creating dedicated service user and data directory"
id -u "$APP_USER" &>/dev/null || useradd --system --create-home --home-dir "$DATA_DIR" "$APP_USER"
mkdir -p "$DATA_DIR"
chown "$APP_USER":"$APP_USER" "$DATA_DIR"

echo "==> Fetching application code (ref: $GIT_REF)"
if [ -d "$APP_DIR/.git" ]; then
  git -C "$APP_DIR" fetch origin "$GIT_REF"
  git -C "$APP_DIR" checkout "$GIT_REF"
  git -C "$APP_DIR" reset --hard "origin/$GIT_REF"
else
  git clone --branch "$GIT_REF" "$REPO_URL" "$APP_DIR"
fi
"$UV_BIN" --directory "$APP_DIR" sync --frozen --no-dev
chown -R "$APP_USER":"$APP_USER" "$APP_DIR"

if [ ! -f "$ENV_FILE" ]; then
  echo "==> Writing $ENV_FILE (first run - fill in real WorkOS/Garmin values before it can log in)"
  sed "s#REPLACE-WITH-YOUR-HOSTNAME#${HOSTNAME_ARG}#" \
    "$APP_DIR/deploy/gcp/ismiseeanna-mcp.env.example" > "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  NEEDS_EDIT=1
else
  echo "==> $ENV_FILE already exists, leaving it as-is"
  NEEDS_EDIT=0
fi

echo "==> Installing systemd service"
cp "$APP_DIR/deploy/gcp/ismiseeanna-mcp.service" /etc/systemd/system/ismiseeanna-mcp.service
systemctl daemon-reload
systemctl enable ismiseeanna-mcp
if [ "$NEEDS_EDIT" -eq 0 ]; then
  systemctl restart ismiseeanna-mcp
fi

echo "==> Installing Caddy reverse proxy config"
sed "s#REPLACE-WITH-YOUR-HOSTNAME#${HOSTNAME_ARG}#" "$APP_DIR/deploy/gcp/Caddyfile" > /etc/caddy/Caddyfile
systemctl reload caddy 2>/dev/null || systemctl restart caddy

echo
if [ "$NEEDS_EDIT" -eq 1 ]; then
  echo "==> Next step: edit $ENV_FILE with your real WORKOS_AUTHKIT_DOMAIN,"
  echo "    GARMIN_EMAIL and GARMIN_PASSWORD, then run:"
  echo "      systemctl restart ismiseeanna-mcp"
else
  echo "==> Done. Server should be reachable at: https://${HOSTNAME_ARG}/mcp"
fi
