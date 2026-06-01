#!/usr/bin/env bash
# Fix apt (VS Code / Microsoft repo GPG) and install cloudflared via apt.
# Does NOT configure or start any tunnel.
# Usage: bash scripts/install-cloudflared-apt.sh

set -euo pipefail

if [[ "${EUID:-0}" -ne 0 ]]; then
  echo "Run with sudo: sudo bash scripts/install-cloudflared-apt.sh"
  exit 1
fi

echo "==> Fixing Microsoft (VS Code) apt signing key..."
curl -fsSL https://packages.microsoft.com/keys/microsoft.asc \
  | gpg --dearmor -o /usr/share/keyrings/microsoft.gpg
chmod 644 /usr/share/keyrings/microsoft.gpg

if [[ ! -f /etc/apt/sources.list.d/cloudflared.list ]]; then
  echo "==> Adding Cloudflare cloudflared apt repository..."
  curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg \
    | gpg --dearmor -o /usr/share/keyrings/cloudflare-main.gpg
  echo 'deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared jammy main' \
    > /etc/apt/sources.list.d/cloudflared.list
fi

echo "==> apt update..."
apt-get update

echo "==> Installing cloudflared only..."
apt-get install -y cloudflared

echo "==> Done. Version:"
cloudflared --version
echo "No tunnel was created or started."
