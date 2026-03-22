#!/usr/bin/env python3
"""
init_db.py — ClawGrowth database initialization and migration script.

Usage:
    python scripts/init_db.py                  # init at default path
    python scripts/init_db.py --path /tmp/x.db # custom path
    python scripts/init_db.py --reset          # DROP all tables then re-create (destructive!)
    python scripts/init_db.py --info           # show table info only, no changes

Default DB path: $CLAWGROWTH_DB_PATH or ~/.openclaw/clawgrowth/clawgrowth.db
"""
import argparse
import os
import sqlite3
import sys
from pathlib import Path


def _get_default_db_path() -> Path:
    """Get default DB path from environment or fallback to ~/.openclaw/clawgrowth/clawgrowth.db"""
    env_path = os.environ.get('CLAWGROWTH_DB_PATH', '')
    if env_path:
        return Path(env_path)
    openclaw_root = os.environ.get('CLAWGROWTH_OPENCLAW_ROOT', '')
    if openclaw_root:
        return Path(openclaw_root) / 'clawgrowth' / 'clawgrowth.db'
    return Path.home() / '.openclaw' / 'clawgrowth' / 'clawgrowth.db'


DEFAULT_DB_PATH = _get_default_db_path()

# ---------------------------------------------------------------------------
# Schema definitions
# ---------------------------------------------------------------------------

