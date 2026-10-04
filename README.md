# codex

Latest Linux image download and smoke-test automation.

## Default image

This repository uses the official Ubuntu Docker image:

```text
ubuntu:latest
```

`ubuntu:latest` tracks Ubuntu's latest LTS image. The image is pulled fresh on each run.

## Run locally

Requirements:

- Docker
- Bash

Run:

```bash
chmod +x scripts/run-latest-linux.sh
./scripts/run-latest-linux.sh
```

Use another Linux container image if needed:

```bash
LINUX_IMAGE=ubuntu:rolling ./scripts/run-latest-linux.sh
```

## GitHub Actions

The `Latest Linux Image` workflow:

1. Pulls the current `ubuntu:latest` image.
2. Prints the resolved image digest.
3. Starts the container.
4. Prints OS, architecture, and kernel information.
5. Verifies the container can execute commands successfully.

It runs on relevant pushes, can be started manually, and performs a weekly refresh check.
