# Cloudflare deployment

Qayem's public backend is an async Python Worker with a dedicated D1 database,
`qayem-public`. Workers Static Assets serves the React build on the same origin.
The website uses the existing `/api/*` contract. The Worker runs the same Python
comparison functions as the local API; no second valuation implementation is maintained.

Crawling, Pi enrichment (`zai-coding-cn/glm-5.3-flash`) and entity resolution run
in the separate Cloudflare update service described in
[CLOUD_UPDATES.md](CLOUD_UPDATES.md). Private R2 checkpoints preserve the canonical
SQLite database, including raw source payloads and change history. D1 contains
the sanitized public read model, developer-price benchmarks and the internal
records needed for comparison. Only the update service receives the selected
GLM key as a Worker secret. The public API Worker and D1 receive no Pi credentials.

## Development and staging

Production is `https://qayem.ai`. Staging is
`https://qayem-staging.qayem-ai.workers.dev`, backed by the separate `qayem-staging`
D1 database. Both use the existing Cloudflare account and Workers subscription;
their usage shares the account's allowances. Staging has no custom production
domains, scheduled jobs, update container or AI credentials. Its HTML and API
identify it as staging and send `noindex` headers.

Work on a Git branch, develop locally, deploy that branch to staging, check it,
then release the approved code to production. The cloud updater owns production
data. Website releases use its latest active dataset.

From the repository root, pull a verified copy of the saved cloud database:

```sh
.venv/bin/python scripts/cloud-dev.py pull
```

This downloads the private R2 checkpoint into the ignored
`.artifacts/development/qayem.db`, preserving the existing local `qayem.db`.
Checksums and SQLite integrity are verified before replacement. The copy includes
saved enrichment and entity results; pulling does not crawl or call AI. Repeating
the command checks the small current-pointer object and skips the checkpoint
download when it is unchanged.

Run the API and frontend in separate terminals:

```sh
QAYEM_DB="$PWD/.artifacts/development/qayem.db" .venv/bin/python -m uvicorn qayem.web:app --reload --host 127.0.0.1 --port 8000
npm --prefix web run dev
```

Open `http://127.0.0.1:5174`. Vite forwards `/api` to the local API. Refresh the
development copy manually when newer cloud data is needed.

Publish copied data and the current branch's website to staging:

```sh
.venv/bin/python scripts/cloud-dev.py refresh
bash scripts/deploy-cloudflare.sh staging
QAYEM_WEB_URL=https://qayem-staging.qayem-ai.workers.dev npm --prefix web run test:e2e
```

`refresh` reads the saved cloud checkpoint and exports a sanitized public dataset
to staging only. It skips another D1 publication if the source snapshot, Python
comparison/export code and filters are unchanged and that version is still active.
Python comparison changes or new data require a fresh projection; frontend-only
changes need only the deployment command. Refreshes
are manual and never run another crawl, enrichment or production publication.
Separate staging assets and import artifacts prevent staging builds from
overwriting the production build. Deployment runs Python tests, the frontend
typecheck/build and live staging identity, catalogue and isolation checks.

After reviewing staging, release website code with:

```sh
bash scripts/deploy-cloudflare.sh production
```

This updates the production Worker and assets while continuing to use production's
active cloud dataset. Changes to crawling, enrichment or comparison code also
require deploying the updater and publishing a new projection; follow
[CLOUD_UPDATES.md](CLOUD_UPDATES.md). Avoid local production publication during
ordinary development. No automatic Git push or production release is configured.

## Local Worker verification

```sh
# From the repository root
uv pip install --python .venv/bin/python -e '.[dev,web]'
cd web
npm ci
npm run build
cd ..
.venv/bin/python scripts/cloud-dev.py pull
.venv/bin/python scripts/cloudflare-sync.py --local --database .artifacts/development/qayem.db
cd cloudflare
uv sync
python3 prepare.py
uv run pywrangler dev --port 8788
```

The Python Workers SDK requires uv >=0.12.3. Use a current uv installation; the
migration's isolated tool copy is `.artifacts/cloudflare-tools/bin/uv`.
`prepare.py` copies the shared comparison/API source into an ignored build directory;
run it after Python changes. `python_modules/`, `.venv-workers/` and `.wrangler/`
are generated tooling and are not committed. `uv.lock` and `pylock.toml` pin dependencies.

