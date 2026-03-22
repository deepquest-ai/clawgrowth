"""
service.py — Core business logic for ClawGrowth API.

Assembles full AgentDetail and AgentsOverview responses by:
  1. Parsing session JSONL files
  2. Parsing cron run logs (per-agent filtered)
  3. Scanning the agent workspace
  4. Scanning the shared workspace
  5. Computing scores, status, XP
  6. Persisting to SQLite
  7. Returning rich response dicts
"""
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from config import OPENCLAW_ROOT, AGENTS_DIR, CRON_RUNS_DIR
from collectors.cron_parser import get_cron_jobs_config, parse_cron_logs
from collectors.session_parser import collect_session_logs, parse_sessions_index
from collectors.workspace_scanner import (
    build_collab_graph,
    scan_collaboration,
    scan_shared_workspace,
    scan_workspace,
)
from calculators.scores import (
    calc_accumulation_score,
    calc_automation_score,
    calc_collaboration_score,
    calc_efficiency_score,
    calc_output_score,
    calc_total_score,
    get_claw_color_info,
)
from calculators.status import calc_status
from calculators.xp import calc_daily_xp, calc_level
from database import get_conn, init_db


# ---------------------------------------------------------------------------
# Date / timestamp utilities
# ---------------------------------------------------------------------------

def _today() -> str:
    return datetime.now().strftime('%Y-%m-%d')


def _iso_date(value: Any) -> str:
    """Extract YYYY-MM-DD from any timestamp value."""
    if value is None:
        return _today()
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value / 1000, tz=timezone.utc).astimezone().strftime('%Y-%m-%d')
        except Exception:
            return _today()
    text = str(value)
    try:
        return datetime.fromisoformat(text.replace('Z', '+00:00')).astimezone().strftime('%Y-%m-%d')
    except Exception:
        return _today()


def _to_iso(value: Any) -> Optional[str]:
    """Convert any timestamp value to ISO string, or None."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value / 1000, tz=timezone.utc).isoformat()
        except Exception:
            return None
    text = str(value)
    try:
        return datetime.fromisoformat(text.replace('Z', '+00:00')).isoformat()
    except Exception:
        return None


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat()


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def _get_total_xp(agent_id: str, conn) -> int:
    """Return the stored cumulative XP for an agent."""
    row = conn.execute(
        'SELECT total_xp FROM agent_profiles WHERE agent_id = ?', (agent_id,)
    ).fetchone()
    return int(row['total_xp']) if row else 0


def _load_prev_status(agent_id: str, conn) -> Optional[Dict[str, Any]]:
    """Return the most recently stored status values for EMA smoothing."""
    row = conn.execute(
        'SELECT energy, health, mood, hunger FROM agent_profiles WHERE agent_id = ?',
        (agent_id,),
    ).fetchone()
    if not row:
        return None
    return {
        'energy': float(row['energy'] or 0),
        'health': float(row['health'] or 0),
        'mood':   float(row['mood']   or 0),
        'hunger': float(row['hunger'] or 0),
    }


# ---------------------------------------------------------------------------
# Cron jobs config / overview helpers
# ---------------------------------------------------------------------------

def _get_cron_jobs_stats() -> Tuple[int, int, Dict[str, int]]:
    """Return (total_jobs, enabled_jobs, jobs_by_agent) from cron/jobs.json."""
    jobs_file = OPENCLAW_ROOT / 'cron' / 'jobs.json'
    if not jobs_file.exists():
        return 0, 0, {}
    try:
        data = json.loads(jobs_file.read_text(encoding='utf-8'))
    except Exception:
        return 0, 0, {}
    jobs = data.get('jobs', [])
    total = len(jobs)
    enabled = sum(1 for j in jobs if j.get('enabled'))
    by_agent: Dict[str, int] = {}
    for j in jobs:
        aid = j.get('agentId', 'unknown')
        by_agent[aid] = by_agent.get(aid, 0) + 1
    return total, enabled, by_agent


def _build_cron_summary(agent_id: str, today_crons: List[Dict]) -> Dict[str, Any]:
    """Build the cron section of AgentDetail from cron job config + today's runs."""
    config = get_cron_jobs_config(agent_id)
    success_today = sum(1 for x in today_crons if x.get('status') == 'ok')
    avg_duration_ms = 0.0
    if today_crons:
        avg_duration_ms = round(
            sum(x.get('duration_ms', 0) for x in today_crons) / len(today_crons), 2
        )

    recent_errors = [
        {
            'job_id':        x.get('job_id'),
            'error_message': x.get('error_message'),
            'run_time':      _to_iso(x.get('run_time')),
        }
        for x in today_crons
        if x.get('error_message')
    ][:10]

    return {
        'jobs_total':       config['jobs_total'],
        'jobs_enabled':     config['jobs_enabled'],
        'runs_today':       len(today_crons),
        'success_today':    success_today,
        'avg_duration_ms':  avg_duration_ms,
        'recent_errors':    recent_errors,
    }


