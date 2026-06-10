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

CREATE TABLE IF NOT EXISTS volumes (
  id INTEGER PRIMARY KEY,
  project_id INTEGER NOT NULL REFERENCES projects(id),
  title TEXT NOT NULL,
  source_path TEXT NOT NULL,
  source_format TEXT NOT NULL CHECK (source_format IN ('epub', 'txt', 'html')),
  volume_order INTEGER NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chapters (
  id TEXT PRIMARY KEY,
  project_id INTEGER REFERENCES projects(id),
  volume_id INTEGER REFERENCES volumes(id),
  title TEXT,
  href TEXT,
  spine_order INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_volumes_project ON volumes(project_id, volume_order);
CREATE INDEX IF NOT EXISTS idx_chapters_volume ON chapters(volume_id, spine_order);

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
  )),
  review_status TEXT NOT NULL DEFAULT 'not_reviewed' CHECK (review_status IN (
    'not_reviewed',
    'needs_review',
    'needs_revision',
    'approved',
    'rejected'
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
  input_tokens INTEGER,
  output_tokens INTEGER,
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

CREATE TABLE IF NOT EXISTS characters (
  id INTEGER PRIMARY KEY,
  project_id INTEGER REFERENCES projects(id),
  jp_name TEXT NOT NULL,
  en_name TEXT NOT NULL,
  gender TEXT,
  role TEXT,
  notes TEXT,
  UNIQUE(project_id, jp_name)
);

CREATE INDEX IF NOT EXISTS idx_characters_project ON characters(project_id, jp_name);

CREATE TABLE IF NOT EXISTS translation_memory (
  id INTEGER PRIMARY KEY,
  project_id INTEGER REFERENCES projects(id),
  source_text TEXT NOT NULL,
  source_hash TEXT NOT NULL,
  target_text TEXT NOT NULL,
  provider TEXT,
  model TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(project_id, source_hash)
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
  job_id TEXT,
  event TEXT NOT NULL,
  data_json TEXT,
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_job_events_job ON job_events(job_id, id);

-- Sprint I (ADR 010) — SQLite-backed JobRegistry, single-process, in-thread.
-- One row per submitted background job (translate/batch/export plus future
-- parse/ocr scopes reserved by status). Status state machine:
--   queued | running | done | failed | cancelled
-- Transitional states `processed` and `finalizing` are reserved for J/M.
CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  project_name TEXT NOT NULL,
  scope TEXT,
  scope_id TEXT,
  chapter_id TEXT,
  status TEXT NOT NULL CHECK (status IN (
    'queued',
    'running',
    'done',
    'failed',
    'cancelled',
    'processed',
    'finalizing'
  )),
  mode TEXT,
  target TEXT,
  total_units INTEGER NOT NULL DEFAULT 0,
  done_units INTEGER NOT NULL DEFAULT 0,
  failed_units INTEGER NOT NULL DEFAULT 0,
  skipped_units INTEGER NOT NULL DEFAULT 0,
  current_label TEXT,
  result_json TEXT,
  error_summary TEXT,
  started_at TEXT NOT NULL,
  finished_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_jobs_project_status ON jobs(project_name, status);
CREATE INDEX IF NOT EXISTS idx_jobs_kind_status ON jobs(kind, status);

CREATE TABLE IF NOT EXISTS job_progress_snapshots (
  job_id TEXT REFERENCES jobs(id),
  snapshot_at TEXT NOT NULL,
  done_units INTEGER NOT NULL,
  total_units INTEGER NOT NULL,
  PRIMARY KEY (job_id, snapshot_at)
);

-- Sprint J (ADR 010-adjacent) — preservation snapshot of Phase F ParsedEpub.
-- Six additive tables keyed by volume_id. The snapshot is invalidated when
-- either the source EPUB hash or the parser version changes; readers walk
-- these tables instead of re-parsing the archive.
CREATE TABLE IF NOT EXISTS epub_snapshots (
  volume_id INTEGER PRIMARY KEY REFERENCES volumes(id),
  source_hash TEXT NOT NULL,
  parser_version INTEGER NOT NULL,
  package_path TEXT NOT NULL,
  opf_path TEXT,
  spine_toc TEXT,
  page_progression_direction TEXT,
  metadata_json TEXT NOT NULL,
  preservation_context_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS epub_snapshot_manifest (
  volume_id INTEGER NOT NULL REFERENCES epub_snapshots(volume_id),
  position INTEGER NOT NULL,
  data_json TEXT NOT NULL,
  PRIMARY KEY (volume_id, position)
);

CREATE TABLE IF NOT EXISTS epub_snapshot_spine (
  volume_id INTEGER NOT NULL REFERENCES epub_snapshots(volume_id),
  position INTEGER NOT NULL,
  data_json TEXT NOT NULL,
  PRIMARY KEY (volume_id, position)
);

CREATE TABLE IF NOT EXISTS epub_snapshot_navigation (
  volume_id INTEGER NOT NULL REFERENCES epub_snapshots(volume_id),
  position INTEGER NOT NULL,
  data_json TEXT NOT NULL,
  PRIMARY KEY (volume_id, position)
);

CREATE TABLE IF NOT EXISTS epub_snapshot_images (
  volume_id INTEGER NOT NULL REFERENCES epub_snapshots(volume_id),
  position INTEGER NOT NULL,
  data_json TEXT NOT NULL,
  PRIMARY KEY (volume_id, position)
);

CREATE TABLE IF NOT EXISTS epub_snapshot_validation (
  volume_id INTEGER NOT NULL REFERENCES epub_snapshots(volume_id),
  position INTEGER NOT NULL,
  data_json TEXT NOT NULL,
  PRIMARY KEY (volume_id, position)
);

-- Sprint L (ADR 010-adjacent) — translation candidate review & character text drafts.
-- Additive tables: translation_candidates for AI-suggested translations (never
-- auto-mutate current translation); character_page_drafts for XHTML/text-only
-- character page extraction (no OCR, no image processing).

CREATE TABLE IF NOT EXISTS translation_candidates (
  id TEXT PRIMARY KEY,
  project_id INTEGER NOT NULL REFERENCES projects(id),
  volume_id INTEGER REFERENCES volumes(id),
  chapter_id TEXT NOT NULL REFERENCES chapters(id),
  segment_id TEXT NOT NULL REFERENCES segments(id),
  source_text TEXT NOT NULL,
  candidate_text TEXT NOT NULL,
  provider TEXT NOT NULL,
  model TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN (
    'pending',
    'approved',
    'rejected',
    'applied',
    'superseded',
    'failed'
  )),
  provenance_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_candidates_segment ON translation_candidates(segment_id, status);
CREATE INDEX IF NOT EXISTS idx_candidates_project ON translation_candidates(project_id, status);

CREATE TABLE IF NOT EXISTS character_page_drafts (
  id TEXT PRIMARY KEY,
  project_id INTEGER NOT NULL REFERENCES projects(id),
  volume_id INTEGER REFERENCES volumes(id),
  chapter_id TEXT NOT NULL REFERENCES chapters(id),
  segment_id TEXT REFERENCES segments(id),
  source_text TEXT NOT NULL,
  draft_text TEXT NOT NULL,
  heading TEXT,
  page_identifier TEXT,
  status TEXT NOT NULL CHECK (status IN (
    'draft',
    'approved',
    'rejected'
  )),
  provenance_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_char_drafts_project ON character_page_drafts(project_id, status);
