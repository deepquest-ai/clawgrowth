"""
status.py — Four-status calculation for ClawGrowth agents.

v5.0: Three-dimensional fusion algorithm.
  Energy  = context_remaining(50%) + compaction_health(30%) + freshness(20%)
  Health  = cron_quality(40%)      + tool_health(35%)       + error_trend(25%)
  Mood    = interaction_quality(40%) + activity(30%)        + output_richness(30%)
  Hunger  = time_freshness(50%)    + depth_trend(30%)       + breadth(20%)

Each status returns {"value": float, "breakdown": {...}, "formula": "...", "formula_zh": "..."}.
"""
import json
import math
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    """Clamp a value to [low, high] and round to 2 decimal places."""
    return round(max(low, min(high, value)), 2)


# Tool categories for breadth calculation
TOOL_CATEGORIES = {
    'file':    ['read', 'write', 'edit'],
    'exec':    ['exec', 'process'],
    'search':  ['web_search', 'web_fetch'],
    'browser': ['browser'],
    'nodes':   ['nodes'],
    'message': ['message', 'tts'],
    'session': ['sessions_list', 'sessions_send', 'sessions_spawn',
                'sessions_history', 'subagents', 'agents_list'],
    'media':   ['image', 'pdf', 'canvas'],
    'system':  ['session_status'],
}
TOTAL_CATEGORIES = len(TOOL_CATEGORIES)  # 9


# ---------------------------------------------------------------------------
# Internal data helpers
# ---------------------------------------------------------------------------

def _get_sessions_dir(agent_id: str) -> Optional[Path]:
    try:
        from config import AGENTS_DIR
        sd = AGENTS_DIR / agent_id / 'sessions'
        return sd if sd.exists() else None
    except Exception:
        return None


def _get_workspace_dir(agent_id: str) -> Optional[Path]:
    try:
        from config import OPENCLAW_ROOT
        wd = OPENCLAW_ROOT / f'workspace-{agent_id}'
        return wd if wd.exists() else None
    except Exception:
        return None


def weighted_stop_reasons(
    events: List[Tuple[float, str]], decay_hours: float = 12.0
) -> Dict[str, float]:
    """
    Exponential time-decay weighting of stop_reason events.
    Half-life = decay_hours. More recent events have higher weight.
    events: [(unix_timestamp, stop_reason), ...]
    """
    now = time.time()
    good = 0.0
    bad = 0.0
    for ts, stop_reason in events:
        hours_ago = (now - ts) / 3600
        weight = math.exp(-hours_ago / decay_hours)
        if stop_reason in ('stop', 'end_turn', 'tool_use'):
            good += weight
        elif stop_reason in ('max_tokens', 'error', 'timeout'):
            bad += weight
    return {'good': good, 'bad': bad, 'total': good + bad}


