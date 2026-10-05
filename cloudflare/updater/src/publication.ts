import {validateManifest, type Manifest} from "./protocol.ts";

export async function activateDatabase(database: D1Database, manifest: Manifest): Promise<Record<string, string | number>> {
  validateManifest(manifest);
  const v = manifest.version;
  const [, , verified] = await database.batch([
    database.prepare("UPDATE datasets SET ready=1,entity_count=? WHERE version=? AND unit_count=? AND launch_count=? " +
      "AND ?=(SELECT count(*) FROM units WHERE version=?) AND ?=(SELECT count(*) FROM launches WHERE version=?) " +
      "AND ?=(SELECT count(*) FROM documents WHERE version=?) AND ?=(SELECT count(*) FROM entities WHERE version=?)")
      .bind(manifest.document_parts + manifest.entities, v, manifest.units, manifest.launches,
        manifest.units, v, manifest.launches, v, manifest.document_parts, v, manifest.entities, v),
    database.prepare("INSERT INTO state(key,value) SELECT 'active',version FROM datasets WHERE version=? AND ready=1 " +
      "ON CONFLICT(key) DO UPDATE SET value=excluded.value").bind(v),
    database.prepare("SELECT d.version,d.ready,d.unit_count,d.launch_count,d.generated_at FROM datasets d " +
      "JOIN state s ON s.value=d.version WHERE s.key='active' AND d.version=? AND d.ready=1").bind(v),
  ]);
  if (!verified.results.length) throw new Error("Incomplete catalogue; previous publication retained");
  return verified.results[0] as Record<string, string | number>;
}