# ---------------------------------------------------------------------------
# Tool stats helpers
# ---------------------------------------------------------------------------

def _build_tools_section(today_tools: List[Dict]) -> Dict[str, Any]:
    """Build the tools section of AgentDetail from today's tool call events."""
    category_counter: Counter = Counter(x.get('tool_category', 'other') for x in today_tools)
    name_counter: Counter = Counter(x.get('tool_name', 'unknown') for x in today_tools)
    stop_reason_counter: Counter = Counter(
        x.get('stop_reason', '') for x in today_tools if x.get('stop_reason')
    )
    return {
        'by_category':   dict(category_counter),
        'top_tools':     name_counter.most_common(10),
        'stop_reasons':  dict(stop_reason_counter),
    }


# ---------------------------------------------------------------------------
# Derived metrics
# ---------------------------------------------------------------------------

def _build_derived(data: Dict[str, Any]) -> Dict[str, Any]:
    """Compute derived metrics dict for AgentDetail."""
    input_tokens  = int(data.get('input_tokens', 0) or 0)
    output_tokens = int(data.get('output_tokens', 0) or 0)
    cache_read    = int(data.get('cache_read', 0) or 0)
    cron_runs     = int(data.get('cron_runs', 0) or 0)
    cron_success  = int(data.get('cron_success', 0) or 0)
    tool_calls    = int(data.get('tool_calls', 0) or 0)
    tool_errors   = int(data.get('tool_errors', 0) or 0)
    collab_agents = int(data.get('collab_agents', 0) or 0)
    unique_tools  = int(data.get('unique_tools', 0) or 0)
    memories_count = int(data.get('memories_count', 0) or 0)
    context_tokens = int(data.get('context_tokens', 200000) or 200000)
    total_tokens   = int(data.get('total_tokens', 0) or 0)

    token_efficiency = round(output_tokens / input_tokens, 4) if input_tokens else 0.0
    # cache_hit_rate = cache_read / (input_tokens + cache_read)
    # cache_read is the portion saved from input, total input needed = input_tokens + cache_read
    total_input = input_tokens + cache_read
    cache_hit_rate = round(cache_read / total_input, 4) if total_input else 0.0
    cron_success_rate = round(cron_success / cron_runs * 100, 1) if cron_runs else 0.0
    tool_error_rate = round(tool_errors / max(tool_calls, 1) * 100, 2)
    tool_diversity = round(unique_tools / max(tool_calls, 1), 2)
    memory_rate = round(memories_count / 7, 2)  # memories per day this week proxy
    context_usage = round(total_tokens / max(context_tokens, 1) * 100, 2)

    return {
        'token_efficiency':  token_efficiency,
        'cache_hit_rate':    cache_hit_rate,
        'cron_success_rate': cron_success_rate,
        'tool_error_rate':   tool_error_rate,
        'tool_diversity':    tool_diversity,
        'memory_rate':        memory_rate,
        'context_usage':     context_usage,
    }


# ---------------------------------------------------------------------------
# Persist snapshot to DB
# ---------------------------------------------------------------------------