DDL_STATEMENTS = [

    # ── agent_profiles ──────────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS agent_profiles (
        agent_id            TEXT    PRIMARY KEY,
        display_name        TEXT,
        level               INTEGER DEFAULT 1,
        total_xp            INTEGER DEFAULT 0,
        stage               TEXT    DEFAULT 'baby',
        efficiency_score    REAL    DEFAULT 0,
        output_score        REAL    DEFAULT 0,
        automation_score    REAL    DEFAULT 0,
        collaboration_score REAL    DEFAULT 0,
        accumulation_score  REAL    DEFAULT 0,
        total_score         REAL    DEFAULT 0,
        energy              REAL    DEFAULT 100,
        health              REAL    DEFAULT 100,
        mood                REAL    DEFAULT 50,
        hunger              REAL    DEFAULT 100,
        updated_at          TEXT    DEFAULT CURRENT_TIMESTAMP
    )
    """,

    # ── daily_snapshots ─────────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS daily_snapshots (
        id                          INTEGER PRIMARY KEY AUTOINCREMENT,
        agent_id                    TEXT    NOT NULL,
        date                        TEXT    NOT NULL,
        conversations               INTEGER DEFAULT 0,
        tool_calls                  INTEGER DEFAULT 0,
        unique_tools                INTEGER DEFAULT 0,
        input_tokens                INTEGER DEFAULT 0,
        output_tokens               INTEGER DEFAULT 0,
        cache_read                  INTEGER DEFAULT 0,
        tool_errors                 INTEGER DEFAULT 0,
        cron_runs                   INTEGER DEFAULT 0,
        cron_success                INTEGER DEFAULT 0,
        cron_error_count            INTEGER DEFAULT 0,
        avg_duration_ms             REAL    DEFAULT 0,
        collaborations              INTEGER DEFAULT 0,
        collab_success              INTEGER DEFAULT 0,
        collab_agents               INTEGER DEFAULT 0,
        skills_count                INTEGER DEFAULT 0,
        memories_count              INTEGER DEFAULT 0,
        memories_words              INTEGER DEFAULT 0,
        has_today_memory             INTEGER DEFAULT 0,
        recent_memory_count          INTEGER DEFAULT 0,
        learnings_count             INTEGER DEFAULT 0,
        learnings_words             INTEGER DEFAULT 0,
        errors_count                INTEGER DEFAULT 0,
        feature_requests_count      INTEGER DEFAULT 0,
        recent_feature_requests     INTEGER DEFAULT 0,
        memory_sections             INTEGER DEFAULT 0,
        memory_words                INTEGER DEFAULT 0,
        tools_skills_installed      INTEGER DEFAULT 0,
        tools_external_integrations INTEGER DEFAULT 0,
        tools_md_updated_days_ago   INTEGER DEFAULT 0,
        total_tokens                INTEGER DEFAULT 0,
        context_tokens              INTEGER DEFAULT 0,
        context_usage               REAL    DEFAULT 0,
        compaction_count            INTEGER DEFAULT 0,
        hours_since_active          REAL    DEFAULT 0,
        heartbeat_hours_ago         REAL    DEFAULT 0,
        heartbeat_daily_count       INTEGER DEFAULT 0,
        last_task_hours_ago         REAL    DEFAULT 0,
        projects_active_count       INTEGER DEFAULT 0,
        tasks_blocked               INTEGER DEFAULT 0,
        tasks_overdue               INTEGER DEFAULT 0,
        decisions_count             INTEGER DEFAULT 0,
        recent_decisions_count      INTEGER DEFAULT 0,
        reports_count               INTEGER DEFAULT 0,
        recent_reports_count        INTEGER DEFAULT 0,
        collections_count           INTEGER DEFAULT 0,
        handoffs_count              INTEGER DEFAULT 0,
        efficiency_score            REAL    DEFAULT 0,
        output_score                REAL    DEFAULT 0,
        automation_score            REAL    DEFAULT 0,
        collaboration_score         REAL    DEFAULT 0,
        accumulation_score          REAL    DEFAULT 0,
        total_score                 REAL    DEFAULT 0,
        energy                      REAL    DEFAULT 0,
        health                      REAL    DEFAULT 0,
        mood                        REAL    DEFAULT 0,
        hunger                      REAL    DEFAULT 0,
        xp_gained                   INTEGER DEFAULT 0,
        created_at                  TEXT    DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(agent_id, date)
    )
    """,

    "CREATE INDEX IF NOT EXISTS idx_snapshots_agent_date ON daily_snapshots(agent_id, date DESC)",
    "CREATE INDEX IF NOT EXISTS idx_snapshots_date ON daily_snapshots(date DESC)",

    # ── tool_call_logs ───────────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS tool_call_logs (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        agent_id      TEXT    NOT NULL,
        session_id    TEXT,
        tool_name     TEXT,
        tool_category TEXT,
        input_tokens  INTEGER DEFAULT 0,
        output_tokens INTEGER DEFAULT 0,
        cache_read    INTEGER DEFAULT 0,
        stop_reason   TEXT,
        is_error      INTEGER DEFAULT 0,
        call_time     TEXT,
        raw_json      TEXT,
        created_at    TEXT    DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(agent_id, session_id, tool_name, call_time)
    )
    """,

    "CREATE INDEX IF NOT EXISTS idx_tool_logs_agent_time ON tool_call_logs(agent_id, call_time DESC)",
    "CREATE INDEX IF NOT EXISTS idx_tool_logs_tool ON tool_call_logs(tool_name)",
    "CREATE INDEX IF NOT EXISTS idx_tool_logs_stop ON tool_call_logs(agent_id, stop_reason)",

    # ── cron_run_logs ────────────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS cron_run_logs (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        agent_id      TEXT    NOT NULL,
        job_id        TEXT,
        job_name      TEXT,
        status        TEXT,
        error_message TEXT,
        duration_ms   INTEGER DEFAULT 0,
        input_tokens  INTEGER DEFAULT 0,
        output_tokens INTEGER DEFAULT 0,
        total_tokens  INTEGER DEFAULT 0,
        model         TEXT,
        provider      TEXT,
        run_time      TEXT,
        raw_json      TEXT,
        created_at    TEXT    DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(agent_id, job_id, run_time, status)
    )
    """,

    "CREATE INDEX IF NOT EXISTS idx_cron_logs_agent_time ON cron_run_logs(agent_id, run_time DESC)",
    "CREATE INDEX IF NOT EXISTS idx_cron_logs_job ON cron_run_logs(job_id)",
    "CREATE INDEX IF NOT EXISTS idx_cron_logs_status ON cron_run_logs(agent_id, status)",

    # ── collection_state ─────────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS collection_state (
        agent_id          TEXT    PRIMARY KEY,
        session_offsets   TEXT    DEFAULT '{}',
        cron_offsets      TEXT    DEFAULT '{}',
        last_collected_at TEXT    DEFAULT CURRENT_TIMESTAMP,
        last_snapshot_at  TEXT
    )
    """,

    # ── achievements ─────────────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS achievements (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        agent_id         TEXT    NOT NULL,
        achievement_type TEXT,
        title            TEXT,
        description      TEXT,
        unlocked_at      TEXT    DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(agent_id, achievement_type)
    )
    """,

    "CREATE INDEX IF NOT EXISTS idx_achievements_agent ON achievements(agent_id)",
]

# Columns to add to existing tables via ALTER TABLE (safe migration)
MIGRATION_COLUMNS = {
    "daily_snapshots": [
        ("cron_error_count",              "INTEGER DEFAULT 0"),
        ("memories_words",                "INTEGER DEFAULT 0"),
        ("has_today_memory",               "INTEGER DEFAULT 0"),
        ("recent_memory_count",            "INTEGER DEFAULT 0"),
        ("learnings_words",               "INTEGER DEFAULT 0"),
        ("errors_count",                  "INTEGER DEFAULT 0"),
        ("feature_requests_count",        "INTEGER DEFAULT 0"),
        ("recent_feature_requests",       "INTEGER DEFAULT 0"),
        ("memory_words",                  "INTEGER DEFAULT 0"),
        ("tools_skills_installed",        "INTEGER DEFAULT 0"),
        ("tools_external_integrations",   "INTEGER DEFAULT 0"),
        ("tools_md_updated_days_ago",     "INTEGER DEFAULT 0"),
        ("hours_since_active",            "REAL DEFAULT 0"),
        ("heartbeat_hours_ago",           "REAL DEFAULT 0"),
        ("heartbeat_daily_count",         "INTEGER DEFAULT 0"),
        ("last_task_hours_ago",           "REAL DEFAULT 0"),
        ("projects_active_count",         "INTEGER DEFAULT 0"),
        ("tasks_blocked",                 "INTEGER DEFAULT 0"),
        ("tasks_overdue",                 "INTEGER DEFAULT 0"),
        ("decisions_count",               "INTEGER DEFAULT 0"),
        ("recent_decisions_count",        "INTEGER DEFAULT 0"),
        ("reports_count",                 "INTEGER DEFAULT 0"),
        ("recent_reports_count",          "INTEGER DEFAULT 0"),
        ("collections_count",             "INTEGER DEFAULT 0"),
        ("handoffs_count",                "INTEGER DEFAULT 0"),
        ("energy",                        "REAL DEFAULT 0"),
        ("health",                        "REAL DEFAULT 0"),
        ("mood",                          "REAL DEFAULT 0"),
        ("hunger",                        "REAL DEFAULT 0"),
        ("tool_errors",                   "INTEGER DEFAULT 0"),
    ],
    "tool_call_logs": [
        ("stop_reason", "TEXT"),
        ("is_error",    "INTEGER DEFAULT 0"),
    ],
}

