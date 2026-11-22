# Working on Qayem

## Branches

Owner rule, 2026-11-21: work only on `main`. Do not create feature branches or worktrees;
commit directly to `main` and push `main` when asked. Staging (`bash scripts/deploy-cloudflare.sh staging`)
is the place to check a change before `production`.

## Computer use

Owner rule, 2026-11-22: computer use runs only in the isolated Linux VM `computer-use` (OrbStack,
driven by `cua-driver` through `~/.local/bin/vm-cu`, Qayem's Brave profile via `vm-cu brave qayem`),
never on the Mac's own desktop or browser. Every step holds content-engine's shared desktop lock:
`cd ~/projects/content-engine && .venv/bin/python -m studio.desktop_lock run --brand qayem --owner <who> --task <task> --wait <s> -- <cmd>`;
exit 75 means it was not taken, so do no computer use. A missing VM, driver or profile is a blocker
to report, never a reason to fall back to the Mac. Details: `docs/STRATEGY.md` section 5.4.

## Where things are

- `README.md`: sources, CLI, pipeline.
- `docs/WEBSITE.md`, `docs/WEB_API.md`: the site and its API.
- `docs/CLOUDFLARE.md`, `docs/CLOUD_UPDATES.md`: deployment and the nightly updater.
- `docs/GROWTH.md`: page heads, leads, alerts, secrets, the funnel and the weekly content brief.
- `docs/STRATEGY.md`: the direction from 2026-11-22: Egypt-wide price guide, data sources, map, article agent, SEO/GEO.
- `docs/PRICE_GUIDE.md`: how it is built: market districts, dedupe, segments, the Qayem Index, CBE rates, developer
  reports, the map, the article agent (`qayem articles`, agy `gemini-4-neon` medium), WhatsApp intake and observations.

Run `.venv/bin/python -m pytest -q` and `npm --prefix web run build` before committing; the end-to-end
check is `QAYEM_WEB_URL=… npm --prefix web run test:e2e`.
