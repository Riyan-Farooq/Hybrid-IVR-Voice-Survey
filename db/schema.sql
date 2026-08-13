-- Survey system schema (SQLite dialect; see MIGRATION NOTES at the bottom for MySQL)
--
-- Layout:
--   Definition : surveys -> questions -> question_options
--   Targeting  : contacts, campaigns
--   Execution  : calls -> survey_sessions
--   Results    : responses (one per question) + response_attempts (full audit)
--   Diagnostics: call_events

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

-- ---------------------------------------------------------------- definition

CREATE TABLE IF NOT EXISTS surveys (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    survey_key   TEXT    NOT NULL,
    version      INTEGER NOT NULL DEFAULT 1,
    title        TEXT    NOT NULL,
    description  TEXT,
    locale       TEXT    NOT NULL DEFAULT 'en-US',
    intro_text   TEXT,
    intro_audio  TEXT,
    outro_text   TEXT,
    outro_audio  TEXT,
    status       TEXT    NOT NULL DEFAULT 'draft'
                 CHECK (status IN ('draft', 'active', 'archived')),
    metadata     TEXT,
    created_at   TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at   TEXT,
    UNIQUE (survey_key, version)
);

CREATE TABLE IF NOT EXISTS questions (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    survey_id        INTEGER NOT NULL REFERENCES surveys(id) ON DELETE CASCADE,
    question_key     TEXT    NOT NULL,
    position         INTEGER NOT NULL,
    text             TEXT    NOT NULL,
    prompt_audio     TEXT,
    question_type    TEXT    NOT NULL DEFAULT 'dtmf_choice'
                     CHECK (question_type IN ('dtmf_choice', 'dtmf_numeric', 'yes_no',
                                              'rating', 'speech', 'info')),
    min_digits       INTEGER NOT NULL DEFAULT 1,
    max_digits       INTEGER NOT NULL DEFAULT 1,
    terminator       TEXT             DEFAULT '#',
    input_timeout_ms INTEGER NOT NULL DEFAULT 15000,
    max_attempts     INTEGER NOT NULL DEFAULT 3,
    is_required      INTEGER NOT NULL DEFAULT 1 CHECK (is_required IN (0, 1)),
    metadata         TEXT,
    created_at       TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE (survey_id, question_key),
    UNIQUE (survey_id, position)
);

CREATE TABLE IF NOT EXISTS question_options (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    question_id      INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    option_key       TEXT    NOT NULL,
    label            TEXT    NOT NULL,
    numeric_value    REAL,
    position         INTEGER NOT NULL,
    -- NULL means "fall through to the next question by position"
    next_question_id INTEGER REFERENCES questions(id) ON DELETE SET NULL,
    is_terminal      INTEGER NOT NULL DEFAULT 0 CHECK (is_terminal IN (0, 1)),
    metadata         TEXT,
    UNIQUE (question_id, option_key)
);

-- ---------------------------------------------------------------- targeting

