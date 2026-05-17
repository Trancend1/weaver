PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS projects (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  source_path TEXT NOT NULL,
  source_lang TEXT NOT NULL,
  target_lang TEXT NOT NULL,
  created_at TEXT NOT NULL,
  schema_version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS chapters (
  id TEXT PRIMARY KEY,
  project_id INTEGER REFERENCES projects(id),
  title TEXT,
  href TEXT,
  spine_order INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS segments (
  id TEXT PRIMARY KEY,
  chapter_id TEXT REFERENCES chapters(id),
  block_order INTEGER NOT NULL,
  kind TEXT NOT NULL,
  source_text TEXT NOT NULL,
  source_hash TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN (
    'pending',
    'in_progress',
    'translated',
    'failed',
    'stale',
    'skipped',
    'manual'
  ))
);

CREATE TABLE IF NOT EXISTS translations (
  segment_id TEXT REFERENCES segments(id),
  attempt INTEGER NOT NULL,
  text TEXT NOT NULL,
  source_hash TEXT NOT NULL,
  provider TEXT NOT NULL,
  model TEXT NOT NULL,
  created_at TEXT NOT NULL,
  raw_response TEXT,
  PRIMARY KEY (segment_id, attempt)
);

CREATE INDEX IF NOT EXISTS idx_segments_status ON segments(status);
CREATE INDEX IF NOT EXISTS idx_segments_chapter ON segments(chapter_id, block_order);

CREATE TABLE IF NOT EXISTS glossary_candidates (
  id INTEGER PRIMARY KEY,
  project_id INTEGER REFERENCES projects(id),
  source TEXT NOT NULL,
  target TEXT,
  category TEXT,
  notes TEXT,
  status TEXT NOT NULL CHECK (status IN ('pending', 'approved', 'rejected', 'edited')),
  frequency INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS glossary_terms (
  id INTEGER PRIMARY KEY,
  project_id INTEGER REFERENCES projects(id),
  source TEXT NOT NULL,
  target TEXT NOT NULL,
  category TEXT,
  notes TEXT,
  case_sensitive INTEGER NOT NULL DEFAULT 0,
  UNIQUE(project_id, source)
);

CREATE TABLE IF NOT EXISTS qa_warnings (
  id INTEGER PRIMARY KEY,
  segment_id TEXT REFERENCES segments(id),
  check_name TEXT NOT NULL,
  severity TEXT NOT NULL CHECK (severity IN ('info', 'warning', 'critical')),
  message TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS job_events (
  id INTEGER PRIMARY KEY,
  project_id INTEGER REFERENCES projects(id),
  event TEXT NOT NULL,
  data_json TEXT,
  created_at TEXT NOT NULL
);
