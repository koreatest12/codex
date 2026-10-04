# codex

Latest Ubuntu image download, container server build, and runtime verification automation.

## Architecture

The repository now performs the full container-server flow:

1. Pull the official `ubuntu:latest` base image.
2. Verify the Linux image and print OS/architecture/kernel information.
3. Build a new Ubuntu-based Nginx server image from `Dockerfile`.
4. Start the server container.
5. Verify `/healthz`.
6. Verify the web page response.
7. Keep the container running locally, or clean it up automatically in CI.

## Container server

Default values:

- Base image: `ubuntu:latest`
- Server image: `codex-linux-server:latest`
- Container name: `codex-linux-server`
- Container port: `8080`
- Local bind address: `127.0.0.1`
- Local URL: `http://127.0.0.1:8080`
- Health check: `http://127.0.0.1:8080/healthz`

The image installs Nginx, curl, and CA certificates on top of the current Ubuntu base image.

## Build and deploy locally

Requirements:

- Docker
- Bash

Run the complete download/build/start/verify flow:

```bash
chmod +x scripts/deploy-container-server.sh
./scripts/deploy-container-server.sh
```

After successful deployment:

```text
http://127.0.0.1:8080
```

Check health:

```bash
curl http://127.0.0.1:8080/healthz
```

Expected response:

```text
ok
```

## Docker Compose

Build and run persistently:

```bash
docker compose up -d --build
```

Check status:

```bash
docker compose ps
```

View logs:

```bash
docker compose logs -f
```

Stop the server:

```bash
docker compose down
```

## Customize

Use another Ubuntu/Linux image:

```bash
LINUX_IMAGE=ubuntu:rolling ./scripts/deploy-container-server.sh
```

Change the host port:

```bash
HOST_PORT=9090 ./scripts/deploy-container-server.sh
```

Change the built image name:

```bash
SERVER_IMAGE=my-linux-server:latest ./scripts/deploy-container-server.sh
```

## Base image smoke test only

```bash
chmod +x scripts/run-latest-linux.sh
./scripts/run-latest-linux.sh
```

## GitHub Actions

The `Latest Linux Image and Container Server` workflow automatically:

1. Pulls `ubuntu:latest`.
2. Runs the base Linux smoke test.
3. Builds the Nginx server image.
4. Starts the server container.
5. Checks the health endpoint.
6. Checks the web page.
7. Confirms the final server image was built successfully.

The workflow runs on relevant pushes and pull requests, can be started manually, and performs a weekly refresh/build verification.
