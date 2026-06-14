-- Recon schema · Postgres 16 + pgvector
CREATE EXTENSION IF NOT EXISTS vector;

-- ─── companies ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS companies (
    id              SERIAL PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE,
    tier            TEXT CHECK (tier IN ('A','B','C')) DEFAULT 'B',
    ats_name        TEXT,                       -- greenhouse | ashby | lever | workday | manual
    ats_token       TEXT,                       -- board token / org slug / tenant id
    careers_url     TEXT,
    snoozed_until   DATE,
    notes           TEXT,
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- ─── roles ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS roles (
    id                SERIAL PRIMARY KEY,
    company_id        INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    ats_job_id        TEXT NOT NULL,
    title             TEXT NOT NULL,
    location          TEXT,
    remote_flag       BOOLEAN DEFAULT FALSE,
    department        TEXT,
    url               TEXT,
    description_hash  TEXT,                      -- drives change detection
    posted_at         TIMESTAMPTZ,               -- when the ATS says it was posted
    first_seen        TIMESTAMPTZ DEFAULT now(),
    last_seen         TIMESTAMPTZ DEFAULT now(),
    status            TEXT CHECK (status IN ('open','changed','closed')) DEFAULT 'open',
    -- scoring (filled by the Claude scorer)
    fit_score         REAL,
    score_tier        TEXT,                      -- A | B | C | pass
    domain            TEXT,
    why_fit           TEXT,
    concerns          TEXT,
    curriculum_hook   TEXT,
    tc_estimate       TEXT,
    is_product_pm     BOOLEAN,
    scored_at         TIMESTAMPTZ,
    embedding         vector(1536),
    UNIQUE (company_id, ats_job_id)
);
CREATE INDEX IF NOT EXISTS idx_roles_status   ON roles(status);
CREATE INDEX IF NOT EXISTS idx_roles_fit       ON roles(fit_score DESC);
CREATE INDEX IF NOT EXISTS idx_roles_last_seen ON roles(last_seen);

-- ─── applications (the pipeline) ────────────────────────────
CREATE TABLE IF NOT EXISTS applications (
    id               SERIAL PRIMARY KEY,
    role_id          INTEGER REFERENCES roles(id) ON DELETE SET NULL,
    -- frozen snapshot, because postings disappear
    company_name     TEXT,
    role_title       TEXT,
    role_url         TEXT,
    stage            TEXT CHECK (stage IN
                       ('watching','drafting','applied','screen','onsite','offer','closed'))
                       DEFAULT 'watching',
    outcome          TEXT,                       -- won | lost | withdrawn | null
    applied_at       TIMESTAMPTZ,
    next_action      TEXT,
    next_action_due  DATE,
    notes            TEXT,
    created_at       TIMESTAMPTZ DEFAULT now(),
    updated_at       TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_app_stage ON applications(stage);

-- ─── application_events (stage history) ─────────────────────
CREATE TABLE IF NOT EXISTS application_events (
    id               SERIAL PRIMARY KEY,
    application_id   INTEGER NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    from_stage       TEXT,
    to_stage         TEXT,
    note             TEXT,
    at               TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_app_events_app ON application_events(application_id);

-- ─── contacts ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS contacts (
    id           SERIAL PRIMARY KEY,
    company_id   INTEGER REFERENCES companies(id) ON DELETE CASCADE,
    name         TEXT,
    role         TEXT,
    email        TEXT,
    linkedin     TEXT,
    warmth       TEXT,                            -- cold | warm | hot
    notes        TEXT,
    created_at   TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_contacts_company ON contacts(company_id);

-- ─── scan_runs (health + cost telemetry) ────────────────────
CREATE TABLE IF NOT EXISTS scan_runs (
    id                  SERIAL PRIMARY KEY,
    started_at          TIMESTAMPTZ DEFAULT now(),
    finished_at         TIMESTAMPTZ,
    companies_scanned   INTEGER DEFAULT 0,
    new_count           INTEGER DEFAULT 0,
    changed_count       INTEGER DEFAULT 0,
    closed_count        INTEGER DEFAULT 0,
    claude_tokens_in    INTEGER DEFAULT 0,
    claude_tokens_out   INTEGER DEFAULT 0,
    est_cost_usd        REAL DEFAULT 0,
    errors              TEXT
);

-- ─── daily_briefs ───────────────────────────────────────────
CREATE TABLE IF NOT EXISTS daily_briefs (
    id           SERIAL PRIMARY KEY,
    brief_date   DATE UNIQUE,
    markdown     TEXT,
    new_count    INTEGER DEFAULT 0,
    action_count INTEGER DEFAULT 0,
    created_at   TIMESTAMPTZ DEFAULT now()
);

-- ─── push_subscriptions (web push) ──────────────────────────
CREATE TABLE IF NOT EXISTS push_subscriptions (
    id           SERIAL PRIMARY KEY,
    endpoint     TEXT NOT NULL UNIQUE,
    p256dh       TEXT NOT NULL,
    auth         TEXT NOT NULL,
    created_at   TIMESTAMPTZ DEFAULT now()
);