CREATE TABLE IF NOT EXISTS contacts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    external_id  TEXT UNIQUE,
    phone_number TEXT NOT NULL,
    display_name TEXT,
    locale       TEXT,
    do_not_call  INTEGER NOT NULL DEFAULT 0 CHECK (do_not_call IN (0, 1)),
    metadata     TEXT,
    created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS campaigns (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    survey_id                INTEGER NOT NULL REFERENCES surveys(id),
    name                     TEXT    NOT NULL,
    status                   TEXT    NOT NULL DEFAULT 'draft'
                             CHECK (status IN ('draft', 'running', 'paused',
                                               'completed', 'cancelled')),
    max_attempts_per_contact INTEGER NOT NULL DEFAULT 3,
    retry_delay_minutes      INTEGER NOT NULL DEFAULT 60,
    scheduled_start          TEXT,
    scheduled_end            TEXT,
    metadata                 TEXT,
    created_at               TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- ---------------------------------------------------------------- execution

CREATE TABLE IF NOT EXISTS calls (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    call_uuid        TEXT    NOT NULL UNIQUE,
    campaign_id      INTEGER REFERENCES campaigns(id) ON DELETE SET NULL,
    contact_id       INTEGER REFERENCES contacts(id)  ON DELETE SET NULL,
    direction        TEXT    NOT NULL DEFAULT 'outbound'
                     CHECK (direction IN ('outbound', 'inbound')),
    from_number      TEXT,
    to_number        TEXT    NOT NULL,
    sip_gateway      TEXT,
    attempt_no       INTEGER NOT NULL DEFAULT 1,
    status           TEXT    NOT NULL DEFAULT 'queued'
                     CHECK (status IN ('queued', 'dialing', 'ringing', 'answered',
                                       'completed', 'partial', 'no_answer', 'busy',
                                       'rejected', 'failed', 'abandoned')),
    hangup_cause     TEXT,
    initiated_at     TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    answered_at      TEXT,
    ended_at         TEXT,
    ring_seconds     INTEGER,
    talk_seconds     INTEGER,
    duration_seconds INTEGER,
    recording_path   TEXT,
    error_message    TEXT,
    metadata         TEXT
);

CREATE TABLE IF NOT EXISTS survey_sessions (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    session_uuid       TEXT    NOT NULL UNIQUE,
    survey_id          INTEGER NOT NULL REFERENCES surveys(id),
    call_id            INTEGER REFERENCES calls(id)    ON DELETE CASCADE,
    contact_id         INTEGER REFERENCES contacts(id) ON DELETE SET NULL,
    channel            TEXT    NOT NULL DEFAULT 'voice'
                       CHECK (channel IN ('voice', 'sms', 'web', 'test')),
    status             TEXT    NOT NULL DEFAULT 'in_progress'
                       CHECK (status IN ('in_progress', 'completed', 'partial',
                                         'abandoned', 'failed')),
    questions_total    INTEGER NOT NULL DEFAULT 0,
    questions_answered INTEGER NOT NULL DEFAULT 0,
    started_at         TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    completed_at       TEXT,
    metadata           TEXT,
    UNIQUE (call_id, survey_id)
);

-- ---------------------------------------------------------------- results

CREATE TABLE IF NOT EXISTS responses (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id    INTEGER NOT NULL REFERENCES survey_sessions(id) ON DELETE CASCADE,
    question_id   INTEGER NOT NULL REFERENCES questions(id),
    option_id     INTEGER REFERENCES question_options(id),
    raw_input     TEXT,
    numeric_value REAL,
    text_value    TEXT,
    outcome       TEXT    NOT NULL DEFAULT 'answered'
                  CHECK (outcome IN ('answered', 'no_input', 'invalid',
                                     'skipped', 'hangup', 'error')),
    attempts_used INTEGER NOT NULL DEFAULT 1,
    response_ms   INTEGER,
    answered_at   TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE (session_id, question_id)
);

CREATE TABLE IF NOT EXISTS response_attempts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  INTEGER NOT NULL REFERENCES survey_sessions(id) ON DELETE CASCADE,
    question_id INTEGER NOT NULL REFERENCES questions(id),
    attempt_no  INTEGER NOT NULL,
    raw_input   TEXT,
    outcome     TEXT    NOT NULL
                CHECK (outcome IN ('valid', 'invalid', 'no_input',
                                   'terminator', 'hangup', 'error')),
    response_ms INTEGER,
    occurred_at TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE (session_id, question_id, attempt_no)
);

-- ---------------------------------------------------------------- diagnostics

CREATE TABLE IF NOT EXISTS call_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    call_id     INTEGER REFERENCES calls(id)            ON DELETE CASCADE,
    session_id  INTEGER REFERENCES survey_sessions(id)  ON DELETE CASCADE,
    event_type  TEXT    NOT NULL,
    payload     TEXT,
    occurred_at TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- ---------------------------------------------------------------- indexes

CREATE INDEX IF NOT EXISTS idx_questions_survey        ON questions(survey_id, position);
CREATE INDEX IF NOT EXISTS idx_options_question        ON question_options(question_id, position);
CREATE INDEX IF NOT EXISTS idx_contacts_phone          ON contacts(phone_number);
CREATE INDEX IF NOT EXISTS idx_calls_contact           ON calls(contact_id, initiated_at);
CREATE INDEX IF NOT EXISTS idx_calls_campaign_status   ON calls(campaign_id, status);
CREATE INDEX IF NOT EXISTS idx_calls_status_time       ON calls(status, initiated_at);
CREATE INDEX IF NOT EXISTS idx_sessions_survey_status  ON survey_sessions(survey_id, status, started_at);
CREATE INDEX IF NOT EXISTS idx_sessions_call           ON survey_sessions(call_id);
CREATE INDEX IF NOT EXISTS idx_responses_question      ON responses(question_id, option_id);
CREATE INDEX IF NOT EXISTS idx_responses_session       ON responses(session_id);
CREATE INDEX IF NOT EXISTS idx_attempts_question       ON response_attempts(question_id, outcome);
CREATE INDEX IF NOT EXISTS idx_events_call_time        ON call_events(call_id, occurred_at);

-- ---------------------------------------------------------------- views

