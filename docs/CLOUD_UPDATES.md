# Independent cloud updates

The update service is isolated from the public website: `cloudflare/updater/`
defines `qayem-updater`, the `qayem-nightly` Workflow, one `UpdateContainer`, and
the private `qayem-history` R2 bucket. It publishes to the existing `qayem-public`
D1 database. The public Python Worker and React build are not redeployed by this service.

## Migration status

Workers Paid is active and `qayem-updater`, its container application and the
`qayem-nightly` Workflow are deployed. The first complete cloud run,
`manual-1b34da28-8de1-48af-be79-bf273d97ce98`, completed on 5 October 2026
(Cairo time). Both source crawls and enrichment health checks passed. Its public
D1 version has 7,565 listings, 5,122 developer-sale benchmarks and 12,230 document
and entity rows; actual row counts match, and the live public API serves it.

The final R2 backup was downloaded and restored: both SHA-256 hashes and SQLite
integrity pass. It contains 56,568 properties, 65,030 history versions, 4,259
enrichment rows and 4,950 aliases. The local nightly LaunchAgent was unloaded
after publication verification and its plist renamed to `.plist.disabled`.
Verification evidence is saved privately under `.artifacts/cloud-updater/`.

## Schedule and operation

The service starts at **02:30 Africa/Cairo every day**, including daylight-saving
changes. Two UTC cron candidates are configured; the handler starts a Workflow
only for the candidate that falls at 02:30 Cairo. Its date-based instance ID
deduplicates repeated cron delivery. One shared Durable Object reserves the run,
so overlapping manual and scheduled jobs cannot write competing checkpoints.

The container restores `canonical/current.json` from R2 and checks the compressed
and restored database hashes plus SQLite integrity. It never creates an empty
replacement if its checkpoint is missing or damaged. The existing crawler,
entity resolution and GLM description enrichment run with their existing source
rules, request pacing and time budgets. Blocks are not bypassed. Checkpoints use
SQLite's backup API, include committed WAL rows, and alternate between two objects
per run so long jobs do not create an unbounded number of snapshots.
Within a run, identical database backups reuse their compressed file and are not
uploaded again. Log uploads are also skipped while their bytes are unchanged.
The backup uses a fresh SQLite destination so its transaction counter cannot make
unchanged data look different. Failed uploads remain eligible for retry.

AqarExit checks sitemap modification dates and fetches only new or changed detail
pages. Saved entity aliases and completed description enrichments survive in R2
and are reused; normal runs process only pending work and bounded retries. Nawy's
search inventory is refreshed nightly to detect price and availability changes.
The public D1 catalogue is still published as one complete, verified snapshot,
including updated freshness and time-dependent valuations.

Startup retries allow several minutes for image provisioning. The runner saves
checkpoints every five minutes and after each stage. Private
logs and terminal status are stored under `runs/<run-id>/`. Workflow polling keeps
the container alive and records failure; the container is destroyed after
completion or failure, with a five-minute inactivity fallback. This ensures that
the Python process running as PID 1 cannot ignore a stop signal and keep the
instance running between updates. A stopped instance loses its
filesystem, but the next run restores the last saved cloud checkpoint.

Source or enrichment health failures retain the preceding public catalogue.
Publication sends bounded, idempotent insert batches to the Worker's D1 binding.
Only a dataset whose unit, launch, document-part and entity counts match can be
marked ready and selected as active. A partial transfer cannot move the pointer.
The three most recent D1 versions and the active version remain for rollback.

## Credentials and costs

The image contains no database, Pi auth file, Cloudflare token, or other brands'
credentials. Only the `zai-coding-cn/glm-5.3-flash` provider's model configuration
is bundled. `GLM_API_KEY` and `ADMIN_TOKEN` are Cloudflare Worker secrets; the Pi
auth file is created only inside the running container with mode 600. Cloud
storage and publication use an outbound-only virtual hostname with Worker
bindings. No Cloudflare account token or R2 key is given to the crawler.

The administration endpoints require the Qayem token. The local token is kept at
`.artifacts/cloud-updater/admin-token` with mode 600 and is ignored by Git.
Do not print or commit it. R2 has no public URL or custom domain configured.

Containers require Workers Paid ($5/month plus usage beyond included allowances).
AI/provider charges are separate. This service uses one `basic` instance and
stops between runs. Retain independent database backups; the canonical SQLite
history is stored privately and is distinct from the sanitized D1 read model.

## Commissioning

From the repository root:

```sh
# Authorize Wrangler for the existing account plus Containers management/log reading.
# Activate Workers Paid in that account before deploying a container.
# The private qayem-history bucket and initial seed were created during preparation.
.venv/bin/python scripts/cloud-updater.py seed # first migration only, never reseed an active cloud history
bash scripts/deploy-cloud-updater.sh
.venv/bin/python scripts/cloud-updater.py run
.venv/bin/python scripts/cloud-updater.py status
.venv/bin/python scripts/cloud-updater.py verify # succeeds only after a complete publication
```

Verify that the Workflow completes, the R2 pointer names the cloud run, the D1
active version equals its verified publication, and the public API serves that
catalogue. Then run:

```sh
.venv/bin/python scripts/cloud-updater.py disable-local
```

This command checks that the cloud run completed, its R2 checkpoint is current,
D1 selected the complete version with matching row counts, and the live public API
serves its full catalogue. It saves the original LaunchAgent and
renames its installed plist to `.plist.disabled`. It does not stop the local web
server. To recover the local schedule, restore its filename and run
`launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.qayem.crawl.nightly.plist`.

Monitoring is available in the Cloudflare Workflow/Containers dashboards and
through the authenticated `status` command. A failed cloud run is not completion;
inspect its private R2 log and source health before starting another run.
The authenticated `stop` command destroys an idle or finished container and
refuses to interrupt a run whose status is still `running`:

```sh
.venv/bin/python scripts/cloud-updater.py stop
```
