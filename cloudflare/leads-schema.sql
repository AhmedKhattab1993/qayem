-- qayem-leads: persistent first-party data (visits, leads, alerts). A separate D1 database from
-- qayem-public, so catalogue publications, imports and version retention can never touch it.
-- No raw IP addresses are stored: ip_hash is a salted hash that changes every day (rate limits only).
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL, day TEXT NOT NULL,
  event_type TEXT NOT NULL, visitor TEXT, ip_hash TEXT, is_bot INTEGER NOT NULL DEFAULT 0, device TEXT,
  country TEXT, lang TEXT, path TEXT, entity_key TEXT, unit_id INTEGER, referrer TEXT,
  utm_source TEXT, utm_medium TEXT, utm_campaign TEXT, meta TEXT
);
CREATE INDEX IF NOT EXISTS events_day ON events(day, event_type);
CREATE INDEX IF NOT EXISTS events_ip ON events(day, ip_hash);
CREATE TABLE IF NOT EXISTS leads (
  id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL, day TEXT NOT NULL, kind TEXT NOT NULL,
  role TEXT, name TEXT, whatsapp TEXT, email TEXT, country TEXT, lang TEXT, compound_key TEXT, unit_id INTEGER,
  intent TEXT NOT NULL, page_path TEXT, visitor TEXT, ip_hash TEXT,
  utm_source TEXT, utm_medium TEXT, utm_campaign TEXT, status TEXT NOT NULL DEFAULT 'new'
);
CREATE INDEX IF NOT EXISTS leads_day ON leads(day);
CREATE INDEX IF NOT EXISTS leads_ip ON leads(day, ip_hash);
CREATE TABLE IF NOT EXISTS alerts (
  id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL, day TEXT NOT NULL, channel TEXT NOT NULL,
  destination TEXT NOT NULL, role TEXT, lang TEXT NOT NULL DEFAULT 'ar', query TEXT NOT NULL, label TEXT NOT NULL,
  country TEXT, visitor TEXT, ip_hash TEXT, utm_source TEXT, page_path TEXT,
  last_seen_unit INTEGER NOT NULL DEFAULT 0, last_checked TEXT, last_sent TEXT,
  sent_count INTEGER NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1, token TEXT NOT NULL UNIQUE
);
CREATE INDEX IF NOT EXISTS alerts_active ON alerts(active, id);
CREATE INDEX IF NOT EXISTS alerts_destination ON alerts(destination, query);
CREATE INDEX IF NOT EXISTS alerts_ip ON alerts(day, ip_hash);
CREATE TABLE IF NOT EXISTS deliveries (
  id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL, alert_id INTEGER NOT NULL, version TEXT NOT NULL,
  channel TEXT NOT NULL, matches INTEGER NOT NULL, status TEXT NOT NULL, UNIQUE(alert_id, version)
);
CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT NOT NULL);