-- Flattened answers: the workhorse for reporting.
CREATE VIEW IF NOT EXISTS v_answers AS
SELECT
    sv.survey_key,
    sv.version           AS survey_version,
    q.question_key,
    q.position           AS question_position,
    q.text               AS question_text,
    o.option_key,
    o.label              AS option_label,
    COALESCE(r.numeric_value, o.numeric_value) AS numeric_value,
    r.raw_input,
    r.outcome,
    r.attempts_used,
    r.response_ms,
    r.answered_at,
    ss.id                AS session_id,
    ss.status            AS session_status,
    ss.channel,
    c.call_uuid,
    c.to_number,
    ct.external_id       AS contact_external_id
FROM responses r
JOIN survey_sessions ss  ON ss.id = r.session_id
JOIN surveys sv          ON sv.id = ss.survey_id
JOIN questions q         ON q.id  = r.question_id
LEFT JOIN question_options o ON o.id = r.option_id
LEFT JOIN calls c        ON c.id  = ss.call_id
LEFT JOIN contacts ct    ON ct.id = ss.contact_id;

-- How answers are distributed per option.
CREATE VIEW IF NOT EXISTS v_option_distribution AS
SELECT
    survey_key,
    survey_version,
    question_key,
    question_position,
    option_key,
    option_label,
    COUNT(*) AS response_count
FROM v_answers
WHERE outcome = 'answered'
GROUP BY survey_key, survey_version, question_key, question_position,
         option_key, option_label;

-- Score per question (CSAT-style averages) using option numeric_value.
CREATE VIEW IF NOT EXISTS v_question_scores AS
SELECT
    survey_key,
    survey_version,
    question_key,
    COUNT(numeric_value)            AS scored_responses,
    ROUND(AVG(numeric_value), 3)    AS avg_score,
    MIN(numeric_value)              AS min_score,
    MAX(numeric_value)              AS max_score
FROM v_answers
WHERE outcome = 'answered' AND numeric_value IS NOT NULL
GROUP BY survey_key, survey_version, question_key;

-- Completion funnel per survey version.
CREATE VIEW IF NOT EXISTS v_survey_completion AS
SELECT
    sv.survey_key,
    sv.version AS survey_version,
    COUNT(*)                                                          AS sessions,
    SUM(CASE WHEN ss.status = 'completed' THEN 1 ELSE 0 END)          AS completed,
    SUM(CASE WHEN ss.status = 'partial'   THEN 1 ELSE 0 END)          AS partial,
    SUM(CASE WHEN ss.status = 'abandoned' THEN 1 ELSE 0 END)          AS abandoned,
    ROUND(100.0 * SUM(CASE WHEN ss.status = 'completed' THEN 1 ELSE 0 END)
          / COUNT(*), 2)                                              AS completion_rate
FROM survey_sessions ss
JOIN surveys sv ON sv.id = ss.survey_id
GROUP BY sv.survey_key, sv.version;

-- Which questions confuse people: invalid and no-input rates.
CREATE VIEW IF NOT EXISTS v_question_friction AS
SELECT
    sv.survey_key,
    q.question_key,
    COUNT(*)                                                             AS total_attempts,
    SUM(CASE WHEN ra.outcome = 'invalid'  THEN 1 ELSE 0 END)             AS invalid_attempts,
    SUM(CASE WHEN ra.outcome = 'no_input' THEN 1 ELSE 0 END)             AS no_input_attempts,
    ROUND(100.0 * SUM(CASE WHEN ra.outcome IN ('invalid', 'no_input')
                           THEN 1 ELSE 0 END) / COUNT(*), 2)             AS friction_rate
FROM response_attempts ra
JOIN questions q  ON q.id  = ra.question_id
JOIN surveys sv   ON sv.id = q.survey_id
GROUP BY sv.survey_key, q.question_key;

-- Telephony outcomes for operational dashboards.
CREATE VIEW IF NOT EXISTS v_call_outcomes AS
SELECT
    campaign_id,
    status,
    COUNT(*)                    AS calls,
    ROUND(AVG(talk_seconds), 1) AS avg_talk_seconds,
    ROUND(AVG(ring_seconds), 1) AS avg_ring_seconds
FROM calls
GROUP BY campaign_id, status;

-- ---------------------------------------------------------------- MIGRATION NOTES
--
-- Moving to MySQL 8:
--   INTEGER PRIMARY KEY AUTOINCREMENT -> BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY
--   TEXT on any indexed/unique column -> VARCHAR(n)  (e.g. call_uuid VARCHAR(64))
--   TEXT timestamps                   -> DATETIME(3), default CURRENT_TIMESTAMP(3)
--   metadata TEXT                     -> JSON
--   CHECK (x IN (...))                -> ENUM(...) or keep CHECK (8.0.16+)
--   Add: ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
--   Integer booleans (is_required, do_not_call) -> TINYINT(1)
--
-- SQLite runtime requirement: foreign keys are OFF by default and must be
-- enabled per connection with `PRAGMA foreign_keys = ON`.
