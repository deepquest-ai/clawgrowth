import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Tuple

from config import DB_PATH


def get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _add_column_if_missing(cur: sqlite3.Cursor, table: str, column: str, col_type: str) -> None:
    """Add a column to a table if it does not already exist (SQLite migration helper)."""
    try:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
    except sqlite3.OperationalError:
        pass  # Column already exists


def init_db() -> None:
    conn = get_conn()
    cur = conn.cursor()

    # Agent profiles table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS agent_profiles (
        agent_id TEXT PRIMARY KEY,
        display_name TEXT,
        level INTEGER DEFAULT 1,
        total_xp INTEGER DEFAULT 0,
        stage TEXT DEFAULT 'baby',
        efficiency_score REAL DEFAULT 0,
        output_score REAL DEFAULT 0,
        automation_score REAL DEFAULT 0,
        collaboration_score REAL DEFAULT 0,
        accumulation_score REAL DEFAULT 0,
        total_score REAL DEFAULT 0,
        energy REAL DEFAULT 100,
        health REAL DEFAULT 100,
        mood REAL DEFAULT 50,
        hunger REAL DEFAULT 100,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Daily snapshots table — full schema
    cur.execute("""
    CREATE TABLE IF NOT EXISTS daily_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        agent_id TEXT NOT NULL,
        date TEXT NOT NULL,
        conversations INTEGER DEFAULT 0,
        tool_calls INTEGER DEFAULT 0,
        unique_tools INTEGER DEFAULT 0,
        input_tokens INTEGER DEFAULT 0,
        output_tokens INTEGER DEFAULT 0,
        cache_read INTEGER DEFAULT 0,
        cron_runs INTEGER DEFAULT 0,
        cron_success INTEGER DEFAULT 0,
        cron_error_count INTEGER DEFAULT 0,
        avg_duration_ms REAL DEFAULT 0,
        collaborations INTEGER DEFAULT 0,
        collab_success INTEGER DEFAULT 0,
        collab_agents INTEGER DEFAULT 0,
        skills_count INTEGER DEFAULT 0,
        memories_count INTEGER DEFAULT 0,
        memories_words INTEGER DEFAULT 0,
        has_today_memory INTEGER DEFAULT 0,
        recent_memory_count INTEGER DEFAULT 0,
        learnings_count INTEGER DEFAULT 0,
        learnings_words INTEGER DEFAULT 0,
        errors_count INTEGER DEFAULT 0,
        feature_requests_count INTEGER DEFAULT 0,
        recent_feature_requests INTEGER DEFAULT 0,
        memory_sections INTEGER DEFAULT 0,
        memory_words INTEGER DEFAULT 0,
        tools_skills_installed INTEGER DEFAULT 0,
        tools_external_integrations INTEGER DEFAULT 0,
        tools_md_updated_days_ago INTEGER DEFAULT 0,
        total_tokens INTEGER DEFAULT 0,
        context_tokens INTEGER DEFAULT 0,
        context_usage REAL DEFAULT 0,
        compaction_count INTEGER DEFAULT 0,
        hours_since_active REAL DEFAULT 0,
        heartbeat_hours_ago REAL DEFAULT 0,
        heartbeat_daily_count INTEGER DEFAULT 0,
        last_task_hours_ago REAL DEFAULT 0,
        projects_active_count INTEGER DEFAULT 0,
        tasks_blocked INTEGER DEFAULT 0,
        tasks_overdue INTEGER DEFAULT 0,
        decisions_count INTEGER DEFAULT 0,
        recent_decisions_count INTEGER DEFAULT 0,
        reports_count INTEGER DEFAULT 0,
        recent_reports_count INTEGER DEFAULT 0,
        collections_count INTEGER DEFAULT 0,
        handoffs_count INTEGER DEFAULT 0,
        efficiency_score REAL DEFAULT 0,
        output_score REAL DEFAULT 0,
        automation_score REAL DEFAULT 0,
        collaboration_score REAL DEFAULT 0,
        accumulation_score REAL DEFAULT 0,
        total_score REAL DEFAULT 0,
        energy REAL DEFAULT 0,
        health REAL DEFAULT 0,
        mood REAL DEFAULT 0,
        hunger REAL DEFAULT 0,
        xp_gained INTEGER DEFAULT 0,
        tool_errors INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(agent_id, date)
    )
    """)

    # Migrate existing daily_snapshots — add new columns if missing
    new_snapshot_cols = [
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
    ]
    for col_name, col_def in new_snapshot_cols:
        _add_column_if_missing(cur, "daily_snapshots", col_name, col_def)

    # Tool call logs table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS tool_call_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        agent_id TEXT NOT NULL,
        session_id TEXT,
        tool_name TEXT,
        tool_category TEXT,
        input_tokens INTEGER DEFAULT 0,
        output_tokens INTEGER DEFAULT 0,
        cache_read INTEGER DEFAULT 0,
        stop_reason TEXT,
        is_error INTEGER DEFAULT 0,
        call_time TEXT,
        raw_json TEXT,
        UNIQUE(agent_id, session_id, tool_name, call_time)
    )
    """)

    # Migrate existing tool_call_logs
    _add_column_if_missing(cur, "tool_call_logs", "stop_reason", "TEXT")
    _add_column_if_missing(cur, "tool_call_logs", "is_error", "INTEGER DEFAULT 0")

    # Cron run logs table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS cron_run_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        agent_id TEXT NOT NULL,
        job_id TEXT,
        job_name TEXT,
        status TEXT,
        error_message TEXT,
        duration_ms INTEGER DEFAULT 0,
        input_tokens INTEGER DEFAULT 0,
        output_tokens INTEGER DEFAULT 0,
        total_tokens INTEGER DEFAULT 0,
        model TEXT,
        provider TEXT,
        run_time TEXT,
        raw_json TEXT,
        UNIQUE(agent_id, job_id, run_time, status)
    )
    """)

    # Collection state table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS collection_state (
        agent_id TEXT PRIMARY KEY,
        session_offsets TEXT DEFAULT '{}',
        cron_offsets TEXT DEFAULT '{}',
        last_collected_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Achievements table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS achievements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        agent_id TEXT NOT NULL,
        achievement_type TEXT,
        title TEXT,
        description TEXT,
        unlocked_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(agent_id, achievement_type)
    )
    """)

    # =========================================================================
    # Optimization indexes - speed up queries and incremental collection
    # =========================================================================
    
    # tool_call_logs indexes
    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_tool_logs_agent_time 
    ON tool_call_logs(agent_id, call_time)
    """)
    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_tool_logs_tool 
    ON tool_call_logs(tool_name)
    """)
    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_tool_logs_stop 
    ON tool_call_logs(agent_id, stop_reason)
    """)
    
    # cron_run_logs indexes
    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_cron_logs_agent_time 
    ON cron_run_logs(agent_id, run_time)
    """)
    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_cron_logs_job 
    ON cron_run_logs(job_id)
    """)
    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_cron_logs_status 
    ON cron_run_logs(agent_id, status)
    """)
    
    # daily_snapshots indexes
    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_snapshots_agent_date 
    ON daily_snapshots(agent_id, date)
    """)
    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_snapshots_date 
    ON daily_snapshots(date DESC)
    """)
    
    # achievements index
    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_achievements_agent 
    ON achievements(agent_id)
    """)

    conn.commit()
    conn.close()


def upsert_collection_state(
    agent_id: str, session_offsets: Dict[str, Any], cron_offsets: Dict[str, Any]
) -> None:
    conn = get_conn()
    conn.execute(
        """
        INSERT INTO collection_state (agent_id, session_offsets, cron_offsets, last_collected_at)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(agent_id) DO UPDATE SET
            session_offsets=excluded.session_offsets,
            cron_offsets=excluded.cron_offsets,
            last_collected_at=CURRENT_TIMESTAMP
        """,
        (agent_id, json.dumps(session_offsets), json.dumps(cron_offsets)),
    )
    conn.commit()
    conn.close()


def load_collection_state(agent_id: str) -> Tuple[Dict[str, int], Dict[str, int]]:
    conn = get_conn()
    row = conn.execute(
        "SELECT session_offsets, cron_offsets FROM collection_state WHERE agent_id = ?",
        (agent_id,),
    ).fetchone()
    conn.close()
    if not row:
        return {}, {}
    return json.loads(row['session_offsets'] or '{}'), json.loads(row['cron_offsets'] or '{}')
