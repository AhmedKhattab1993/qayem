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
-- Articles written by the article agent (src/qayem/articles.py) from Qayem's own figures. They publish
-- without approval once the fact check and gates pass; `status='unpublished'` takes one down.
CREATE TABLE IF NOT EXISTS articles (
  slug TEXT PRIMARY KEY, lang TEXT NOT NULL, title TEXT NOT NULL, summary TEXT NOT NULL, body TEXT NOT NULL,
  kind TEXT NOT NULL, trigger_key TEXT NOT NULL, district TEXT, compound TEXT, translation TEXT, meta TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'published', published_at TEXT NOT NULL, updated_at TEXT NOT NULL,
  unpublish_token TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS articles_published ON articles(status, lang, published_at);
CREATE INDEX IF NOT EXISTS articles_trigger ON articles(trigger_key);
-- First-party price observations: price checks run, what visitors were quoted, broker sheets.
-- No names or contact details: a check is a price, an area and a compound.
CREATE TABLE IF NOT EXISTS observations (
  id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL, day TEXT NOT NULL, kind TEXT NOT NULL,
  source TEXT NOT NULL, compound TEXT, district TEXT, property_type TEXT, area_m2 REAL, price REAL,
  over REAL, developer_price REAL, paid_price REAL, month TEXT, fingerprint TEXT NOT NULL, ip_hash TEXT,
  status TEXT NOT NULL DEFAULT 'accepted', inbox_id INTEGER, UNIQUE(fingerprint)
);
CREATE INDEX IF NOT EXISTS observations_day ON observations(day, kind);
-- Incoming WhatsApp Business messages (broker inventory sheets, developers' offers), for extraction and review.
CREATE TABLE IF NOT EXISTS inbox (
  id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL, channel TEXT NOT NULL, message_id TEXT NOT NULL UNIQUE,
  sender_hash TEXT NOT NULL, kind TEXT NOT NULL, text TEXT, media_id TEXT, status TEXT NOT NULL DEFAULT 'new',
  extracted TEXT, reviewed_at TEXT
);
CREATE INDEX IF NOT EXISTS inbox_status ON inbox(status, id);