DROP_ORDER = [
    "achievements",
    "collection_state",
    "cron_run_logs",
    "tool_call_logs",
    "daily_snapshots",
    "agent_profiles",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _add_column_if_missing(cur: sqlite3.Cursor, table: str, col: str, col_def: str) -> bool:
    try:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_def}")
        return True
    except sqlite3.OperationalError:
        return False  # column already exists


def _table_info(conn: sqlite3.Connection) -> dict:
    cur = conn.cursor()
    tables = [r[0] for r in cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()]
    info = {}
    for t in tables:
        cols = cur.execute(f"PRAGMA table_info({t})").fetchall()
        count = cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        info[t] = {"columns": len(cols), "rows": count}
    return info


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

def do_init(db_path: Path) -> None:
    print(f"Initializing database: {db_path}")
    conn = _connect(db_path)
    cur = conn.cursor()

    for stmt in DDL_STATEMENTS:
        cur.execute(stmt)

    # Safe migrations for pre-existing databases
    migrated = 0
    for table, columns in MIGRATION_COLUMNS.items():
        for col, col_def in columns:
            if _add_column_if_missing(cur, table, col, col_def):
                print(f"  + migrated: {table}.{col}")
                migrated += 1

    conn.commit()
    conn.close()

    info = _table_info(_connect(db_path))
    print(f"\nDatabase ready ({len(info)} tables):")
    for table, meta in sorted(info.items()):
        print(f"  {table:<30} {meta['columns']:>3} columns   {meta['rows']:>6} rows")
    if migrated:
        print(f"\n  {migrated} column(s) migrated.")


def do_reset(db_path: Path) -> None:
    print(f"WARNING: dropping all tables in {db_path}")
    answer = input("Type 'yes' to confirm: ").strip().lower()
    if answer != 'yes':
        print("Aborted.")
        sys.exit(0)
    conn = _connect(db_path)
    for t in DROP_ORDER:
        conn.execute(f"DROP TABLE IF EXISTS {t}")
    conn.commit()
    conn.close()
    print("All tables dropped.")
    do_init(db_path)


def do_info(db_path: Path) -> None:
    if not db_path.exists():
        print(f"Database not found: {db_path}")
        return
    conn = _connect(db_path)
    info = _table_info(conn)
    conn.close()
    print(f"Database: {db_path}")
    print(f"Tables: {len(info)}\n")
    for table, meta in sorted(info.items()):
        print(f"  {table:<30} {meta['columns']:>3} columns   {meta['rows']:>6} rows")


def do_cleanup(db_path: Path) -> None:
    """Remove tool_call_logs and cron_run_logs older than 90 days."""
    if not db_path.exists():
        print(f"Database not found: {db_path}")
        return
    conn = _connect(db_path)
    r1 = conn.execute(
        "DELETE FROM tool_call_logs WHERE call_time < datetime('now', '-90 days')"
    ).rowcount
    r2 = conn.execute(
        "DELETE FROM cron_run_logs WHERE run_time < datetime('now', '-90 days')"
    ).rowcount
    conn.execute("VACUUM")
    conn.commit()
    conn.close()
    print(f"Cleanup complete: removed {r1} tool_call_logs, {r2} cron_run_logs. VACUUM done.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="ClawGrowth DB management")
    parser.add_argument("--path",    default=str(DEFAULT_DB_PATH), help="Database file path")
    parser.add_argument("--reset",   action="store_true", help="Drop all tables then re-create (destructive)")
    parser.add_argument("--info",    action="store_true", help="Show table info only")
    parser.add_argument("--cleanup", action="store_true", help="Remove data older than 90 days and VACUUM")
    args = parser.parse_args()

    db_path = Path(args.path)

    if args.info:
        do_info(db_path)
    elif args.reset:
        do_reset(db_path)
    elif args.cleanup:
        do_cleanup(db_path)
    else:
        do_init(db_path)


if __name__ == "__main__":
    main()
