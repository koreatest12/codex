#!/usr/bin/env bash
# Ubuntu Server only; no Docker TCP socket or firewall changes.
set -euo pipefail

if [[ "$EUID" -ne 0 ]]; then
  echo "Run with sudo: sudo bash scripts/install-docker-ubuntu.sh" >&2
  exit 1
fi

if [[ ! -r /etc/os-release ]]; then
  echo "Unable to detect operating system" >&2
  exit 1
fi
# shellcheck disable=SC1091
source /etc/os-release
if [[ "${ID:-}" != "ubuntu" ]]; then
  echo "This installer supports Ubuntu Server only." >&2
  exit 1
fi

if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  echo "Docker Engine and Compose are already running; no changes needed."
  docker --version
  docker compose version
  exit 0
fi

# Do not overwrite a host's existing Docker apt repository configuration.
if [[ -e /etc/apt/sources.list.d/docker.sources ]]; then
  echo "Existing docker.sources found; review it manually before installation." >&2
  exit 1
fi

echo "==> Installing prerequisites"
apt-get update
apt-get install -y ca-certificates curl

echo "==> Registering the official Docker apt repository"
install -m 0755 -d /etc/apt/keyrings
curl --fail --silent --show-error --location \
  https://download.docker.com/linux/ubuntu/gpg \
  --output /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc

arch="$(dpkg --print-architecture)"
codename="${UBUNTU_CODENAME:-${VERSION_CODENAME:-}}"
if [[ -z "$codename" ]]; then
  echo "Ubuntu codename not found" >&2
  exit 1
fi

cat > /etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: ${codename}
Components: stable
Architectures: ${arch}
Signed-By: /etc/apt/keyrings/docker.asc
EOF

echo "==> Installing Docker Engine, Buildx and Compose plugin"
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker

docker version
docker buildx version
docker compose version
echo "Docker Engine setup finished. Docker daemon access remains privileged."
