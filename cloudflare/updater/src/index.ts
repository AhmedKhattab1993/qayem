import {Container} from "@cloudflare/containers";
export {ContainerProxy} from "@cloudflare/containers";
import {WorkflowEntrypoint, type WorkflowEvent, type WorkflowStep} from "cloudflare:workers";
import {assertRunId, authorized, scheduledRun, validateBatch, validateCheckpoint,
  type Checkpoint, type Manifest} from "./protocol";
import {activateDatabase} from "./publication";

interface Bindings {
  UPDATER: DurableObjectNamespace<UpdateContainer>;
  UPDATES: Workflow<Params>;
  HISTORY: R2Bucket;
  DB: D1Database;
  ADMIN_TOKEN: string;
  GLM_API_KEY: string;
  QAYEM_SOURCES: string;
  QAYEM_BENCHMARK_SOURCES: string;
}
interface Params {run_id?: string}
interface Job {run_id: string; status: string; stage?: string; started_at?: string;
  finished_at?: string; error?: string; publication?: Record<string, string | number>}

export class UpdateContainer extends Container<Bindings> {
  defaultPort = 8080;
  sleepAfter = "5m";
  enableInternet = true;
  pingEndpoint = "/health";
  envVars = {GLM_API_KEY: this.env.GLM_API_KEY, QAYEM_SOURCES: this.env.QAYEM_SOURCES,
    QAYEM_BENCHMARK_SOURCES: this.env.QAYEM_BENCHMARK_SOURCES};

  async active(runId: string): Promise<Job> {
    assertRunId(runId);
    const job = await this.ctx.storage.get<Job>("job");
    if (!job || job.run_id !== runId || job.status !== "running") throw new Error("Run is not active");
    return job;
  }

  async begin(runId: string): Promise<Job> {
    assertRunId(runId);
    const existing = await this.ctx.storage.transaction(async tx => {
      const previous = await tx.get<Job>("job");
      if (!previous || (previous.run_id !== runId && previous.status !== "running")) {
        await tx.put("job", {run_id: runId, status: "running", stage: "starting",
          started_at: new Date().toISOString()});
      }
      return previous;
    });
    if (existing?.run_id === runId && existing.status !== "running") return existing;
    if (existing?.status === "running" && existing.run_id !== runId) {
      return {run_id: runId, status: "skipped", error: "Another update is still running"};
    }
    if (!existing || existing.run_id !== runId) {
      if (this.ctx.container?.running) await this.destroy();
    }
    const response = await this.containerFetch("http://container/run", {
      method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({run_id: runId}),
    });
    if (!response.ok) {
      let detail = await response.text();
      for (const secret of [this.env.GLM_API_KEY, this.env.ADMIN_TOKEN]) {
        if (secret) detail = detail.replaceAll(secret, "[redacted]");
      }
      console.error("Container startup failed", response.status, detail.slice(0, 800));
      throw new Error(`Container could not start the update (HTTP ${response.status})`);
    }
    return response.json<Job>();
  }

  async status(runId?: string): Promise<Job | null> {
    const saved = await this.ctx.storage.get<Job>("job");
    if (!saved || (runId && saved.run_id !== runId)) return null;
    if (saved.status !== "running") return saved;
    if (!this.ctx.container?.running && saved.stage === "starting" &&
        Date.now() - Date.parse(saved.started_at || "") < 10 * 60_000) return saved;
    if (!this.ctx.container?.running) {
      return this.finish(saved.run_id, {status: "failed", error: "Container stopped; next run restores its cloud checkpoint"});
    }
    const response = await this.containerFetch("http://container/status");
    if (!response.ok) throw new Error("Could not read container status");
    const current = await response.json<Job>();
    if (current.run_id !== saved.run_id) throw new Error("Container has no matching run");
    await this.ctx.storage.put("job", current);
    return current;
  }

