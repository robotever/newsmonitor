-- observed_at is canonical UTC; payload_json preserves validated source timestamps.
-- Only derived dashboard payloads are stored. No raw provider rows or credentials.
CREATE TABLE IF NOT EXISTS market_dashboard_snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  observed_at TEXT NOT NULL,
  market_date TEXT NOT NULL,
  session TEXT NOT NULL,
  schema_version TEXT NOT NULL,
  scoring_version TEXT NOT NULL,
  completeness INTEGER NOT NULL,
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE (observed_at, scoring_version)
);

CREATE INDEX IF NOT EXISTS idx_market_dashboard_latest
ON market_dashboard_snapshots(observed_at DESC);
