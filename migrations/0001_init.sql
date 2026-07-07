-- ProcessIQ initial schema (design Section 9.2). Apply via Alembic or psql.
-- Owner: Utkarsh. RLS policies enforce tenant isolation (design Section 14.2).

CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS citext;

CREATE TABLE IF NOT EXISTS tenant (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  region TEXT NOT NULL DEFAULT 'primary',
  settings JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS app_user (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenant(id),
  email CITEXT NOT NULL,
  display_name TEXT,
  idp_subject TEXT,
  status TEXT NOT NULL DEFAULT 'active',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, email)
);

CREATE TABLE IF NOT EXISTS process (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenant(id),
  name TEXT NOT NULL,
  owner_id UUID REFERENCES app_user(id),
  status TEXT NOT NULL DEFAULT 'active',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS job (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL,
  process_id UUID REFERENCES process(id),
  status TEXT NOT NULL,
  stage TEXT,
  progress SMALLINT NOT NULL DEFAULT 0,
  input_hash TEXT,
  gpu_ms BIGINT NOT NULL DEFAULT 0,
  token_cost BIGINT NOT NULL DEFAULT 0,
  error JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_job_tenant_status ON job (tenant_id, status);

CREATE TABLE IF NOT EXISTS artifact (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL,
  process_id UUID REFERENCES process(id),
  kind TEXT NOT NULL,
  object_key TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  phash TEXT,
  seq_order INT,
  mime TEXT,
  bytes BIGINT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_artifact_process ON artifact (tenant_id, process_id, seq_order);

CREATE TABLE IF NOT EXISTS sop (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL,
  process_id UUID REFERENCES process(id),
  title TEXT NOT NULL,
  current_version INT NOT NULL DEFAULT 1,
  state TEXT NOT NULL DEFAULT 'DRAFT',
  overall_confidence NUMERIC(4,3),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS sop_version (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  sop_id UUID REFERENCES sop(id),
  version INT NOT NULL,
  mongo_doc_id TEXT NOT NULL,
  confidence NUMERIC(4,3),
  created_by UUID,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  immutable BOOLEAN NOT NULL DEFAULT true,
  UNIQUE (sop_id, version)
);

-- Enable RLS (policies added when auth/session tenant context is wired).
ALTER TABLE process ENABLE ROW LEVEL SECURITY;
ALTER TABLE job ENABLE ROW LEVEL SECURITY;
ALTER TABLE artifact ENABLE ROW LEVEL SECURITY;
ALTER TABLE sop ENABLE ROW LEVEL SECURITY;