Verify `http://localhost:8788/api/health` and open `http://localhost:8788/`.
`QAYEM_WEB_URL=http://localhost:8788 npm run test:e2e` in `web/` checks the UI.

## Account deployment

1. Sign in with Wrangler. The account must be the account intended for Qayem.
2. Create or reuse the Qayem database:
   `npx wrangler@4.147.0 d1 create qayem-public` in `cloudflare/`.
3. Put the returned database ID and the chosen `account_id` in `wrangler.jsonc`.
   The all-zero ID is only a local development placeholder.
4. Publish production data from the repository root:
   `.venv/bin/python scripts/cloudflare-sync.py`.
5. In `cloudflare/`, run `python3 prepare.py`, then `uv run pywrangler deploy`.
   For subsequent releases, `bash scripts/deploy-cloudflare.sh` from the root
   runs tests, builds and deploys the Worker using the active cloud dataset.
   For an intentional initial seed or recovery from the local database, set
   `QAYEM_LOCAL_PUBLISH=1`; ordinary website releases do not publish local data.
6. Verify the generated workers.dev URL: health, catalogue, list, detail, lookup,
   compound/developer pages and comparisons. Then bind `qayem.ai` as a Worker
   custom domain once that zone is active in this Cloudflare account. If DNS is
   elsewhere, nameserver/domain verification must be completed first.

The account plan, remote database and domain are external deployment state;
configuration files alone do not confirm a production deployment. No subscription
upgrade is performed by these scripts.

The production site is available at `https://qayem.ai` and
`https://www.qayem.ai`, with `https://qayem.qayem-ai.workers.dev` as the direct
Worker URL. Both custom domains belong to the same Cloudflare account as the
Worker. The dedicated D1 database is in Eastern Europe. `wrangler.jsonc`
contains its real database ID and both custom-domain bindings. The four old
Vercel A records were removed with the owner's approval on 2026-10-05; their
settings are saved in `.artifacts/cloudflare/domain-cutover-before.json`.

## Publication and recovery

`cloudflare-sync.py` reads the live SQLite database in read-only mode and uses
SQLite's backup API to take a consistent copy. It computes the same inclusion
rules and comparisons as the local site. A full SQL export stages an immutable
version. Only a version with the expected unit, launch and document-part counts
can become active. Interrupted imports retain the previous active version.
The script checks the activated version after import and exits on failure.
Wrangler's bulk SQL import can briefly make D1 unavailable while the import runs;
the API returns a retryable 503 during database unavailability. Publishing is a
maintenance operation, not a guarantee of uninterrupted reads. Failed imports
restore the preceding database state.

Large JSON documents are split into small statements to respect D1 limits.
Comparable listings are joined by ID within the pinned version rather than
duplicating their images in every detail response. Unit filters, sort and
pagination, including compound and developer lists, use SQL indexes. Evaluation
loads only the selected compound and its evidence,
with a memory guard that returns 503 rather than silently omitting evidence.

SQL, a count manifest, the consistent source backup and import logs are written
under `.artifacts/cloudflare/`; these files are ignored by Git. Keep an independent
backup of `qayem.db`, including history. D1 is a public projection, not a replacement
for that canonical database.

For the independent cloud pipeline, see [cloud updates](CLOUD_UPDATES.md).
Its commissioning status records whether the cloud scheduler has actually taken over.

For the local fallback, set `QAYEM_CLOUDFLARE_SYNC=1` for `scripts/crawl.sh` to publish
after the nightly local pipeline. The Mac must stay available for these updates;
the deployed website itself serves the last successful snapshot independently.
The dedicated updater runs the crawler and Pi CLI in a Cloudflare Container.
The public Python Worker itself cannot launch the local Pi executable.

The explainer films use Cloudflare's native edge cache for byte-range responses;
the rest of the static assets are served directly. Video lengths come from the
same frontend build that is uploaded, and native streaming avoids buffering a film in
Python memory. Content hashes isolate cached films between builds. Restart the
local Python Worker after running `prepare.py`:
additional Python modules can remain cached during Wrangler's hot reload.

The three most recent D1 versions and the active version remain for rollback.
Older projections are retired only after the new publication has been verified;
`--keep-versions` changes the retention count. Canonical history stays in SQLite.
To roll back, update `state.value` for
`key='active'` to a previous `datasets.version` whose `ready=1`. Never select an
incomplete version. Monitor D1 storage as catalogue size grows.