def _persist_snapshot(
    agent_id: str,
    data: Dict[str, Any],
    scores: Dict[str, Any],
    status: Dict[str, Any],
    xp: Dict[str, Any],
    total_xp: int,
    conn,
) -> None:
    """Write agent profile and daily snapshot to the database."""

    def _sv(key: str) -> float:
        """Get score value from scores dict (handles both float and dict)."""
        v = scores.get(key)
        if isinstance(v, dict):
            return float(v.get('value', 0))
        return float(v or 0)

    def _stv(key: str) -> float:
        """Get status value from status dict."""
        v = status.get(key)
        if isinstance(v, dict):
            return float(v.get('value', 0))
        return float(v or 0)

    level, stage, _ = calc_level(total_xp)

    # Upsert agent profile
    conn.execute(
        """
        INSERT INTO agent_profiles
        (agent_id, display_name, level, total_xp, stage,
         efficiency_score, output_score, automation_score,
         collaboration_score, accumulation_score, total_score,
         energy, health, mood, hunger, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
        ON CONFLICT(agent_id) DO UPDATE SET
            display_name=excluded.display_name,
            level=excluded.level,
            total_xp=excluded.total_xp,
            stage=excluded.stage,
            efficiency_score=excluded.efficiency_score,
            output_score=excluded.output_score,
            automation_score=excluded.automation_score,
            collaboration_score=excluded.collaboration_score,
            accumulation_score=excluded.accumulation_score,
            total_score=excluded.total_score,
            energy=excluded.energy,
            health=excluded.health,
            mood=excluded.mood,
            hunger=excluded.hunger,
            updated_at=CURRENT_TIMESTAMP
        """,
        (
            agent_id, agent_id, level, total_xp, stage,
            _sv('efficiency'), _sv('output'), _sv('automation'),
            _sv('collaboration'), _sv('accumulation'), _sv('total'),
            _stv('energy'), _stv('health'), _stv('mood'), _stv('hunger'),
        ),
    )

    today = _today()
    # Upsert daily snapshot
    conn.execute(
        """
        INSERT INTO daily_snapshots
        (agent_id, date, conversations, tool_calls, unique_tools,
         input_tokens, output_tokens, cache_read,
         cron_runs, cron_success, cron_error_count, avg_duration_ms,
         collaborations, collab_success, collab_agents,
         skills_count, memories_count, memories_words,
         has_today_memory, recent_memory_count,
         learnings_count, learnings_words, errors_count,
         feature_requests_count, recent_feature_requests,
         memory_sections, memory_words,
         tools_skills_installed, tools_external_integrations, tools_md_updated_days_ago,
         total_tokens, context_tokens, context_usage, compaction_count,
         hours_since_active,
         efficiency_score, output_score, automation_score,
         collaboration_score, accumulation_score, total_score,
         energy, health, mood, hunger,
         xp_gained, tool_errors)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(agent_id, date) DO UPDATE SET
            conversations=excluded.conversations,
            tool_calls=excluded.tool_calls,
            unique_tools=excluded.unique_tools,
            input_tokens=excluded.input_tokens,
            output_tokens=excluded.output_tokens,
            cache_read=excluded.cache_read,
            cron_runs=excluded.cron_runs,
            cron_success=excluded.cron_success,
            cron_error_count=excluded.cron_error_count,
            avg_duration_ms=excluded.avg_duration_ms,
            collaborations=excluded.collaborations,
            collab_success=excluded.collab_success,
            collab_agents=excluded.collab_agents,
            skills_count=excluded.skills_count,
            memories_count=excluded.memories_count,
            memories_words=excluded.memories_words,
            has_today_memory=excluded.has_today_memory,
            recent_memory_count=excluded.recent_memory_count,
            learnings_count=excluded.learnings_count,
            learnings_words=excluded.learnings_words,
            errors_count=excluded.errors_count,
            feature_requests_count=excluded.feature_requests_count,
            recent_feature_requests=excluded.recent_feature_requests,
            memory_sections=excluded.memory_sections,
            memory_words=excluded.memory_words,
            tools_skills_installed=excluded.tools_skills_installed,
            tools_external_integrations=excluded.tools_external_integrations,
            tools_md_updated_days_ago=excluded.tools_md_updated_days_ago,
            total_tokens=excluded.total_tokens,
            context_tokens=excluded.context_tokens,
            context_usage=excluded.context_usage,
            compaction_count=excluded.compaction_count,
            hours_since_active=excluded.hours_since_active,
            efficiency_score=excluded.efficiency_score,
            output_score=excluded.output_score,
            automation_score=excluded.automation_score,
            collaboration_score=excluded.collaboration_score,
            accumulation_score=excluded.accumulation_score,
            total_score=excluded.total_score,
            energy=excluded.energy,
            health=excluded.health,
            mood=excluded.mood,
            hunger=excluded.hunger,
            xp_gained=excluded.xp_gained,
            tool_errors=excluded.tool_errors
        """,
        (
            agent_id, today,
            data.get('conversations', 0), data.get('tool_calls', 0), data.get('unique_tools', 0),
            data.get('input_tokens', 0), data.get('output_tokens', 0), data.get('cache_read', 0),
            data.get('cron_runs', 0), data.get('cron_success', 0), data.get('cron_error_count', 0),
            data.get('avg_duration_ms', 0),
            data.get('collaborations', 0), data.get('collab_success', 0), data.get('collab_agents', 0),
            data.get('skills_count', 0), data.get('memories_count', 0), data.get('memories_words', 0),
            1 if data.get('has_today_memory') else 0,
            data.get('recent_memory_count', 0),
            data.get('learnings_count', 0), data.get('learnings_words', 0), data.get('errors_count', 0),
            data.get('feature_requests_count', 0), data.get('recent_feature_requests', 0),
            data.get('memory_sections', 0), data.get('memory_words', 0),
            data.get('tools_skills_installed', 0), data.get('tools_external_integrations', 0),
            data.get('tools_md_updated_days_ago', 0),
            data.get('total_tokens', 0), data.get('context_tokens', 200000),
            data.get('context_usage', 0), data.get('compaction_count', 0),
            data.get('hours_since_active', 0),
            _sv('efficiency'), _sv('output'), _sv('automation'),
            _sv('collaboration'), _sv('accumulation'), _sv('total'),
            _stv('energy'), _stv('health'), _stv('mood'), _stv('hunger'),
            xp.get('total', 0), data.get('tool_errors', 0),
        ),
    )

    # Note: Log persistence moved to _persist_logs_incremental()
    # API calls no longer trigger log writes, handled by background tasks

    conn.execute(
        "INSERT OR IGNORE INTO achievements (agent_id, achievement_type, title, description) "
        "VALUES (?, 'first_collection', 'First Collection', 'Collected native OpenClaw data successfully')",
        (agent_id,),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# build_agent_detail — main response builder
# ---------------------------------------------------------------------------

def build_agent_detail(agent_id: str) -> Dict[str, Any]:
    """
    Build the full AgentDetail response for one agent.

    Collects all data, computes scores / status / XP, persists to DB,
    and returns the complete response dict matching the API contract.
    """
    init_db()
    conn = get_conn()
    today = _today()

    # 1. Parse sessions (latest session stats)
    session_data = parse_sessions_index(agent_id)

    # 2. Collect tool call events (all time — DB deduplication handles history)
    all_tool_logs = collect_session_logs(agent_id)
    today_tools = [x for x in all_tool_logs if _iso_date(x.get('call_time')) == today]

    # 3. Collect cron runs (agent-filtered)
    all_cron_logs = parse_cron_logs(agent_id)
    today_crons = [x for x in all_cron_logs if _iso_date(x.get('run_time')) == today]

    # 4. Scan workspace
    workspace = scan_workspace(agent_id)

    # 5. Scan collaboration (per-agent filtered)
    collab = scan_collaboration(agent_id)

    # 6. Derived today metrics
    tool_name_counter: Counter = Counter(x.get('tool_name') for x in today_tools)
    session_ids = {x.get('session_id') for x in today_tools if x.get('session_id')}
    conversations = len(session_ids)
    cron_success = sum(1 for x in today_crons if x.get('status') == 'ok')
    cron_error_count = sum(1 for x in today_crons if x.get('error_message'))
    avg_duration_ms = 0.0
    if today_crons:
        avg_duration_ms = round(
            sum(x.get('duration_ms', 0) for x in today_crons) / len(today_crons), 2
        )
    tool_errors = sum(1 for x in today_tools if x.get('is_error'))
    unique_tools = len(tool_name_counter)

    # 7. Assemble combined data dict for calculators
    data: Dict[str, Any] = {
        'agent_id':          agent_id,
        'date':              today,
        'conversations':     conversations,
        'tool_calls':        len(today_tools),
        'unique_tools':      unique_tools,
        'input_tokens':      sum(x.get('input_tokens', 0) for x in today_tools),
        'output_tokens':     sum(x.get('output_tokens', 0) for x in today_tools),
        'cache_read':        sum(x.get('cache_read', 0) for x in today_tools),
        'cron_runs':         len(today_crons),
        'cron_success':      cron_success,
        'cron_error_count':  cron_error_count,
        'avg_duration_ms':   avg_duration_ms,
        'tool_errors':       tool_errors,
        # Collaboration
        **collab,
        # Workspace
        **workspace,
        # Session
        'total_tokens':      session_data.get('total_tokens', 0),
        'context_tokens':    session_data.get('context_tokens', 200000),
        'context_usage':     session_data.get('context_usage', 0),
        'compaction_count':  session_data.get('compaction_count', 0),
        'hours_since_active': session_data.get('hours_since_active', 24.0),
        # Raw logs stashed for persistence
        '_tool_logs':        all_tool_logs,
        '_cron_logs':        all_cron_logs,
    }

    # 8. Calculate scores (each returns dict with value + breakdown)
    eff_score   = calc_efficiency_score(data)
    out_score   = calc_output_score(data)
    auto_score  = calc_automation_score(data)
    collab_score_d = calc_collaboration_score(data)
    accum_score = calc_accumulation_score(data)

    # Pass pre-computed values to total to avoid double-computation
    total_data = dict(data)
    total_data['efficiency_score_val']    = eff_score['value']
    total_data['output_score_val']        = out_score['value']
    total_data['automation_score_val']    = auto_score['value']
    total_data['collaboration_score_val'] = collab_score_d['value']
    total_data['accumulation_score_val']  = accum_score['value']
    total_score = calc_total_score(total_data)

    scores: Dict[str, Any] = {
        'efficiency':    eff_score,
        'output':        out_score,
        'automation':    auto_score,
        'collaboration': collab_score_d,
        'accumulation':  accum_score,
        'total':         total_score,
    }

    # 9. Calculate status with EMA smoothing
    prev_status = _load_prev_status(agent_id, conn)
    status = calc_status(data, db=conn, prev_status=prev_status)

    # 10. Calculate XP
    xp = calc_daily_xp(data)

    # 11. Determine color from total score
    color_info = get_claw_color_info(total_score['value'])

    # 12. Compute cumulative XP (existing + today's gain)
    stored_xp = _get_total_xp(agent_id, conn)
    total_xp = max(stored_xp, xp['total'])  # grow-only: never decrease stored XP

    level, stage, next_level_xp = calc_level(total_xp)

    # 13. Persist to DB
    _persist_snapshot(agent_id, data, scores, status, xp, total_xp, conn)
    conn.close()

    # 14. Build today section
    today_section = {
        'tool_calls':       len(today_tools),
        'unique_tools':     unique_tools,
        'input_tokens':     data['input_tokens'],
        'output_tokens':    data['output_tokens'],
        'cache_read':       data['cache_read'],
        'cron_runs':        len(today_crons),
        'cron_success':     cron_success,
        'cron_error_count': cron_error_count,
        'collaborations':   collab.get('collaborations', 0),
        'collab_success':   collab.get('collab_success', 0),
        'conversations':    conversations,
        'tool_errors':      tool_errors,
    }

    # 15. Build session section
    session_section = {
        'total_tokens':     session_data.get('total_tokens', 0),
        'context_tokens':   session_data.get('context_tokens', 200000),
        'compaction_count': session_data.get('compaction_count', 0),
        'updated_at':       session_data.get('updated_at'),
        'hours_since_active': session_data.get('hours_since_active', 24.0),
    }

    # 16. Build cron section
    cron_section = _build_cron_summary(agent_id, today_crons)

    # 17. Build tools section
    tools_section = _build_tools_section(today_tools)

    # 18. Workspace section (strip internal helpers)
    workspace_section = {k: v for k, v in workspace.items() if not k.startswith('_')}

    # 19. Derived metrics
    derived = _build_derived(data)

    return {
        'agent_id':      agent_id,
        'level':         level,
        'stage':         stage,
        'total_xp':      total_xp,
        'next_level_xp': next_level_xp,
        'color':         color_info['hex'],
        'color_name':    color_info['name'],
        'scores':        scores,
        'status':        status,
        'today':         today_section,
        'derived':       derived,
        'session':       session_section,
        'workspace':     workspace_section,
        'cron':          cron_section,
        'tools':         tools_section,
        'xp_breakdown':  xp,
        'updated_at':    _now_iso(),
    }


# ---------------------------------------------------------------------------
# build_agents_overview
# ---------------------------------------------------------------------------

def _build_agent_summary_fast(agent_id: str) -> Dict[str, Any]:
    """
    Build a lightweight agent summary without the full detail scan.
    Uses cached data from daily_snapshots and DB queries only - no filesystem scan.
    """
    conn = get_conn()
    
    # Get latest snapshot from DB (much faster than full scan)
    row = conn.execute("""
        SELECT total_score, xp_gained, tool_calls, cron_runs, skills_count
        FROM daily_snapshots
        WHERE agent_id = ?
        ORDER BY date DESC
        LIMIT 1
    """, (agent_id,)).fetchone()
    
    # Get total XP
    total_xp = _get_total_xp(agent_id, conn)
    level, stage, _ = calc_level(total_xp)
    total_score = row['total_score'] if row else 50.0
    color_info = get_claw_color_info(total_score)
    
    # Use cached skills_count from snapshot, or 0
    skills_count = int(row['skills_count'] or 0) if row else 0
    
    # Get today's cron stats from cron_run_logs
    cron_row = conn.execute("""
        SELECT COUNT(*) as runs,
               SUM(CASE WHEN status='ok' THEN 1 ELSE 0 END) as success
        FROM cron_run_logs
        WHERE agent_id = ? AND date(run_time) = date('now')
    """, (agent_id,)).fetchone()
    cron_runs = int(cron_row['runs'] or 0) if cron_row else 0
    cron_success = int(cron_row['success'] or 0) if cron_row else 0
    
    # Get today's tool calls
    tool_row = conn.execute("""
        SELECT COUNT(*) as cnt
        FROM tool_call_logs
        WHERE agent_id = ? AND date(call_time) = date('now')
    """, (agent_id,)).fetchone()
    tool_calls = int(tool_row['cnt'] or 0) if tool_row else 0
    
    # Get collaborations
    collab_row = conn.execute("""
        SELECT COUNT(*) as cnt
        FROM tool_call_logs
        WHERE agent_id = ? AND date(call_time) = date('now')
              AND tool_name IN ('sessions_spawn', 'sessions_send', 'subagents')
    """, (agent_id,)).fetchone()
    collaborations = int(collab_row['cnt'] or 0) if collab_row else 0
    
    conn.close()
    
    return {
        'agent_id':     agent_id,
        'level':        level,
        'stage':        stage,
        'total_xp':     total_xp,
        'color':        color_info['hex'],
        'tool_calls':   tool_calls,
        'cron_runs':    cron_runs,
        'cron_success': cron_success,
        'success_rate': round(cron_success / cron_runs * 100, 1) if cron_runs else 0.0,
        'collaborations': collaborations,
        'skills_count':   skills_count,
        'total_score':    total_score,
        'energy':         75.0,  # Placeholder - full scan too slow
        'health':         75.0,  # Placeholder - full scan too slow
    }


def build_agents_overview() -> Dict[str, Any]:
    """Build the AgentsOverview response for all discovered agents."""
    init_db()
    conn = get_conn()
    
    agent_ids = (
        sorted(d.name for d in AGENTS_DIR.iterdir() if d.is_dir())
        if AGENTS_DIR.exists()
        else []
    )

    # Batch fetch all agent data from DB
    placeholders = ','.join('?' for _ in agent_ids)
    
    # Get profiles
    profiles = {}
    if agent_ids:
        rows = conn.execute(f"""
            SELECT agent_id, total_xp FROM agent_profiles
            WHERE agent_id IN ({placeholders})
        """, tuple(agent_ids)).fetchall()
        profiles = {r['agent_id']: r for r in rows}
    
    # Get latest snapshots
    snapshots = {}
    if agent_ids:
        rows = conn.execute(f"""
            SELECT agent_id, total_score, skills_count
            FROM daily_snapshots
            WHERE (agent_id, date) IN (
                SELECT agent_id, MAX(date) FROM daily_snapshots
                WHERE agent_id IN ({placeholders})
                GROUP BY agent_id
            )
        """, tuple(agent_ids)).fetchall()
        snapshots = {r['agent_id']: r for r in rows}
    
    # Get today's cron stats
    cron_stats = {}
    if agent_ids:
        rows = conn.execute(f"""
            SELECT agent_id,
                   COUNT(*) as runs,
                   SUM(CASE WHEN status='ok' THEN 1 ELSE 0 END) as success
            FROM cron_run_logs
            WHERE agent_id IN ({placeholders}) AND date(run_time) = date('now')
            GROUP BY agent_id
        """, tuple(agent_ids)).fetchall()
        cron_stats = {r['agent_id']: r for r in rows}
    
    # Get today's tool calls and collaborations
    tool_stats = {}
    if agent_ids:
        rows = conn.execute(f"""
            SELECT agent_id,
                   COUNT(*) as tool_calls,
                   SUM(CASE WHEN tool_name IN ('sessions_spawn', 'sessions_send', 'subagents') THEN 1 ELSE 0 END) as collabs
            FROM tool_call_logs
            WHERE agent_id IN ({placeholders}) AND date(call_time) = date('now')
            GROUP BY agent_id
        """, tuple(agent_ids)).fetchall()
        tool_stats = {r['agent_id']: r for r in rows}
    
    conn.close()

    # Build agent list
    agents: List[Dict[str, Any]] = []
    for aid in agent_ids:
        try:
            profile = profiles.get(aid)
            snapshot = snapshots.get(aid)
            cron = cron_stats.get(aid)
            tools = tool_stats.get(aid)
            
            # sqlite3.Row needs [] access, not .get()
            total_xp = int(profile['total_xp'] or 0) if profile else 0
            level, stage, _ = calc_level(total_xp)
            total_score = float(snapshot['total_score'] or 50.0) if snapshot else 50.0
            color_info = get_claw_color_info(total_score)
            
            cron_runs = int(cron['runs'] or 0) if cron else 0
            cron_success = int(cron['success'] or 0) if cron else 0
            tool_calls = int(tools['tool_calls'] or 0) if tools else 0
            collaborations = int(tools['collabs'] or 0) if tools else 0
            skills_count = int(snapshot['skills_count'] or 0) if snapshot else 0
            
            agents.append({
                'agent_id':     aid,
                'level':        level,
                'stage':        stage,
                'total_xp':     total_xp,
                'color':        color_info['hex'],
                'tool_calls':   tool_calls,
                'cron_runs':    cron_runs,
                'cron_success': cron_success,
                'success_rate': round(cron_success / cron_runs * 100, 1) if cron_runs else 0.0,
                'collaborations': collaborations,
                'skills_count':   skills_count,
                'total_score':    total_score,
                'energy':         75.0,
                'health':         75.0,
            })
        except Exception:
            agents.append({
                'agent_id': aid, 'level': 1, 'stage': 'baby', 'total_xp': 0,
                'color': '#9B5DE5', 'tool_calls': 0, 'cron_runs': 0,
                'cron_success': 0, 'success_rate': 0.0, 'collaborations': 0,
                'skills_count': 0, 'total_score': 0.0, 'energy': 0.0, 'health': 0.0,
            })

    agents_sorted = sorted(agents, key=lambda x: x['total_score'], reverse=True)

    cron_jobs_total, cron_jobs_enabled, _ = _get_cron_jobs_stats()
    collab_graph = build_collab_graph()
    shared = scan_shared_workspace()

    return {
        'total':              len(agents),
        'active':             sum(1 for a in agents if a['tool_calls'] > 0 or a['cron_runs'] > 0),
        'agents':             agents_sorted,
        'cron_jobs_total':    cron_jobs_total,
        'cron_jobs_enabled':  cron_jobs_enabled,
        'collab_graph':       collab_graph,
        'shared':             shared,
    }


# ---------------------------------------------------------------------------
# build_history
# ---------------------------------------------------------------------------

def build_history(agent_id: str, days: int = 7) -> Dict[str, Any]:
    """Return historical daily snapshots for an agent."""
    init_db()
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT date, total_score, efficiency_score, output_score,
               automation_score, collaboration_score, accumulation_score,
               xp_gained, tool_calls, cron_runs
        FROM daily_snapshots
        WHERE agent_id = ?
        ORDER BY date DESC
        LIMIT ?
        """,
        (agent_id, days),
    ).fetchall()
    conn.close()

    items = [
        {
            'date':               row['date'],
            'total_score':        row['total_score'],
            'efficiency_score':   row['efficiency_score'],
            'output_score':       row['output_score'],
            'automation_score':   row['automation_score'],
            'collaboration_score': row['collaboration_score'],
            'accumulation_score': row['accumulation_score'],
            'xp_gained':          row['xp_gained'],
            'tool_calls':         row['tool_calls'],
            'cron_runs':          row['cron_runs'],
        }
        for row in rows
    ]
    items = items[::-1]  # chronological order

    return {'agent_id': agent_id, 'days': days, 'items': items}


# ---------------------------------------------------------------------------
# run_collection — trigger manual collection
# ---------------------------------------------------------------------------

def run_collection(agent_id: str) -> Dict[str, Any]:
    """Trigger a data collection cycle and return summary stats."""
    try:
        detail = build_agent_detail(agent_id)
        return {
            'ok': True,
            'agent_id':   agent_id,
            'date':       _today(),
            'tool_calls': detail['today']['tool_calls'],
            'cron_runs':  detail['today']['cron_runs'],
            'total_score': detail['scores']['total']['value'],
            'total_xp':   detail['total_xp'],
        }
    except Exception as exc:
        return {'ok': False, 'agent_id': agent_id, 'error': str(exc)}


# ---------------------------------------------------------------------------
# Incremental collection and data cleanup (optimization implementation)
# ---------------------------------------------------------------------------

def _get_last_collected_time(agent_id: str, table: str, conn) -> str:
    """Get the latest record time for this agent in the specified table."""
    time_col = 'call_time' if table == 'tool_call_logs' else 'run_time'
    row = conn.execute(f"""
        SELECT MAX({time_col}) FROM {table} WHERE agent_id = ?
    """, (agent_id,)).fetchone()
    return row[0] if row and row[0] else '1970-01-01T00:00:00'


def _persist_tool_logs_incremental(agent_id: str, tool_logs: List[Dict], conn) -> int:
    """Incrementally insert tool_call_logs: only insert logs newer than the latest."""
    if not tool_logs:
        return 0
    
    last_time = _get_last_collected_time(agent_id, 'tool_call_logs', conn)
    new_logs = [x for x in tool_logs if (x.get('call_time') or '') > last_time]
    
    if not new_logs:
        return 0
    
    # Batch insert
    data = [
        (
            agent_id,
            x.get('session_id'), x.get('tool_name'), x.get('tool_category'),
            x.get('input_tokens', 0), x.get('output_tokens', 0), x.get('cache_read', 0),
            x.get('stop_reason'), x.get('is_error', 0),
            x.get('call_time'), x.get('raw_json'),
        )
        for x in new_logs
    ]
    
    conn.executemany("""
        INSERT OR IGNORE INTO tool_call_logs
        (agent_id, session_id, tool_name, tool_category,
         input_tokens, output_tokens, cache_read,
         stop_reason, is_error, call_time, raw_json)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
    """, data)
    
    return len(new_logs)


def _persist_cron_logs_incremental(agent_id: str, cron_logs: List[Dict], conn) -> int:
    """Incrementally insert cron_run_logs: only insert logs newer than the latest."""
    if not cron_logs:
        return 0
    
    last_time = _get_last_collected_time(agent_id, 'cron_run_logs', conn)
    new_logs = [x for x in cron_logs if (x.get('run_time') or '') > last_time]
    
    if not new_logs:
        return 0
    
    # Batch insert
    data = [
        (
            agent_id,
            x.get('job_id'), x.get('job_name'), x.get('status'), x.get('error_message'),
            x.get('duration_ms', 0), x.get('input_tokens', 0),
            x.get('output_tokens', 0), x.get('total_tokens', 0),
            x.get('model'), x.get('provider'),
            x.get('run_time'), x.get('raw_json'),
        )
        for x in new_logs
    ]
    
    conn.executemany("""
        INSERT OR IGNORE INTO cron_run_logs
        (agent_id, job_id, job_name, status, error_message,
         duration_ms, input_tokens, output_tokens, total_tokens,
         model, provider, run_time, raw_json)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, data)
    
    return len(new_logs)


