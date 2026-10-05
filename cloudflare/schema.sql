-- Public read model only. No phones, raw source payloads, credentials, or enrichment prompts.
CREATE TABLE IF NOT EXISTS datasets (
  version TEXT PRIMARY KEY, generated_at TEXT NOT NULL, today TEXT NOT NULL,
  unit_count INTEGER NOT NULL, launch_count INTEGER NOT NULL, entity_count INTEGER NOT NULL,
  ready INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS documents (
  version TEXT NOT NULL, kind TEXT NOT NULL, key TEXT NOT NULL, part INTEGER NOT NULL, position INTEGER NOT NULL,
  data TEXT NOT NULL, PRIMARY KEY(version,kind,key,part),
  FOREIGN KEY(version) REFERENCES datasets(version)
);
CREATE TABLE IF NOT EXISTS units (
  version TEXT NOT NULL, id INTEGER NOT NULL, is_default INTEGER NOT NULL,
  district TEXT NOT NULL, compound TEXT NOT NULL, developer TEXT NOT NULL,
  property_type TEXT NOT NULL, level TEXT NOT NULL, terms TEXT NOT NULL, source TEXT NOT NULL,
  search TEXT NOT NULL, price REAL NOT NULL, area REAL NOT NULL,
  opportunity_rank INTEGER NOT NULL, launch_gap REAL, same_finishing INTEGER NOT NULL,
  peer_gap REAL, cash_ppm REAL, url_key TEXT,
  public TEXT NOT NULL, record TEXT NOT NULL,
  PRIMARY KEY(version,id), FOREIGN KEY(version) REFERENCES datasets(version)
);
CREATE TABLE IF NOT EXISTS launches (
  version TEXT NOT NULL, compound TEXT NOT NULL, id INTEGER NOT NULL, record TEXT NOT NULL,
  PRIMARY KEY(version,compound,id), FOREIGN KEY(version) REFERENCES datasets(version)
);
CREATE TABLE IF NOT EXISTS entities (
  version TEXT NOT NULL, kind TEXT NOT NULL, key TEXT NOT NULL, position INTEGER NOT NULL,
  name TEXT NOT NULL, name_ar TEXT NOT NULL, search TEXT NOT NULL,
  district TEXT NOT NULL, developer TEXT NOT NULL, units INTEGER NOT NULL, good_count INTEGER NOT NULL,
  launch_gap REAL, compared INTEGER NOT NULL,
  PRIMARY KEY(version,kind,key), FOREIGN KEY(version) REFERENCES datasets(version)
);
CREATE INDEX IF NOT EXISTS entities_position ON entities(version,kind,position);
CREATE INDEX IF NOT EXISTS entities_district ON entities(version,kind,district,position);
CREATE INDEX IF NOT EXISTS entities_developer ON entities(version,kind,developer,position);
CREATE INDEX IF NOT EXISTS entities_name ON entities(version,kind,name,position);
CREATE INDEX IF NOT EXISTS entities_gap ON entities(version,kind,launch_gap,position);
CREATE INDEX IF NOT EXISTS units_default_rank ON units(version,is_default,opportunity_rank);
CREATE INDEX IF NOT EXISTS units_compound ON units(version,compound,is_default);
CREATE INDEX IF NOT EXISTS units_developer ON units(version,developer,is_default);
CREATE INDEX IF NOT EXISTS units_district ON units(version,district,is_default);
CREATE INDEX IF NOT EXISTS units_price ON units(version,is_default,price,id);
CREATE INDEX IF NOT EXISTS units_launch_gap ON units(version,is_default,launch_gap,id);
CREATE INDEX IF NOT EXISTS units_peer_gap ON units(version,is_default,peer_gap,id);
CREATE INDEX IF NOT EXISTS units_cash_ppm ON units(version,is_default,cash_ppm,id);
CREATE INDEX IF NOT EXISTS units_area ON units(version,is_default,area,id);
CREATE INDEX IF NOT EXISTS units_url ON units(version,url_key);