  async finish(runId: string, changes: Partial<Job>): Promise<Job> {
    const saved = await this.ctx.storage.get<Job>("job");
    if (!saved || saved.run_id !== runId) throw new Error("Run does not match");
    // An infrastructure reporting failure cannot overwrite a verified completion.
    const job = saved.status !== "running" ? saved : {...saved, ...changes, run_id: runId,
      finished_at: new Date().toISOString()};
    await this.ctx.storage.put("job", job);
    await this.env.HISTORY.put(`runs/${runId}/status.json`, JSON.stringify(job));
    return job;
  }

  async stage(runId: string, statements: string[]): Promise<void> {
    await this.active(runId);
    validateBatch(runId, statements);
    const ready = await this.env.DB.prepare("SELECT ready FROM datasets WHERE version=?").bind(runId).first<number>("ready");
    if (ready === 1) return; // A replay after activation must not reset ready to zero.
    await this.env.DB.batch(statements.map(sql => this.env.DB.prepare(sql)));
  }

  async activate(manifest: Manifest): Promise<unknown> {
    await this.active(manifest.version);
    const verified = await activateDatabase(this.env.DB, manifest);
    // Keep three recent versions and the active version, including after an older rollback.
    const obsolete = "SELECT version FROM datasets WHERE version NOT IN " +
      "(SELECT version FROM datasets ORDER BY generated_at DESC,version DESC LIMIT 3) " +
      "AND version != (SELECT value FROM state WHERE key='active')";
    try {
      await this.env.DB.batch(["documents", "units", "launches", "entities", "datasets"].map(table =>
        this.env.DB.prepare(`DELETE FROM ${table} WHERE version IN (${obsolete})`)));
    } catch {console.warn("Verified publication complete; retention will retry on the next update");}
    return verified;
  }

  async canonical(value: Checkpoint): Promise<void> {
    await this.active(value.run_id);
    validateCheckpoint(value, value.run_id);
    const object = await this.env.HISTORY.head(value.key);
    if (!object || object.size !== value.compressed_bytes ||
        object.customMetadata?.sha256 !== value.compressed_sha256) throw new Error("Checkpoint object is unverified");
    await this.env.HISTORY.put("canonical/current.json", JSON.stringify(value));
  }

  async onActivityExpired(): Promise<void> {
    await this.destroy();
  }
}

// These requests originate only inside the container. Cloud bindings stay in the Worker;
// the crawler receives neither an R2 API key nor a Cloudflare account token.
UpdateContainer.outboundByHost = {
  "qayem.internal": async (request: Request, rawEnv, ctx) => {
    const env = rawEnv as unknown as Bindings;
    const updater = env.UPDATER.get(env.UPDATER.idFromString(ctx.containerId));
    const path = new URL(request.url).pathname;
    try {
      if (path === "/canonical" && request.method === "GET") {
        const object = await env.HISTORY.get("canonical/current.json");
        return object ? new Response(object.body, {headers: {"Content-Type": "application/json"}})
          : Response.json({error: "Canonical seed is missing"}, {status: 409});
      }
      if (path === "/canonical" && request.method === "PUT") {
        await updater.canonical(await request.json<Checkpoint>());
        return Response.json({saved: true});
      }
      if (path.startsWith("/objects/")) {
        const key = path.slice("/objects/".length);
        if (!/^(canonical|runs)\/[A-Za-z0-9_/-]+\.(db\.gz|log|json)$/.test(key)) {
          return Response.json({error: "Invalid object key"}, {status: 400});
        }
        if (request.method === "GET") {
          const object = await env.HISTORY.get(key);
          return object ? new Response(object.body) : new Response(null, {status: 404});
        }
        if (request.method === "PUT" && request.body) {
          const runId = key.split("/")[1];
          await updater.active(runId);
          const sha256 = request.headers.get("X-Content-SHA256") || "";
          if (!/^[a-f0-9]{64}$/.test(sha256)) return Response.json({error: "Checksum missing"}, {status: 400});
          const checksum = Uint8Array.from(sha256.match(/../g)!, hex => parseInt(hex, 16)).buffer;
          await env.HISTORY.put(key, request.body, {sha256: checksum, customMetadata: {sha256}});
          return Response.json({saved: true});
        }
      }
      if (path === "/publish/batch" && request.method === "POST") {
        const batch = await request.json<{version: string; statements: string[]}>();
        await updater.stage(batch.version, batch.statements);
        return Response.json({staged: true});
      }
      if (path === "/publish/activate" && request.method === "POST") {
        return Response.json(await updater.activate(await request.json<Manifest>()));
      }
      if (path === "/run-status" && request.method === "PUT") {
        const status = await request.json<Job>();
        await updater.finish(status.run_id, status);
        return Response.json({saved: true});
      }
      return Response.json({error: "Unknown operation"}, {status: 404});
    } catch {return Response.json({error: "Cloud operation failed; inspect Worker logs"}, {status: 500});}
  },
};