def run_collection_with_persist(agent_id: str) -> Dict[str, Any]:
    """
    Background task entry point: collect data + incrementally persist logs.
    
    Unlike build_agent_detail(), this function writes logs to the database.
    Should be called by background cron tasks, not API requests.
    """
    init_db()
    conn = get_conn()
    
    try:
        # 1. Collect logs
        all_tool_logs = collect_session_logs(agent_id)
        all_cron_logs = parse_cron_logs(agent_id)
        
        # 2. Incremental persistence
        tool_inserted = _persist_tool_logs_incremental(agent_id, all_tool_logs, conn)
        cron_inserted = _persist_cron_logs_incremental(agent_id, all_cron_logs, conn)
        
        conn.commit()
        
        # 3. Build details (no longer writes logs, only profile and snapshot)
        detail = build_agent_detail(agent_id)
        
        return {
            'ok': True,
            'agent_id': agent_id,
            'date': _today(),
            'tool_logs_inserted': tool_inserted,
            'cron_logs_inserted': cron_inserted,
            'total_score': detail['scores']['total']['value'],
            'total_xp': detail['total_xp'],
        }
    except Exception as exc:
        return {'ok': False, 'agent_id': agent_id, 'error': str(exc)}
    finally:
        conn.close()


def cleanup_old_data(tool_days: int = 7, cron_days: int = 30) -> Dict[str, Any]:
    """
    Clean up expired data.
    
    Args:
        tool_days: Days to keep tool_call_logs, default 7 days
        cron_days: Days to keep cron_run_logs, default 30 days
    
    Returns:
        Statistics of deleted rows
    """
    init_db()
    conn = get_conn()
    
    try:
        # Clean tool_call_logs
        cur = conn.execute(f"""
            DELETE FROM tool_call_logs 
            WHERE call_time < datetime('now', '-{tool_days} days')
        """)
        tool_deleted = cur.rowcount
        
        # Clean cron_run_logs
        cur = conn.execute(f"""
            DELETE FROM cron_run_logs 
            WHERE run_time < datetime('now', '-{cron_days} days')
        """)
        cron_deleted = cur.rowcount
        
        conn.commit()
        
        return {
            'ok': True,
            'tool_call_logs_deleted': tool_deleted,
            'cron_run_logs_deleted': cron_deleted,
        }
    except Exception as exc:
        return {'ok': False, 'error': str(exc)}
    finally:
        conn.close()


def vacuum_database() -> Dict[str, Any]:
    """Execute VACUUM to reclaim disk space."""
    init_db()
    conn = get_conn()
    
    try:
        conn.execute("VACUUM")
        return {'ok': True}
    except Exception as exc:
        return {'ok': False, 'error': str(exc)}
    finally:
        conn.close()
