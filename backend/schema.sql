-- ============================================================================
-- Dispatch — full Postgres schema (Supabase-ready)
--
-- You do not have to run this. Pointing DATABASE_URL at an empty Postgres and
-- starting the app creates every table on boot, and app/schema.py adds any
-- column a later version introduced. This file exists so the shape is
-- reviewable, diffable and reproducible without booting anything — and so it
-- can be pasted straight into the Supabase SQL editor.
--
-- Generated from backend/app/models.py, then hand-finished for Postgres:
--   * JSON  -> JSONB       (indexable, and stored parsed rather than as text)
--   * DEFAULT clauses added, because SQLAlchemy applies its defaults in Python.
--     Without them a row inserted by hand, or through the Supabase table
--     editor, would come out with NULLs in NOT NULL columns.
--   * CHECK constraints on the columns that are really enums. The API already
--     rejects anything else with a 400; this stops a hand-edited row doing
--     what a request cannot.
--
-- ─── One thing not to "fix" ────────────────────────────────────────────────
-- Every timestamp is TIMESTAMP WITHOUT TIME ZONE and every one holds UTC.
-- That is deliberate and the application depends on it: models.py converts to
-- and from the team's clock in exactly one place (working_label / from_working)
-- and treats what comes back from the database as naive UTC. Switching these
-- to TIMESTAMPTZ would make Postgres apply a second conversion on top of the
-- app's, and every interview time would be wrong by your server's offset.
--
-- Safe to run more than once: every statement is IF NOT EXISTS.
-- ============================================================================

BEGIN;

