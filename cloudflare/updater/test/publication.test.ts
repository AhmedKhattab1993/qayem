import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {Miniflare, convertV4MiniflareOptions} from "miniflare";
import {activateDatabase} from "../src/publication.ts";

test("native D1 activation preserves the old snapshot until every staged row exists", async () => {
  const mf = new Miniflare(convertV4MiniflareOptions({modules: true, script: "export default {fetch() {return new Response('test')}}",
    compatibilityDate: "2026-10-01", d1Databases: ["DB"]}));
  try {
    const db = await mf.getD1Database("DB");
    const schema = readFileSync(new URL("../../schema.sql", import.meta.url), "utf8");
    // D1 exec expects one physical line for each SQL statement.
    await db.batch(schema.split(";").map(s => s.replace(/^--[^\n]*\n/gm, "").trim()).filter(Boolean).map(s => db.prepare(s)));
    await db.batch([
      db.prepare("INSERT INTO datasets VALUES ('old','2026-10-04','2026-10-04',1,0,0,1)"),
      db.prepare("INSERT INTO state VALUES ('active','old')"),
      db.prepare("INSERT INTO datasets VALUES ('new','2026-10-05','2026-10-05',1,0,1,0)"),
      db.prepare("INSERT INTO documents VALUES ('new','overview','',0,0,'{}')"),
    ]);
    const manifest = {version: "new", units: 1, launches: 0, document_parts: 1, entities: 0};
    await assert.rejects(activateDatabase(db, manifest), /Incomplete/);
    assert.equal(await db.prepare("SELECT value FROM state WHERE key='active'").first("value"), "old");
    // The last missing unit arrives; only now does the live pointer move.
    await db.prepare("INSERT INTO units(version,id,is_default,district,compound,developer,property_type,level,terms,source,search," +
      "price,area,opportunity_rank,same_finishing,public,record) VALUES ('new',1,1,'','','','','','','','',1,1,0,0,'{}','{}')").run();
    const active = await activateDatabase(db, manifest);
    assert.equal(active.version, "new");
    assert.equal(active.ready, 1);
    assert.equal(await db.prepare("SELECT value FROM state WHERE key='active'").first("value"), "new");
    assert.deepEqual(await activateDatabase(db, manifest), active); // Response loss and retry are harmless.
  } finally {await mf.dispose();}
});
