import test from "node:test";
import assert from "node:assert/strict";
import {authorized, scheduledRun, validateBatch, validateCheckpoint, validateManifest} from "../src/protocol.ts";

test("nightly schedule is 02:30 Cairo in summer and winter without duplicate firing", () => {
  assert.equal(scheduledRun(Date.parse("2026-10-04T23:30:00Z")), "nightly-2026-10-05");
  assert.equal(scheduledRun(Date.parse("2026-10-05T00:30:00Z")), null);
  assert.equal(scheduledRun(Date.parse("2026-11-04T23:30:00Z")), null);
  assert.equal(scheduledRun(Date.parse("2026-11-05T00:30:00Z")), "nightly-2026-11-05");
});

test("administration is private and fails closed without a configured secret", async () => {
  const token = "x".repeat(64);
  assert.equal(await authorized(new Request("https://test/status"), token), false);
  assert.equal(await authorized(new Request("https://test/status", {headers: {Authorization: `Bearer ${token}`}}), token), true);
  assert.equal(await authorized(new Request("https://test/status", {headers: {Authorization: `Bearer ${token}bad`}}), token), false);
  assert.equal(await authorized(new Request("https://test/status", {headers: {Authorization: "Bearer "}}), ""), false);
});

test("staging cannot write another version or activate/delete public data", () => {
  validateBatch("run-1", ["INSERT OR REPLACE INTO documents VALUES ('run-1','overview','','x');"]);
  for (const sql of ["DELETE FROM units;", "UPDATE datasets SET ready=1;", "INSERT INTO state VALUES ('active','run-1');",
    "INSERT OR REPLACE INTO documents VALUES ('other','overview','','x');"]) {
    assert.throws(() => validateBatch("run-1", [sql]));
  }
  assert.throws(() => validateBatch("run-1", Array(41).fill("x")));
});

test("checkpoint pointer requires the current run and complete checksums", () => {
  const value = {key: "canonical/run-1/123.db.gz", run_id: "run-1", sha256: "a".repeat(64),
    compressed_sha256: "b".repeat(64), bytes: 200, compressed_bytes: 80, saved_at: "2026-10-05"};
  validateCheckpoint(value, "run-1");
  assert.throws(() => validateCheckpoint(value, "other"));
  assert.throws(() => validateCheckpoint({...value, key: "canonical/run-1/../../x.db.gz"}, "run-1"));
  assert.throws(() => validateCheckpoint({...value, sha256: "bad"}, "run-1"));
});

test("an empty catalogue or invalid counts cannot be activated", () => {
  const manifest = {version: "run-1", units: 3, launches: 0, document_parts: 5, entities: 2};
  validateManifest(manifest);
  assert.throws(() => validateManifest({...manifest, units: 0}));
  assert.throws(() => validateManifest({...manifest, units: NaN}));
  assert.throws(() => validateManifest({...manifest, entities: -1}));
});