-- ─── users ──────────────────────────────────────────────────────────────────
-- A person who signs in. A manager runs cycles, a BD works profiles, a
-- developer is the person those profiles actually sell.
CREATE TABLE IF NOT EXISTS users (
    id                SERIAL PRIMARY KEY,
    email             VARCHAR(255) NOT NULL,
    name              VARCHAR(120) NOT NULL,
    password_hash     VARCHAR(255) NOT NULL,
    role              VARCHAR(16)  NOT NULL DEFAULT 'bd',
    is_active         BOOLEAN      NOT NULL DEFAULT TRUE,
    -- Whether this person may open their own dashboard. Off until a manager
    -- turns it on, so nobody is measured on a screen before somebody decided
    -- to measure them.
    dashboard_visible BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at        TIMESTAMP    DEFAULT (now() AT TIME ZONE 'utc'),
    CONSTRAINT ck_users_role CHECK (role IN ('admin', 'bd', 'dev'))
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email ON users (email);

-- ─── profiles ───────────────────────────────────────────────────────────────
-- The identity a job is applied under — "Khuram, AI Engineer" on Upwork.
-- The unit of work in this system is the profile, never the person: one person
-- may run several, and a profile may be handed between people.
--
-- Two people stand behind a profile. user_id is the BD who runs the account
-- and does the typing; dev_user_id is the developer the profile sells — the
-- one who sits the interview. Either may be empty.
CREATE TABLE IF NOT EXISTS profiles (
    id             SERIAL PRIMARY KEY,
    name           VARCHAR(120) NOT NULL,
    headline       VARCHAR(160) NOT NULL DEFAULT '',
    platform       VARCHAR(120) NOT NULL DEFAULT '',
    user_id        INTEGER REFERENCES users (id),
    is_active      BOOLEAN      NOT NULL DEFAULT TRUE,
    -- Whether this profile appears on the shared team board.
    share_progress BOOLEAN      NOT NULL DEFAULT TRUE,

    -- The developer behind the identity, and what a client is handed. These
    -- describe a person but live on the profile, because what a client
    -- receives is the profile — one developer running two identities may well
    -- send two different resumes into two different markets.
    dev_user_id    INTEGER REFERENCES users (id),
    email          VARCHAR(255) NOT NULL DEFAULT '',
    resume_url     TEXT         NOT NULL DEFAULT '',
    skills         VARCHAR(400) NOT NULL DEFAULT '',
    timezone       VARCHAR(64)  NOT NULL DEFAULT '',
    rate           VARCHAR(40)  NOT NULL DEFAULT '',
    availability   VARCHAR(16)  NOT NULL DEFAULT 'open',
    bio            TEXT         NOT NULL DEFAULT '',

    created_at     TIMESTAMP DEFAULT (now() AT TIME ZONE 'utc'),
    CONSTRAINT ck_profiles_availability
        CHECK (availability IN ('open', 'limited', 'booked'))
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_profiles_name        ON profiles (name);
CREATE INDEX        IF NOT EXISTS ix_profiles_user_id     ON profiles (user_id);
CREATE INDEX        IF NOT EXISTS ix_profiles_dev_user_id ON profiles (dev_user_id);

-- ─── settings ───────────────────────────────────────────────────────────────
-- Workspace switches the manager holds. One row per key, so a new switch is a
-- new row rather than a migration.
CREATE TABLE IF NOT EXISTS settings (
    key        VARCHAR(64) PRIMARY KEY,
    value      JSONB DEFAULT '{}'::jsonb,
    updated_at TIMESTAMP DEFAULT (now() AT TIME ZONE 'utc')
);

-- ─── batches ────────────────────────────────────────────────────────────────
-- One dispatch cycle. Sheets go in, lists come out. A cycle stays `open` while
-- people work it and the lists rebuild on a timer; closing it stops that.
CREATE TABLE IF NOT EXISTS batches (
    id                 SERIAL PRIMARY KEY,
    name               VARCHAR(160) NOT NULL,
    status             VARCHAR(16)  NOT NULL DEFAULT 'open',
    mode               VARCHAR(16)  NOT NULL DEFAULT 'cover',
    quota              INTEGER      NOT NULL DEFAULT 40,
    one_per_client     BOOLEAN      NOT NULL DEFAULT FALSE,
    created_by         INTEGER REFERENCES users (id),
    created_at         TIMESTAMP DEFAULT (now() AT TIME ZONE 'utc'),
    computed_at        TIMESTAMP,
    report             JSONB DEFAULT '{}'::jsonb,

    -- Minutes between automatic rebuilds; 0 means only when asked.
    auto_build_minutes INTEGER NOT NULL DEFAULT 10,
    last_built_at      TIMESTAMP,
    -- Held for the duration of a build, so two workers cannot rebuild one
    -- cycle at once.
    building_since     TIMESTAMP,
    CONSTRAINT ck_batches_status CHECK (status IN ('open', 'computed')),
    CONSTRAINT ck_batches_mode   CHECK (mode   IN ('cover', 'split'))
);

-- ─── jobs ───────────────────────────────────────────────────────────────────
-- A posting, identified by fingerprint. Global rather than per-cycle, so
-- history carries across cycles.
CREATE TABLE IF NOT EXISTS jobs (
    id              SERIAL PRIMARY KEY,
    fingerprint     VARCHAR(400) NOT NULL,
    tier            VARCHAR(8),
    title           VARCHAR(500),
    company         VARCHAR(300),
    company_key     VARCHAR(300),
    platform        VARCHAR(120),
    url             TEXT,
    -- Where the posting itself is written out, when that is not the apply
    -- link. Never part of a fingerprint: two profiles can hold two different
    -- links to one job's description, and matching on it would split one
    -- posting in two.
    description_url TEXT NOT NULL DEFAULT '',
    first_seen      TIMESTAMP DEFAULT (now() AT TIME ZONE 'utc')
);
CREATE UNIQUE INDEX IF NOT EXISTS ix_jobs_fingerprint ON jobs (fingerprint);
CREATE INDEX        IF NOT EXISTS ix_jobs_company_key ON jobs (company_key);

-- ─── uploads ────────────────────────────────────────────────────────────────
-- A raw sheet, handed in for one profile. Rows are kept verbatim so the column
-- mapping stays editable until the cycle is computed.
CREATE TABLE IF NOT EXISTS uploads (
    id         SERIAL PRIMARY KEY,
    batch_id   INTEGER REFERENCES batches (id) ON DELETE CASCADE,
    profile_id INTEGER REFERENCES profiles (id),
    user_id    INTEGER REFERENCES users (id),
    filename   VARCHAR(255),
    row_count  INTEGER DEFAULT 0,
    headers    JSONB DEFAULT '[]'::jsonb,
    mapping    JSONB DEFAULT '{}'::jsonb,
    rows       JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMP DEFAULT (now() AT TIME ZONE 'utc'),
    CONSTRAINT uq_sheet_per_profile UNIQUE (batch_id, profile_id)
);
CREATE INDEX IF NOT EXISTS ix_uploads_batch_id   ON uploads (batch_id);
CREATE INDEX IF NOT EXISTS ix_uploads_profile_id ON uploads (profile_id);
CREATE INDEX IF NOT EXISTS ix_uploads_user_id    ON uploads (user_id);

-- ─── applications ───────────────────────────────────────────────────────────
-- All-time history: this profile has approached this job. Never re-issued.
--
-- The UNIQUE is per (job, PROFILE), not per (job, user). That is the whole
-- point of the v2 schema: one person's two profiles are two candidates and may
-- both apply to the same posting. Only the same identity twice is forbidden.
CREATE TABLE IF NOT EXISTS applications (
    id         SERIAL PRIMARY KEY,
    job_id     INTEGER REFERENCES jobs (id) ON DELETE CASCADE,
    profile_id INTEGER REFERENCES profiles (id),
    user_id    INTEGER REFERENCES users (id),
    batch_id   INTEGER REFERENCES batches (id),
    -- What the BD typed on their sheet, kept verbatim. created_at is the day
    -- the cycle was built, which is a different day.
    applied_on VARCHAR(40),
    created_at TIMESTAMP DEFAULT (now() AT TIME ZONE 'utc'),
    CONSTRAINT uq_application UNIQUE (job_id, profile_id)
);
CREATE INDEX IF NOT EXISTS ix_applications_job_id     ON applications (job_id);
CREATE INDEX IF NOT EXISTS ix_applications_profile_id ON applications (profile_id);

-- ─── batch_applications ─────────────────────────────────────────────────────
-- Who applied to what, in THIS cycle. `applications` is all-time and unique
-- per (job, profile), so it cannot say who collided in cycle 12 once cycle 13
-- exists — the row belongs to whichever cycle saw it first.
CREATE TABLE IF NOT EXISTS batch_applications (
    id         SERIAL PRIMARY KEY,
    batch_id   INTEGER REFERENCES batches (id) ON DELETE CASCADE,
    job_id     INTEGER REFERENCES jobs (id) ON DELETE CASCADE,
    profile_id INTEGER REFERENCES profiles (id),
    CONSTRAINT uq_batch_application UNIQUE (batch_id, job_id, profile_id)
);
CREATE INDEX IF NOT EXISTS ix_batch_applications_batch_id   ON batch_applications (batch_id);
CREATE INDEX IF NOT EXISTS ix_batch_applications_job_id     ON batch_applications (job_id);
CREATE INDEX IF NOT EXISTS ix_batch_applications_profile_id ON batch_applications (profile_id);

-- ─── assignments ────────────────────────────────────────────────────────────
-- A job placed on one profile's list for one cycle.
CREATE TABLE IF NOT EXISTS assignments (
    id         SERIAL PRIMARY KEY,
    batch_id   INTEGER REFERENCES batches (id) ON DELETE CASCADE,
    job_id     INTEGER REFERENCES jobs (id) ON DELETE CASCADE,
    profile_id INTEGER REFERENCES profiles (id),
    user_id    INTEGER REFERENCES users (id),
    status     VARCHAR(16) DEFAULT 'pending',
    -- Mirrors the cycle's mode onto the row so the partial index below can
    -- hold the split-mode guarantee in the database.
    exclusive  BOOLEAN NOT NULL DEFAULT FALSE,
    status_changed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT (now() AT TIME ZONE 'utc'),
    CONSTRAINT uq_job_per_profile UNIQUE (batch_id, job_id, profile_id),
    CONSTRAINT ck_assignments_status
        CHECK (status IN ('pending', 'applied', 'skipped'))
);
CREATE INDEX IF NOT EXISTS ix_assignments_batch_id   ON assignments (batch_id);
CREATE INDEX IF NOT EXISTS ix_assignments_job_id     ON assignments (job_id);
CREATE INDEX IF NOT EXISTS ix_assignments_profile_id ON assignments (profile_id);
CREATE INDEX IF NOT EXISTS ix_assignments_user_id    ON assignments (user_id);

-- PARTIAL on purpose. A split cycle must never hand one posting to two
-- profiles; a coverage cycle deliberately hands one job to everybody eligible,
-- and a blanket constraint would forbid the normal case.
CREATE UNIQUE INDEX IF NOT EXISTS uq_job_dispatched_once
    ON assignments (batch_id, job_id) WHERE exclusive = TRUE;

-- ─── interviews ─────────────────────────────────────────────────────────────
-- A client wanting to talk to whoever is behind a profile. The first table
-- here that records an OUTCOME: everything before it counts effort, and a team
-- can improve all of that without winning a single piece of work.
--
-- Two people write different halves. The BD books it (time, client, link,
-- brief); the developer says what came of it (status, outcome, debrief).
CREATE TABLE IF NOT EXISTS interviews (
    id               SERIAL PRIMARY KEY,
    profile_id       INTEGER NOT NULL REFERENCES profiles (id) ON DELETE CASCADE,
    job_id           INTEGER REFERENCES jobs (id),
    client           VARCHAR(300) NOT NULL DEFAULT '',
    role             VARCHAR(300) NOT NULL DEFAULT '',
    -- UTC. What the team typed was Eastern; the app converts both ways.
    scheduled_at     TIMESTAMP NOT NULL,
    duration_minutes INTEGER   NOT NULL DEFAULT 30,
    mode             VARCHAR(16) NOT NULL DEFAULT 'video',
    link             TEXT        NOT NULL DEFAULT '',
    -- `draft` is a reply with no time agreed yet. It counts towards nothing
    -- until somebody puts an hour on it.
    status           VARCHAR(16) NOT NULL DEFAULT 'scheduled',
    -- Where on the ladder this sitting is. On the interview rather than the
    -- job, because one job produces several and each is at a different rung.
    stage            VARCHAR(16) NOT NULL DEFAULT 'screening',
    outcome          VARCHAR(16) NOT NULL DEFAULT 'pending',
    -- The BD's brief, written when it was booked.
    notes            TEXT NOT NULL DEFAULT '',
    -- The developer's account afterwards. A separate column so one cannot be
    -- typed over the other — there is no second copy of either.
    debrief          TEXT NOT NULL DEFAULT '',
    reported_by      INTEGER REFERENCES users (id),
    reported_at      TIMESTAMP,
    -- The round this one follows on from. SET NULL rather than CASCADE:
    -- removing a mistyped screening call must not take the real technical
    -- round with it.
    previous_id      INTEGER REFERENCES interviews (id) ON DELETE SET NULL,
    created_by       INTEGER REFERENCES users (id),
    created_at       TIMESTAMP DEFAULT (now() AT TIME ZONE 'utc'),
    updated_at       TIMESTAMP DEFAULT (now() AT TIME ZONE 'utc'),

    CONSTRAINT ck_interviews_mode
        CHECK (mode IN ('video', 'call', 'onsite', 'async')),
    CONSTRAINT ck_interviews_status
        CHECK (status IN ('draft', 'scheduled', 'done', 'cancelled', 'no_show')),
    CONSTRAINT ck_interviews_stage
        CHECK (stage IN ('screening', 'technical', 'assessment', 'final', 'offer')),
    CONSTRAINT ck_interviews_outcome
        CHECK (outcome IN ('pending', 'passed', 'offer', 'hired', 'rejected'))
);
CREATE INDEX IF NOT EXISTS ix_interviews_profile_id   ON interviews (profile_id);
CREATE INDEX IF NOT EXISTS ix_interviews_job_id       ON interviews (job_id);
CREATE INDEX IF NOT EXISTS ix_interviews_scheduled_at ON interviews (scheduled_at);
CREATE INDEX IF NOT EXISTS ix_interviews_previous_id  ON interviews (previous_id);
-- What every screen asks — what is next for this profile — in the order the
-- screens want it.
CREATE INDEX IF NOT EXISTS ix_interview_profile_time
    ON interviews (profile_id, scheduled_at);

-- ─── assessments ────────────────────────────────────────────────────────────
-- A take-home, a test, a written exercise. Its own table rather than a field
-- on an interview, because a client can send a test before anybody has spoken
-- and an assessment that could only exist under an interview would force
-- somebody to invent a call that never happened.
CREATE TABLE IF NOT EXISTS assessments (
    id             SERIAL PRIMARY KEY,
    profile_id     INTEGER NOT NULL REFERENCES profiles (id) ON DELETE CASCADE,
    interview_id   INTEGER REFERENCES interviews (id) ON DELETE SET NULL,
    job_id         INTEGER REFERENCES jobs (id),

    -- The BD's half: the client sent them the brief, the link and the deadline.
    title          VARCHAR(300) NOT NULL DEFAULT '',
    client         VARCHAR(300) NOT NULL DEFAULT '',
    brief          TEXT NOT NULL DEFAULT '',
    link           TEXT NOT NULL DEFAULT '',
    -- Nullable on purpose. Plenty of clients send a test with no deadline at
    -- all, and inventing one puts a red flag on a screen that nobody set.
    due_at         TIMESTAMP,

    -- The developer's half.
    status         VARCHAR(16) NOT NULL DEFAULT 'sent',
    submission_url TEXT NOT NULL DEFAULT '',
    notes          TEXT NOT NULL DEFAULT '',
    submitted_at   TIMESTAMP,

    created_by     INTEGER REFERENCES users (id),
    updated_by     INTEGER REFERENCES users (id),
    created_at     TIMESTAMP DEFAULT (now() AT TIME ZONE 'utc'),
    updated_at     TIMESTAMP DEFAULT (now() AT TIME ZONE 'utc'),

    CONSTRAINT ck_assessments_status
        CHECK (status IN ('sent', 'in_progress', 'submitted', 'passed', 'failed'))
);
CREATE INDEX IF NOT EXISTS ix_assessments_profile_id   ON assessments (profile_id);
CREATE INDEX IF NOT EXISTS ix_assessments_interview_id ON assessments (interview_id);
CREATE INDEX IF NOT EXISTS ix_assessments_job_id       ON assessments (job_id);
CREATE INDEX IF NOT EXISTS ix_assessments_due_at       ON assessments (due_at);
-- What is outstanding for this identity, soonest deadline first.
CREATE INDEX IF NOT EXISTS ix_assessment_profile_due
    ON assessments (profile_id, due_at);

COMMIT;


-- ============================================================================
-- Supabase: lock the auto-generated REST API out of these tables
-- ============================================================================
--
-- Supabase publishes a PostgREST API over every table in `public` and reaches
-- it with the `anon` and `authenticated` roles. This app does not use that API
-- at all — it connects as a normal Postgres user over the connection string —
-- but the API is on by default, and an anon key is a public value.
--
-- Turning RLS on with NO policies is the fix. RLS denies by default, so the
-- REST API returns nothing to anybody, while the app's own connection is
-- unaffected: the `postgres` role Supabase gives you in the connection string
-- has BYPASSRLS.
--
-- It also clears Supabase's "RLS disabled in public" security warning, which
-- is otherwise about to be right.
--
-- Run this. It is not optional if the project is on the internet.

ALTER TABLE users              ENABLE ROW LEVEL SECURITY;
ALTER TABLE profiles           ENABLE ROW LEVEL SECURITY;
ALTER TABLE settings           ENABLE ROW LEVEL SECURITY;
ALTER TABLE batches            ENABLE ROW LEVEL SECURITY;
ALTER TABLE jobs               ENABLE ROW LEVEL SECURITY;
ALTER TABLE uploads            ENABLE ROW LEVEL SECURITY;
ALTER TABLE applications       ENABLE ROW LEVEL SECURITY;
ALTER TABLE batch_applications ENABLE ROW LEVEL SECURITY;
ALTER TABLE assignments        ENABLE ROW LEVEL SECURITY;
ALTER TABLE interviews         ENABLE ROW LEVEL SECURITY;
ALTER TABLE assessments        ENABLE ROW LEVEL SECURITY;

-- Belt and braces: take the grants away too, so the REST API cannot see the
-- tables even if RLS is later switched off by accident.
REVOKE ALL ON ALL TABLES    IN SCHEMA public FROM anon, authenticated;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM anon, authenticated;


-- ============================================================================
-- Sanity check — run after the app has booted once
-- ============================================================================
--
--   SELECT table_name FROM information_schema.tables
--    WHERE table_schema = 'public' ORDER BY table_name;
--
-- Expect exactly eleven: applications, assessments, assignments,
-- batch_applications, batches, interviews, jobs, profiles, settings, uploads,
-- users.
--
-- The first manager account is not created here. Set ADMIN_EMAIL and
-- ADMIN_PASSWORD on the service and the app makes it once, on an empty
-- database; sign in, change the password, then clear both variables.
-- ============================================================================
