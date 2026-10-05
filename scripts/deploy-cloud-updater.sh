#!/usr/bin/env bash
set -euo pipefail
QAYEM_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$QAYEM_ROOT"
.venv/bin/python -m pytest -q tests/test_cloud_pipeline.py tests/test_cloudflare.py tests/test_ai.py
npm --prefix cloudflare/updater ci
npm --prefix cloudflare/updater run check
npm --prefix cloudflare/updater test
# Use an isolated Docker configuration; preserve the user's other registry logins.
export DOCKER_HOST="$(docker context inspect --format '{{ .Endpoints.docker.Host }}')"
export DOCKER_CONFIG="$QAYEM_ROOT/.artifacts/updater-docker"
mkdir -p "$DOCKER_CONFIG/cli-plugins"
# A registry placeholder prevents Docker from auto-selecting the locked macOS
# credential helper. Wrangler obtains a short-lived registry token at deploy time.
clear_registry_credentials() {
  (umask 077; printf '{"auths": {"registry.cloudflare.com": {}}}\n' > "$DOCKER_CONFIG/config.json")
}
clear_registry_credentials
trap clear_registry_credentials EXIT
if [[ -x "$HOME/.docker/cli-plugins/docker-buildx" ]]; then
  ln -sf "$HOME/.docker/cli-plugins/docker-buildx" "$DOCKER_CONFIG/cli-plugins/docker-buildx"
fi
cd cloudflare/updater
npx wrangler deploy
cd "$QAYEM_ROOT"
.venv/bin/python scripts/cloud-updater.py secrets