export class NightlyUpdate extends WorkflowEntrypoint<Bindings, Params> {
  async run(event: WorkflowEvent<Params>, step: WorkflowStep): Promise<Job> {
    const runId = event.payload?.run_id || event.instanceId;
    assertRunId(runId);
    const updater = this.env.UPDATER.getByName("nightly");
    const retry = {retries: {limit: 3, delay: "10 seconds", backoff: "exponential"}, timeout: "5 minutes"} as const;
    const startRetry = {retries: {limit: 12, delay: "30 seconds", backoff: "constant"}, timeout: "5 minutes"} as const;
    try {
      // A newly deployed image can take several minutes to become available.
      const initial = await step.do<Job>("restore and start pipeline", startRetry, () => updater.begin(runId));
      if (initial.status === "skipped") return initial;
      for (let minute = 0; minute < 450; minute++) {
        const status = await step.do<Job | null>(`check pipeline ${minute}`, retry, () => updater.status(runId));
        if (!status) throw new Error("Update run is missing");
        if (status.status !== "running") {
          if (status.status !== "complete") throw new Error("Update failed; previous catalogue remains available");
          await step.do("stop completed container", retry, () => updater.destroy());
          return status;
        }
        await step.sleep(`wait for pipeline ${minute}`, "1 minute");
      }
      throw new Error("Update exceeded its time budget");
    } catch {
      await step.do("record failed update", retry, () => updater.finish(runId,
        {status: "failed", error: "Cloud update failed; inspect its private run log and Workflow status"}));
      await step.do("stop failed container", retry, () => updater.destroy());
      throw new Error("Qayem cloud update failed");
    }
  }
}

export default {
  async fetch(request: Request, env: Bindings): Promise<Response> {
    if (!(await authorized(request, env.ADMIN_TOKEN))) return new Response("Unauthorized", {status: 401});
    const path = new URL(request.url).pathname;
    if (path === "/status" && request.method === "GET") {
      return Response.json(await env.UPDATER.getByName("nightly").status());
    }
    if (path === "/run" && request.method === "POST") {
      const runId = `manual-${crypto.randomUUID()}`;
      const instance = await env.UPDATES.create({id: runId, params: {run_id: runId}});
      return Response.json({run_id: instance.id}, {status: 202});
    }
    if (path === "/stop" && request.method === "POST") {
      const updater = env.UPDATER.getByName("nightly");
      const job = await updater.status();
      if (job?.status === "running") return Response.json({error: "Update is still running"}, {status: 409});
      await updater.destroy();
      return Response.json({stopped: true});
    }
    return new Response("Not found", {status: 404});
  },
  async scheduled(controller: ScheduledController, env: Bindings): Promise<void> {
    const runId = scheduledRun(controller.scheduledTime);
    if (!runId) return;
    try {await env.UPDATES.create({id: runId, params: {run_id: runId}});}
    catch (error) {
      // A duplicate cron firing is harmless only when this exact instance exists.
      const instance = await env.UPDATES.get(runId);
      await instance.status();
      console.log("Nightly update already exists", runId);
    }
  },
} satisfies ExportedHandler<Bindings>;
