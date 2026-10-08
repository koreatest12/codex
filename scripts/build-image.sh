#!/usr/bin/env bash
set -euo pipefail

image="${SERVER_IMAGE:-codex-linux-server:latest}"
base="${LINUX_IMAGE:-ubuntu:latest}"

if ! command -v docker >/dev/null 2>&1 || ! docker info >/dev/null 2>&1; then
  echo "Docker Engine must be running to build images." >&2
  exit 1
fi

echo "==> Building ${image} from ${base}"
docker build --pull --file Dockerfile --build-arg "BASE_IMAGE=${base}" --tag "$image" .

echo "==> Verifying safe project packaging and unit tests"
docker run --rm --entrypoint /bin/bash "$image" -euc '
  for path in \
    /opt/codex-source/README.md \
    /opt/codex-source/docs/DOCKER_OPERATIONS.md \
    /opt/codex-source/app/server.py \
    /opt/codex-source/java-biff-planner/pom.xml \
    /opt/codex-source/.github/workflows/docker-image-ci.yml \
    /opt/codex-source/data/biff-2026/seed.json; do
    test -f "$path"
  done
  for path in /opt/codex-source/.git /opt/codex-source/.env \
              /opt/codex-source/secrets /opt/codex-source/.ci-secrets \
              /opt/codex-source/app/__pycache__; do
    test ! -e "$path"
  done
  PYTHONPATH=/opt/app /opt/venv/bin/python -m unittest discover -s /opt/codex-source/tests -v
  java -jar /opt/java-biff-planner/target/biff-planner-1.0.0.jar toolchain
'
echo "Image build and verification completed: ${image}"
