-- =============================================================================
-- ClawGrowth Database Initialization Script
-- Version: 2.0
-- Database: SQLite
-- Path: ~/.openclaw/clawgrowth/clawgrowth.db
-- Tables: 6
-- =============================================================================

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- =============================================================================
-- Table 1: agent_profiles
-- Purpose: Stores current state of each agent (updated daily)
-- =============================================================================
CREATE TABLE IF NOT EXISTS agent_profiles (
    agent_id            TEXT    PRIMARY KEY,
    display_name        TEXT,

    -- Growth
    level               INTEGER DEFAULT 1,
    total_xp            INTEGER DEFAULT 0,
    stage               TEXT    DEFAULT 'baby',   -- baby/growing/mature/expert/legend

    -- Five-dimension scores (0-100)
    efficiency_score    REAL    DEFAULT 0,
    output_score        REAL    DEFAULT 0,
    automation_score    REAL    DEFAULT 0,
    collaboration_score REAL    DEFAULT 0,
    accumulation_score  REAL    DEFAULT 0,
    total_score         REAL    DEFAULT 0,

    -- Four status values (0-100)
    energy              REAL    DEFAULT 100,
    health              REAL    DEFAULT 100,
    mood                REAL    DEFAULT 50,
    hunger              REAL    DEFAULT 100,

    updated_at          TEXT    DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================================
-- Table 2: daily_snapshots
-- Purpose: Daily aggregated metrics per agent (inserted once per day)
-- =============================================================================
CREATE TABLE IF NOT EXISTS daily_snapshots (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id                    TEXT    NOT NULL,
    date                        TEXT    NOT NULL,   -- YYYY-MM-DD

    -- Session activity (from sessions/*.jsonl)
    conversations               INTEGER DEFAULT 0,
    tool_calls                  INTEGER DEFAULT 0,
    unique_tools                INTEGER DEFAULT 0,
    input_tokens                INTEGER DEFAULT 0,
    output_tokens               INTEGER DEFAULT 0,
    cache_read                  INTEGER DEFAULT 0,
    tool_errors                 INTEGER DEFAULT 0,

    -- Cron automation (from cron/runs/*.jsonl)
    cron_runs                   INTEGER DEFAULT 0,
    cron_success                INTEGER DEFAULT 0,
    cron_error_count            INTEGER DEFAULT 0,
    avg_duration_ms             REAL    DEFAULT 0,

    -- Collaboration (from subagents/runs.json)
    collaborations              INTEGER DEFAULT 0,
    collab_success              INTEGER DEFAULT 0,
    collab_agents               INTEGER DEFAULT 0,

    -- Workspace — knowledge accumulation
    skills_count                INTEGER DEFAULT 0,
    memories_count              INTEGER DEFAULT 0,
    memories_words              INTEGER DEFAULT 0,  -- total memory chars
    has_today_memory             INTEGER DEFAULT 0,  -- 0/1 boolean
    recent_memory_count          INTEGER DEFAULT 0,  -- memories modified in last 7 days
    learnings_count             INTEGER DEFAULT 0,  -- ## sections in LEARNINGS.md
    learnings_words             INTEGER DEFAULT 0,  -- recent learning word count
    errors_count                INTEGER DEFAULT 0,  -- ## sections in ERRORS.md
    feature_requests_count      INTEGER DEFAULT 0,  -- ## sections in FEATURE_REQUESTS.md
    recent_feature_requests     INTEGER DEFAULT 0,  -- feature requests in last 7 days
    memory_sections             INTEGER DEFAULT 0,  -- ## sections in MEMORY.md
    memory_words                INTEGER DEFAULT 0,  -- total MEMORY.md char count

    -- Workspace — TOOLS.md metrics
    tools_skills_installed      INTEGER DEFAULT 0,  -- count of '✅ 已安装：' lines
    tools_external_integrations INTEGER DEFAULT 0,  -- unique http(s):// hostnames
    tools_md_updated_days_ago   INTEGER DEFAULT 0,  -- days since TOOLS.md was updated

    -- Session state (from sessions.json, current session only)
    total_tokens                INTEGER DEFAULT 0,
    context_tokens              INTEGER DEFAULT 0,
    context_usage               REAL    DEFAULT 0,  -- total_tokens / context_tokens × 100
    compaction_count            INTEGER DEFAULT 0,
    hours_since_active          REAL    DEFAULT 0,

    -- Shared workspace — team commander metrics (agent_id = '__shared__')
    heartbeat_hours_ago         REAL    DEFAULT 0,  -- from heartbeat-state.json
    heartbeat_daily_count       INTEGER DEFAULT 0,
    last_task_hours_ago         REAL    DEFAULT 0,
    projects_active_count       INTEGER DEFAULT 0,  -- from PROJECT_STATUS.md
    tasks_blocked               INTEGER DEFAULT 0,
    tasks_overdue               INTEGER DEFAULT 0,
    decisions_count             INTEGER DEFAULT 0,  -- from DECISIONS.md
    recent_decisions_count      INTEGER DEFAULT 0,  -- decisions in last 7 days
    reports_count               INTEGER DEFAULT 0,  -- files in reports/
    recent_reports_count        INTEGER DEFAULT 0,
    collections_count           INTEGER DEFAULT 0,  -- files in collections/
    handoffs_count              INTEGER DEFAULT 0,  -- files in handoffs/

    -- Five-dimension scores (0-100)
    efficiency_score            REAL    DEFAULT 0,
    output_score                REAL    DEFAULT 0,
    automation_score            REAL    DEFAULT 0,
    collaboration_score         REAL    DEFAULT 0,
    accumulation_score          REAL    DEFAULT 0,
    total_score                 REAL    DEFAULT 0,

    -- Four status values (0-100, EMA-smoothed)
    energy                      REAL    DEFAULT 0,
    health                      REAL    DEFAULT 0,
    mood                        REAL    DEFAULT 0,
    hunger                      REAL    DEFAULT 0,

    -- XP earned on this day
    xp_gained                   INTEGER DEFAULT 0,

    created_at                  TEXT    DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(agent_id, date)
);

CREATE INDEX IF NOT EXISTS idx_snapshots_agent_date
    ON daily_snapshots(agent_id, date DESC);

CREATE INDEX IF NOT EXISTS idx_snapshots_date
    ON daily_snapshots(date DESC);

-- =============================================================================
-- Table 3: tool_call_logs
-- Purpose: Per-tool-call event log (rolling 90-day retention)
-- Source: agents/<id>/sessions/*.jsonl → type=message, content[].type=toolCall
-- =============================================================================
CREATE TABLE IF NOT EXISTS tool_call_logs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id      TEXT    NOT NULL,
    session_id    TEXT,                     -- session file stem (UUID)

    -- Tool info
    tool_name     TEXT,                     -- read / write / exec / web_search ...
    tool_category TEXT,                     -- file / exec / search / browser / session ...

    -- Token usage for the containing message turn
    input_tokens  INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    cache_read    INTEGER DEFAULT 0,

    -- Health signals
    stop_reason   TEXT,                     -- stop / end_turn / tool_use / max_tokens / error / timeout
    is_error      INTEGER DEFAULT 0,        -- 1 if toolResult.is_error = true

    -- Timestamp (ISO 8601)
    call_time     TEXT,

    -- Raw source line for debugging / replay
    raw_json      TEXT,

    created_at    TEXT    DEFAULT CURRENT_TIMESTAMP,

    -- Dedup: same session + tool + timestamp only inserted once
    UNIQUE(agent_id, session_id, tool_name, call_time)
);

CREATE INDEX IF NOT EXISTS idx_tool_logs_agent_time
    ON tool_call_logs(agent_id, call_time DESC);

CREATE INDEX IF NOT EXISTS idx_tool_logs_tool
    ON tool_call_logs(tool_name);

CREATE INDEX IF NOT EXISTS idx_tool_logs_stop
    ON tool_call_logs(agent_id, stop_reason);

CREATE INDEX IF NOT EXISTS idx_tool_logs_error
    ON tool_call_logs(agent_id, is_error)
    WHERE is_error = 1;

-- =============================================================================
-- Table 4: cron_run_logs
-- Purpose: Per-cron-execution event log (rolling 90-day retention)
-- Source: cron/runs/*.jsonl → action=finished, filtered by sessionKey/agentId
-- =============================================================================
CREATE TABLE IF NOT EXISTS cron_run_logs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id      TEXT    NOT NULL,
    job_id        TEXT,                     -- cron job identifier
    job_name      TEXT,

    -- Execution result
    status        TEXT,                     -- ok / error
    error_message TEXT,
    duration_ms   INTEGER DEFAULT 0,

    -- Token usage
    input_tokens  INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    total_tokens  INTEGER DEFAULT 0,

    -- Model info
    model         TEXT,
    provider      TEXT,

    -- Timestamp (ISO 8601)
    run_time      TEXT,

    raw_json      TEXT,

    created_at    TEXT    DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(agent_id, job_id, run_time, status)
);

CREATE INDEX IF NOT EXISTS idx_cron_logs_agent_time
    ON cron_run_logs(agent_id, run_time DESC);

CREATE INDEX IF NOT EXISTS idx_cron_logs_job
    ON cron_run_logs(job_id);

CREATE INDEX IF NOT EXISTS idx_cron_logs_status
    ON cron_run_logs(agent_id, status);

-- =============================================================================
-- Table 5: collection_state
-- Purpose: Tracks incremental collection progress (byte offsets per file)
-- =============================================================================
CREATE TABLE IF NOT EXISTS collection_state (
    agent_id            TEXT    PRIMARY KEY,
    session_offsets     TEXT    DEFAULT '{}',   -- JSON: {filepath: byte_offset}
    cron_offsets        TEXT    DEFAULT '{}',   -- JSON: {filepath: byte_offset}
    last_collected_at   TEXT    DEFAULT CURRENT_TIMESTAMP,
    last_snapshot_at    TEXT
);

-- =============================================================================
-- Table 6: achievements
-- Purpose: Tracks unlocked achievements per agent
-- =============================================================================
CREATE TABLE IF NOT EXISTS achievements (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id        TEXT    NOT NULL,
    achievement_type TEXT,                  -- unique achievement identifier
    title           TEXT,
    description     TEXT,
    unlocked_at     TEXT    DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(agent_id, achievement_type)
);

CREATE INDEX IF NOT EXISTS idx_achievements_agent
    ON achievements(agent_id);

-- =============================================================================
-- Maintenance: 90-day rolling cleanup (run weekly via cron or manually)
-- =============================================================================

-- DELETE FROM tool_call_logs WHERE call_time < datetime('now', '-90 days');
-- DELETE FROM cron_run_logs  WHERE run_time  < datetime('now', '-90 days');
-- VACUUM;

-- =============================================================================
-- Quick verification
-- =============================================================================
SELECT 'Tables created: ' || COUNT(*) AS result
FROM sqlite_master
WHERE type = 'table' AND name NOT LIKE 'sqlite_%';