def get_recent_stop_reasons(agent_id: str, hours: float) -> List[Tuple[float, str]]:
    """
    Extract stop_reason events from session JSONL files within the last N hours.
    Returns [(unix_timestamp, stop_reason), ...].
    """
    sd = _get_sessions_dir(agent_id)
    if not sd:
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    events: List[Tuple[float, str]] = []

    for fp in sd.glob('*.jsonl'):
        try:
            with fp.open('r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    item = json.loads(line)
                    if item.get('type') != 'message':
                        continue
                    msg = item.get('message', item) or {}
                    if msg.get('role') != 'assistant':
                        continue
                    stop = msg.get('stopReason', '') or ''
                    if not stop:
                        continue
                    ts_str = item.get('timestamp', '')
                    unix_ts = time.time()
                    if ts_str:
                        try:
                            ts_dt = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                            if ts_dt < cutoff:
                                continue
                            unix_ts = ts_dt.timestamp()
                        except Exception:
                            pass
                    events.append((unix_ts, stop))
        except Exception:
            continue

    return events


def get_recent_tool_category_count(agent_id: str, days: int = 7) -> int:
    """Count distinct tool categories used in session files over the last N days."""
    sd = _get_sessions_dir(agent_id)
    if not sd:
        return 0

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    used_categories: set = set()

    for fp in sd.glob('*.jsonl'):
        try:
            with fp.open('r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    item = json.loads(line)
                    ts_str = item.get('timestamp', '')
                    if ts_str:
                        try:
                            ts_dt = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                            if ts_dt < cutoff:
                                continue
                        except Exception:
                            pass
                    msg = item.get('message', item) or {}
                    for block in msg.get('content', []) or []:
                        if block.get('type') == 'toolCall':
                            name = block.get('name', '')
                            for cat, tools in TOOL_CATEGORIES.items():
                                if name in tools:
                                    used_categories.add(cat)
                                    break
        except Exception:
            continue

    return len(used_categories)


def _get_latest_session_info(agent_id: str) -> Dict[str, Any]:
    """
    Read sessions.json and return the most recent session's token stats.
    Returns: current_tokens, context_tokens, compaction, updated_at_ms.
    """
    default = {
        'current_tokens': 0,
        'context_tokens': 200000,
        'compaction': 0,
        'updated_at_ms': 0,
    }
    try:
        from config import AGENTS_DIR
        sessions_file = AGENTS_DIR / agent_id / 'sessions' / 'sessions.json'
    except Exception:
        return default

    if not sessions_file.exists():
        return default

    try:
        with sessions_file.open('r', encoding='utf-8') as f:
            sessions_data = json.load(f)
    except Exception:
        return default

    prefix = f'agent:{agent_id}:'
    latest_session = None
    latest_updated_at: Any = 0

    for key, session in sessions_data.items():
        if not isinstance(session, dict):
            continue
        if prefix not in key and not key.startswith(prefix):
            continue
        updated_at = session.get('updatedAt', 0) or 0
        if updated_at > latest_updated_at:
            latest_updated_at = updated_at
            latest_session = session

    if not latest_session:
        return default

    # updated_at_ms: normalize to milliseconds
    updated_at_ms = 0
    if latest_updated_at:
        if isinstance(latest_updated_at, (int, float)):
            # If it looks like seconds (< year 3000 in ms), convert
            updated_at_ms = int(latest_updated_at) if latest_updated_at > 1e10 else int(latest_updated_at * 1000)
        elif isinstance(latest_updated_at, str):
            try:
                dt = datetime.fromisoformat(latest_updated_at.replace('Z', '+00:00'))
                updated_at_ms = int(dt.timestamp() * 1000)
            except Exception:
                pass

    return {
        'current_tokens': int(latest_session.get('totalTokens', 0) or 0),
        'context_tokens': int(latest_session.get('contextTokens', 200000) or 200000),
        'compaction':     int(latest_session.get('compactionCount', 0) or 0),
        'updated_at_ms':  updated_at_ms,
    }


def _get_workspace_learning_info(agent_id: str) -> Dict[str, Any]:
    """
    Scan workspace files and return learning / error metrics for status calculation.
    Returns: last_mtime (unix seconds), recent_words, errors_count.
    """
    try:
        from config import OPENCLAW_ROOT
        workspace = OPENCLAW_ROOT / f'workspace-{agent_id}'
    except Exception:
        return {'last_mtime': 0.0, 'recent_words': 0, 'errors_count': 0}

    mtimes: List[float] = []
    recent_words = 0
    errors_count = 0
    now = time.time()

    # LEARNINGS.md
    learnings_md = workspace / '.learnings' / 'LEARNINGS.md'
    if learnings_md.exists():
        try:
            mtime = learnings_md.stat().st_mtime
            mtimes.append(mtime)
            if now - mtime < 7 * 86400:
                content = learnings_md.read_text(errors='ignore')
                recent_words = len(content)
        except Exception:
            pass

    # ERRORS.md
    errors_md = workspace / '.learnings' / 'ERRORS.md'
    if errors_md.exists():
        try:
            content = errors_md.read_text(errors='ignore')
            errors_count = sum(1 for line in content.splitlines() if line.startswith('## '))
        except Exception:
            pass

    # Most recent memory file
    memory_dir = workspace / 'memory'
    if memory_dir.exists():
        mds = list(memory_dir.glob('*.md'))
        if mds:
            try:
                mtimes.append(max(f.stat().st_mtime for f in mds))
            except Exception:
                pass

    # MEMORY.md
    memory_md = workspace / 'MEMORY.md'
    if memory_md.exists():
        try:
            mtimes.append(memory_md.stat().st_mtime)
        except Exception:
            pass

    # Skills directory
    skills_dir = workspace / 'skills'
    if skills_dir.exists():
        skill_dirs = [d for d in skills_dir.iterdir() if d.is_dir()]
        if skill_dirs:
            try:
                mtimes.append(max(d.stat().st_mtime for d in skill_dirs))
            except Exception:
                pass

    return {
        'last_mtime':   max(mtimes) if mtimes else 0.0,
        'recent_words': recent_words,
        'errors_count': errors_count,
    }


def _calc_conversation_quality_7d(agent_id: str) -> Optional[float]:
    """
    Compute 7-day conversation quality from stop_reason in JSONL files.
    Returns percentage of good stop reasons, or None if no data.
    """
    sd = _get_sessions_dir(agent_id)
    if not sd:
        return None

    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    good = 0
    bad = 0

    for fp in sd.glob('*.jsonl'):
        try:
            with fp.open('r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    item = json.loads(line)
                    if item.get('type') != 'message':
                        continue
                    msg = item.get('message', item) or {}
                    if msg.get('role') != 'assistant':
                        continue
                    ts_str = item.get('timestamp', '')
                    if ts_str:
                        try:
                            ts_dt = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                            if ts_dt < cutoff:
                                continue
                        except Exception:
                            pass
                    stop = msg.get('stopReason', '') or ''
                    if stop in ('stop', 'end_turn', 'tool_use'):
                        good += 1
                    elif stop in ('max_tokens', 'error', 'timeout'):
                        bad += 1
        except Exception:
            continue

    total = good + bad
    if total == 0:
        return None
    return good / total * 100


# ---------------------------------------------------------------------------
# Main status calculation
# ---------------------------------------------------------------------------

def calc_status(
    data: Dict[str, Any],
    db=None,
    prev_status: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Calculate the four agent status values with full breakdown dicts.

    Parameters:
      data        — dict containing at least 'agent_id'
      db          — sqlite3 Connection (or None — graceful degradation)
      prev_status — previous status for EMA smoothing (optional)

    Returns:
      {
        "energy": {"value": float, "breakdown": {...}, "formula": "...", "formula_zh": "..."},
        "health": {...},
        "mood":   {...},
        "hunger": {...},
      }
    """
    agent_id = data.get('agent_id', '') or ''

    # ==================================================================
    # 1. Energy: workload / context health
    #    context_remaining(50%) + compaction_health(30%) + freshness(20%)
    # ==================================================================
    if agent_id:
        sess = _get_latest_session_info(agent_id)
        current_tokens = sess['current_tokens']
        context_tokens = sess['context_tokens']
        compaction     = sess['compaction']
        updated_at_ms  = sess['updated_at_ms']
    else:
        current_tokens = int(data.get('context_usage', 0) or 0) * 2000
        context_tokens = 200000
        compaction     = int(data.get('compaction_count', 0) or 0)
        updated_at_ms  = 0

    context_remaining_score = clamp(100.0 - current_tokens / max(context_tokens, 1) * 100.0)
    # Each compaction costs 15 pts; 7+ compactions = 0
    compaction_score = clamp(100.0 - compaction * 15.0)

    if updated_at_ms:
        session_age_h = (time.time() - updated_at_ms / 1000) / 3600
    else:
        session_age_h = 99
    # Full freshness for <8h, linear decay, minimum 5
    freshness_score = clamp(max(5.0, 100.0 - max(0, session_age_h - 8) * 3.0))

    energy_raw = (
        context_remaining_score * 0.5
        + compaction_score       * 0.3
        + freshness_score        * 0.2
    )
    energy = clamp(energy_raw)

    energy_result = {
        'value': energy,
        'breakdown': [
            {
                'name': 'context_remaining_score',
                'value': round(context_remaining_score * 0.5, 2),
                'formula': f'(100 - {current_tokens}/{context_tokens} × 100) × 0.5 = {round(context_remaining_score, 1)}% × 0.5',
            },
            {
                'name': 'compaction_score',
                'value': round(compaction_score * 0.3, 2),
                'formula': f'(100 - {compaction} × 15) × 0.3 = {round(compaction_score, 1)} × 0.3',
            },
            {
                'name': 'freshness_score',
                'value': round(freshness_score * 0.2, 2),
                'formula': f'session_age={round(session_age_h, 1)}h → {round(freshness_score, 1)} × 0.2',
            },
        ],
        'source_data': {
            'current_tokens': current_tokens,
            'context_tokens': context_tokens,
            'compaction_count': compaction,
            'session_age_hours': round(session_age_h, 1),
        },
        'formula':    'context_remaining×0.5 + compaction×0.3 + freshness×0.2',
        'formula_zh': '上下文剩余×0.5 + 压缩健康×0.3 + 活跃新鲜度×0.2',
    }

    # ==================================================================
    # 2. Health: task completion quality
    #    cron_quality(40%) + tool_health(35%) + error_trend(25%)
    # ==================================================================
    workspace_info = _get_workspace_learning_info(agent_id) if agent_id else {
        'last_mtime': 0.0, 'recent_words': 0, 'errors_count': 0
    }

    recent_error_entries = workspace_info['errors_count']
    error_trend_score = clamp(100.0 - recent_error_entries * 10.0)

    if db and agent_id:
        cron_row = db.execute("""
            SELECT COUNT(*) as runs,
                   SUM(CASE WHEN status='ok' THEN 1 ELSE 0 END) as success
            FROM cron_run_logs
            WHERE agent_id=? AND run_time >= datetime('now','-7 days')
        """, (agent_id,)).fetchone()
        cron_runs_7d    = int(cron_row['runs']    or 0) if cron_row else 0
        cron_success_7d = int(cron_row['success'] or 0) if cron_row else 0

        tool_row = db.execute("""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN is_error=1 THEN 1 ELSE 0 END) as errors
            FROM tool_call_logs
            WHERE agent_id=? AND call_time >= datetime('now','-7 days')
        """, (agent_id,)).fetchone()
        tool_total  = int(tool_row['total']  or 0) if tool_row else 0
        tool_errors = int(tool_row['errors'] or 0) if tool_row else 0
        tool_health_score = clamp((1.0 - tool_errors / max(tool_total, 1)) * 100.0)

        if cron_runs_7d > 0:
            cron_quality_val = cron_success_7d / cron_runs_7d * 100.0
            cron_quality_score = round(cron_quality_val * 0.4, 2)
            tool_health_part   = round(tool_health_score  * 0.35, 2)
            error_part         = round(error_trend_score  * 0.25, 2)
            health = clamp(cron_quality_score + tool_health_part + error_part)
        else:
            cron_quality_score = 0.0
            tool_health_part   = round(tool_health_score * 0.6, 2)
            error_part         = round(error_trend_score * 0.4, 2)
            health = clamp(tool_health_part + error_part)
    else:
        cron_runs_7d    = int(data.get('cron_runs_7d', data.get('cron_runs', 0)) or 0)
        cron_success_7d = int(data.get('cron_success_7d', data.get('cron_success', 0)) or 0)
        conv_quality    = _calc_conversation_quality_7d(agent_id) if agent_id else None
        tool_health_score = conv_quality if conv_quality is not None else 75.0

        if cron_runs_7d > 0:
            cron_quality_val   = cron_success_7d / cron_runs_7d * 100.0
            cron_quality_score = round(cron_quality_val * 0.4, 2)
            tool_health_part   = round(tool_health_score * 0.35, 2)
            error_part         = round(error_trend_score * 0.25, 2)
            health = clamp(cron_quality_score + tool_health_part + error_part)
        else:
            cron_quality_score = 0.0
            tool_health_part   = round(tool_health_score * 0.6, 2)
            error_part         = round(error_trend_score * 0.4, 2)
            health = clamp(tool_health_part + error_part)

    cron_success_pct = round(cron_success_7d / max(cron_runs_7d, 1) * 100, 1)
    health_result = {
        'value': health,
        'breakdown': [
            {
                'name': 'cron_quality_score',
                'value': cron_quality_score,
                'formula': f'{cron_success_7d}/{cron_runs_7d} × 100 × 0.4 = {cron_success_pct}% × 0.4',
            },
            {
                'name': 'tool_health_score',
                'value': tool_health_part,
                'formula': f'tool_health={round(tool_health_score, 1)}% × 0.35',
            },
            {
                'name': 'error_trend_score',
                'value': error_part,
                'formula': f'(100 - {recent_error_entries} × 10) × 0.25 = {round(error_trend_score, 1)} × 0.25',
            },
        ],
        'source_data': {
            'cron_runs_7d': cron_runs_7d,
            'cron_success_7d': cron_success_7d,
            'cron_success_rate': cron_success_pct,
            'recent_error_entries': recent_error_entries,
        },
        'formula':    'cron_quality×0.4 + tool_health×0.35 + error_trend×0.25',
        'formula_zh': 'Cron质量×0.4 + 工具健康×0.35 + 错误趋势×0.25',
    }

    # ==================================================================
    # 3. Mood: recent interaction quality and activity (last 24h)
    #    interaction_quality(40%) + activity(30%) + output_richness(30%)
    # ==================================================================
    if agent_id:
        events_24h = get_recent_stop_reasons(agent_id, hours=24)
        if events_24h:
            sr = weighted_stop_reasons(events_24h, decay_hours=12)
            interaction_quality_score = clamp(sr['good'] / sr['total'] * 100) if sr['total'] > 0 else 85.0
        else:
            interaction_quality_score = 85.0
    else:
        interaction_quality_score = 85.0

    if db and agent_id:
        today_row = db.execute("""
            SELECT COUNT(DISTINCT session_id) as cnt
            FROM tool_call_logs
            WHERE agent_id=? AND date(call_time)=date('now')
        """, (agent_id,)).fetchone()
        today_convs = int(today_row['cnt'] or 0) if today_row else 0

        weekly_row = db.execute("""
            SELECT COUNT(DISTINCT session_id) * 1.0 / 7 as avg
            FROM tool_call_logs
            WHERE agent_id=? AND call_time >= datetime('now','-7 days')
        """, (agent_id,)).fetchone()
        weekly_avg = float(weekly_row['avg'] or 1.0) if weekly_row else 1.0
        activity_ratio = today_convs / max(weekly_avg, 1)
        activity_score = clamp(activity_ratio * 60 + 20)

        token_row = db.execute("""
            SELECT SUM(input_tokens) as inp, SUM(output_tokens) as out
            FROM tool_call_logs
            WHERE agent_id=? AND call_time >= datetime('now','-1 day')
        """, (agent_id,)).fetchone()
        inp = int(token_row['inp'] or 0) if token_row else 0
        out = int(token_row['out'] or 0) if token_row else 0
        output_richness_score = clamp((out / max(inp, 1)) * 150)

        iq_part  = round(interaction_quality_score * 0.4, 2)
        act_part = round(activity_score            * 0.3, 2)
        or_part  = round(output_richness_score     * 0.3, 2)
        mood = clamp(iq_part + act_part + or_part)
    else:
        activity_score        = 50.0
        output_richness_score = 50.0
        iq_part  = round(interaction_quality_score * 0.4, 2)
        act_part = round(activity_score            * 0.3, 2)
        or_part  = round(output_richness_score     * 0.3, 2)
        mood = clamp(iq_part + act_part + or_part)

    mood_result = {
        'value': mood,
        'breakdown': [
            {
                'name': 'interaction_quality_score',
                'value': iq_part,
                'formula': f'good_stop_ratio={round(interaction_quality_score, 1)}% × 0.4',
            },
            {
                'name': 'activity_score',
                'value': act_part,
                'formula': f'activity_level={round(activity_score, 1)} × 0.3',
            },
            {
                'name': 'output_richness_score',
                'value': or_part,
                'formula': f'output_richness={round(output_richness_score, 1)} × 0.3',
            },
        ],
        'source_data': {
            'interaction_quality': round(interaction_quality_score, 1),
            'activity_level': round(activity_score, 1),
            'output_richness': round(output_richness_score, 1),
        },
        'formula':    'interaction_quality×0.4 + activity×0.3 + output_richness×0.3',
        'formula_zh': '交互质量×0.4 + 活跃度×0.3 + 输出丰富度×0.3',
    }

    # ==================================================================
    # 4. Hunger: knowledge freshness and exploration drive
    #    time_freshness(50%) + depth_trend(30%) + breadth(20%)
    # ==================================================================
    if agent_id:
        last_mtime = workspace_info['last_mtime']

        if last_mtime > 0:
            hours_since = max(0.0, (time.time() - last_mtime) / 3600)
            time_freshness_score = clamp(100.0 - hours_since * 2.0)
        else:
            time_freshness_score = 0.0

        recent_words = workspace_info['recent_words']
        if db:
            hist_row = db.execute("""
                SELECT AVG(learnings_words) as avg
                FROM daily_snapshots
                WHERE agent_id=? AND date >= date('now','-30 days')
            """, (agent_id,)).fetchone()
            baseline_words = float(hist_row['avg'] or 0) if hist_row else 0.0
        else:
            baseline_words = 0.0

        if baseline_words > 0:
            depth_ratio = recent_words / baseline_words
            depth_score = clamp(depth_ratio * 70.0 + 15.0)
        else:
            depth_score = 50.0  # neutral when no historical baseline

        tool_cat_count = get_recent_tool_category_count(agent_id, days=7)
        breadth_score = clamp(tool_cat_count / TOTAL_CATEGORIES * 100.0)

        tf_part = round(time_freshness_score * 0.5, 2)
        dp_part = round(depth_score          * 0.3, 2)
        br_part = round(breadth_score        * 0.2, 2)
        hunger = clamp(tf_part + dp_part + br_part)
    else:
        time_freshness_score = 0.0
        depth_score          = 0.0
        breadth_score        = 0.0
        tf_part = dp_part = br_part = 0.0
        hunger = 0.0

    hours_since_learning = round((time.time() - workspace_info.get('last_mtime', 0)) / 3600, 1) if workspace_info.get('last_mtime', 0) > 0 else 999
    hunger_result = {
        'value': hunger,
        'breakdown': [
            {
                'name': 'time_freshness_score',
                'value': tf_part,
                'formula': f'(100 - {round(hours_since_learning, 1)}h × 2) × 0.5 = {round(time_freshness_score, 1)} × 0.5',
            },
            {
                'name': 'depth_score',
                'value': dp_part,
                'formula': f'recent_words={workspace_info.get("recent_words", 0)} → {round(depth_score, 1)} × 0.3',
            },
            {
                'name': 'breadth_score',
                'value': br_part,
                'formula': f'tool_categories={tool_cat_count}/{TOTAL_CATEGORIES} × 100 × 0.2',
            },
        ],
        'source_data': {
            'hours_since_learning': hours_since_learning,
            'recent_words': workspace_info.get('recent_words', 0),
            'tool_categories_used': tool_cat_count,
            'total_categories': TOTAL_CATEGORIES,
        },
        'formula':    'time_freshness×0.5 + depth×0.3 + breadth×0.2',
        'formula_zh': '学习新鲜度×0.5 + 深度×0.3 + 广度×0.2',
    }

    # ==================================================================
    # 5. Status coupling corrections
    # ==================================================================
    # Low energy reduces mood (fatigue affects sentiment)
    if energy < 30:
        mood = clamp(mood * 0.85)
        mood_result['value'] = mood

    # Long-term hunger (>72h without learning) degrades health
    if agent_id:
        lm = workspace_info.get('last_mtime', 0.0)
        hours_since_any = (time.time() - lm) / 3600 if lm > 0 else 999
        if hunger < 20 and hours_since_any > 72:
            health = clamp(health * 0.90)
            health_result['value'] = health

    # ==================================================================
    # 6. EMA smoothing (prevent abrupt swings from single-run failures)
    # ==================================================================
    ALPHA = 0.3
    if prev_status:
        def _prev_val(key: str, current: float) -> float:
            prev = prev_status.get(key)
            if isinstance(prev, dict):
                return float(prev.get('value', current))
            if isinstance(prev, (int, float)):
                return float(prev)
            return current

        energy = clamp(ALPHA * energy + (1 - ALPHA) * _prev_val('energy', energy))
        health = clamp(ALPHA * health + (1 - ALPHA) * _prev_val('health', health))
        mood   = clamp(ALPHA * mood   + (1 - ALPHA) * _prev_val('mood',   mood))
        hunger = clamp(ALPHA * hunger + (1 - ALPHA) * _prev_val('hunger', hunger))

        energy_result['value'] = energy
        health_result['value'] = health
        mood_result['value']   = mood
        hunger_result['value'] = hunger

    return {
        'energy': energy_result,
        'health': health_result,
        'mood':   mood_result,
        'hunger': hunger_result,
    }


# ---------------------------------------------------------------------------
# Legacy helper — kept for backward compatibility with any remaining callers
# ---------------------------------------------------------------------------

def get_claw_color(status: Dict[str, Any]) -> Dict[str, Any]:
    """Return claw color based on average of the four status values."""
    CRAYFISH_COLORS = [
        (80, '#E84B3A', 'red',    'Excellent!'),
        (60, '#F5A623', 'orange', 'Good'),
        (40, '#4DB8A4', 'teal',   'Normal'),
        (20, '#5B9BD5', 'blue',   'Tired'),
        (0,  '#9B5DE5', 'purple', 'Danger!'),
    ]

    def _val(s: Any) -> float:
        if isinstance(s, dict):
            return float(s.get('value', 0))
        return float(s or 0)

    avg = (
        _val(status.get('energy'))
        + _val(status.get('health'))
        + _val(status.get('mood'))
        + _val(status.get('hunger'))
    ) / 4
    avg = round(avg, 2)

    for threshold, hex_color, name, label in CRAYFISH_COLORS:
        if avg >= threshold:
            return {'avg': avg, 'hex': hex_color, 'name': name, 'label': label}
    return {'avg': avg, 'hex': '#9B5DE5', 'name': 'purple', 'label': 'Danger!'}
