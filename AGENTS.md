# Working on Qayem

## Branches

Owner rule, 2026-11-21: work only on `main`. Do not create feature branches or worktrees;
commit directly to `main` and push `main` when asked. Staging (`bash scripts/deploy-cloudflare.sh staging`)
is the place to check a change before `production`.

## Where things are

- `README.md`: sources, CLI, pipeline.
- `docs/WEBSITE.md`, `docs/WEB_API.md`: the site and its API.
- `docs/CLOUDFLARE.md`, `docs/CLOUD_UPDATES.md`: deployment and the nightly updater.
- `docs/GROWTH.md`: page heads, leads, alerts, secrets, the funnel and the weekly content brief.

Run `.venv/bin/python -m pytest -q` and `npm --prefix web run build` before committing; the end-to-end
check is `QAYEM_WEB_URL=… npm --prefix web run test:e2e`.
