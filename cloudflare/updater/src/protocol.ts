export const RUN_ID = /^[A-Za-z0-9_-]{1,100}$/;
export const MAX_BATCH_BYTES = 300_000;

export interface Manifest {
  version: string; units: number; launches: number; document_parts: number; entities: number;
}

export interface Checkpoint {
  key: string; run_id: string; sha256: string; compressed_sha256: string;
  bytes: number; compressed_bytes: number; saved_at: string;
}

export function assertRunId(value: unknown): asserts value is string {
  if (typeof value !== "string" || !RUN_ID.test(value)) throw new Error("Invalid run ID");
}

export function validateManifest(value: Manifest): void {
  assertRunId(value.version);
  for (const count of [value.units, value.launches, value.document_parts, value.entities]) {
    if (!Number.isSafeInteger(count) || count < 0) throw new Error("Invalid publication counts");
  }
  if (!value.units || !value.document_parts) throw new Error("Empty catalogue cannot be activated");
}

export function validateBatch(version: string, statements: string[]): void {
  assertRunId(version);
  if (!Array.isArray(statements) || !statements.length || statements.length > 40) {
    throw new Error("Invalid publication batch");
  }
  if (new TextEncoder().encode(JSON.stringify(statements)).length > MAX_BATCH_BYTES + 1000) {
    throw new Error("Publication batch exceeds its byte budget");
  }
  for (const statement of statements) {
    // Only the trusted exporter's inserts can stage this run. No activation, deletion or cross-version writes.
    if (typeof statement !== "string" || !/^INSERT OR REPLACE INTO (datasets|documents|units|launches|entities) VALUES \('/.test(statement) ||
        !statement.includes(` VALUES ('${version}',`)) throw new Error("Invalid staging statement");
  }
}

export function validateCheckpoint(value: Checkpoint, runId: string): void {
  if (value.run_id !== runId || !value.key.startsWith(`canonical/${runId}/`) ||
      !/^[A-Za-z0-9_/-]+\.db\.gz$/.test(value.key) ||
      !/^[a-f0-9]{64}$/.test(value.sha256) || !/^[a-f0-9]{64}$/.test(value.compressed_sha256) ||
      !Number.isSafeInteger(value.bytes) || value.bytes <= 0 ||
      !Number.isSafeInteger(value.compressed_bytes) || value.compressed_bytes <= 0) {
    throw new Error("Invalid database checkpoint");
  }
}

export function scheduledRun(timestamp: number): string | null {
  // Both UTC candidates are configured. Exactly one matches 02:30 Cairo through DST changes.
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Africa/Cairo", year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", hourCycle: "h23",
  }).formatToParts(new Date(timestamp));
  const part = (name: string) => parts.find(p => p.type === name)?.value;
  return part("hour") === "02" && part("minute") === "30"
    ? `nightly-${part("year")}-${part("month")}-${part("day")}` : null;
}

export async function authorized(request: Request, token: string): Promise<boolean> {
  if (!token || token.length < 32) return false;
  const actual = request.headers.get("Authorization") || "";
  const encode = new TextEncoder();
  const hash = async (text: string) => new Uint8Array(await crypto.subtle.digest("SHA-256", encode.encode(text)));
  const [wanted, provided] = await Promise.all([hash(`Bearer ${token}`), hash(actual)]);
  let difference = 0;
  for (let i = 0; i < wanted.length; i++) difference |= wanted[i] ^ provided[i];
  return difference === 0;
}
