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
7. Retain every created container, including after a failed verification.

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

### Container preservation

The deployment script never deletes, stops, restarts, or replaces an existing
container. If `CONTAINER_NAME` already exists, including a stopped container, it
exits before pulling or building. Failures to list containers also stop deployment.
A simultaneous attempt to claim the same name fails safely at Docker's create step.
All later checks use the newly created container ID, never the name.

New containers are retained after success or failure. If a port is occupied or a
health check fails, use the printed ID to inspect the retained container. The legacy
`CLEANUP_AFTER_TEST` variable is ignored with a warning, even when set to `true`.
There is no automatic cleanup or implicit replacement option.

To test alongside an existing server, first select a new container name, a separate
image tag, and an unused host port. For example, after verifying these are free:

```bash
CONTAINER_NAME=codex-linux-server-check-1 \
SERVER_IMAGE=codex-linux-server:check-1 \
HOST_PORT=9090 \
bash scripts/deploy-container-server.sh
```

Do not reuse that name for another run. Inspect existing containers without changing
them:

```bash
docker ps -a --filter 'name=^/codex-linux-server$'
docker container inspect --format 'ID={{.Id}} Status={{.State.Status}}' codex-linux-server
```

The base-image smoke test also retains its container, which normally exits after
the test command completes. Retention uses disk space; container removal is always
a separate, explicit operator decision.

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

Compose has a different lifecycle from the preservation-first script above.
`docker compose up --build` can recreate a Compose-managed container. Do not use
it to test this fix or update an existing deployment when containers must be kept.
For a separate, new deployment only, use a unique project name, container name,
image tag, and unused port; merely changing the project name is insufficient
because this file declares `container_name` explicitly.

Create a separate Compose deployment only after confirming those values are free:

```bash
CONTAINER_NAME=codex-linux-server-compose-check-1 \
SERVER_IMAGE=codex-linux-server:compose-check-1 \
HOST_PORT=9091 \
docker compose -p codex-check-1 up -d --build
```

Check status:

```bash
docker compose -p codex-check-1 ps
```

View logs:

```bash
docker compose -p codex-check-1 logs -f
```

Avoid `docker compose down` when preserving containers: it removes the project's containers.

## Customize

Use another compatible Ubuntu/Debian image (the Dockerfile requires `apt-get`):

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

## Safety regression tests

Run without Docker or network access:

```bash
python3 -m unittest discover -s tests -v
bash -n scripts/deploy-container-server.sh scripts/run-latest-linux.sh
```

The regression suite uses a strict mock Docker executable. It covers early failures,
existing names, a name-claim race, container-ID targeting, success and failure
retention, and the old cleanup flag. It does not run or remove real containers.
GitHub Actions runs these tests before its separate live build-and-run checks on
an ephemeral GitHub-hosted runner. Each workflow run uses its own container name
and image tag, and neither script requests container removal. CI containers exist
only for the lifetime of that runner; runner teardown is not persistent storage.
