#!/usr/bin/env bash
set -euo pipefail
QAYEM_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$QAYEM_ROOT"
QAYEM_DEPLOY_ENV="${1:-production}"
case "$QAYEM_DEPLOY_ENV" in
  production) QAYEM_ASSETS_DIR="$QAYEM_ROOT/web/dist" ;;
  staging) QAYEM_ASSETS_DIR="$QAYEM_ROOT/web/dist-staging" ;;
  *) echo 'Usage: bash scripts/deploy-cloudflare.sh [staging|production]' >&2; exit 2 ;;
esac
if [[ -x "$QAYEM_ROOT/.artifacts/cloudflare-tools/bin/uv" ]]; then
  export PATH="$QAYEM_ROOT/.artifacts/cloudflare-tools/bin:$PATH"
fi
.venv/bin/python - "$QAYEM_DEPLOY_ENV" <<'PY'
import sys
from pathlib import Path
from qayem.cloud_development import deployment_binding
binding = deployment_binding(Path.cwd(), sys.argv[1])
if binding['database_id'] == '00000000-0000-0000-0000-000000000000':
    raise SystemExit('Configure the actual Cloudflare account_id and D1 database_id before deployment.')
PY
.venv/bin/python -m pytest -q
npm --prefix web ci
npm --prefix web run build -- --outDir "$QAYEM_ASSETS_DIR"
if [[ "$QAYEM_DEPLOY_ENV" == "staging" ]]; then
  .venv/bin/python - "$QAYEM_ASSETS_DIR" <<'PY'
from pathlib import Path
import sys
assets = Path(sys.argv[1])
index = assets / 'index.html'
index.write_text(index.read_text().replace('<head>', '<head>\n    <meta name="robots" content="noindex,nofollow" />').replace('<title>', '<title>[Staging] '))
(assets / '_headers').write_text('/*\n  X-Robots-Tag: noindex, nofollow\n  X-Qayem-Environment: staging\n')
PY
elif [[ "${QAYEM_LOCAL_PUBLISH:-0}" == "1" ]]; then
  .venv/bin/python scripts/cloudflare-sync.py
else
  echo "Using the active Cloudflare dataset; local publication requires QAYEM_LOCAL_PUBLISH=1."
fi
cd cloudflare
uv sync --locked
python3 prepare.py --assets-dir "$QAYEM_ASSETS_DIR"
if [[ "$QAYEM_DEPLOY_ENV" == "staging" ]]; then
  uv run pywrangler deploy --env staging
  cd "$QAYEM_ROOT"
  .venv/bin/python scripts/cloud-dev.py verify
else
  uv run pywrangler deploy
fi
