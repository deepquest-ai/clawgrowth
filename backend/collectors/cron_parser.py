import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import CRON_RUNS_DIR, OPENCLAW_ROOT


def get_cron_files() -> List[Path]:
    """Return sorted list of cron run JSONL files."""
    if not CRON_RUNS_DIR.exists():
        return []
    return sorted(CRON_RUNS_DIR.glob('*.jsonl'))


def _parse_run_time(value: Any) -> Optional[str]:
    """Convert a run timestamp (ms epoch, ISO string, or None) to ISO string."""
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)):
            dt = datetime.fromtimestamp(value / 1000, tz=timezone.utc)
            return dt.isoformat()
        text = str(value)
        return datetime.fromisoformat(text.replace('Z', '+00:00')).isoformat()
    except Exception:
        return str(value)


def parse_cron_logs(agent_id: str) -> List[Dict[str, Any]]:
    """
    Parse cron run logs for a specific agent.

    Bug fix: the old code returned ALL cron runs regardless of agent.
    Now we filter by sessionKey containing 'agent:{agent_id}:'
    OR by agentId field matching agent_id directly.
    """
    agent_prefix = f'agent:{agent_id}:'
    results: List[Dict[str, Any]] = []

    for filepath in get_cron_files():
        try:
            with filepath.open('r', encoding='utf-8') as f:
                lines = f.readlines()
        except Exception:
            continue

        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue

            if item.get('action') != 'finished':
                continue

            # Agent attribution: check sessionKey or agentId field
            session_key = item.get('sessionKey', '') or ''
            item_agent_id = item.get('agentId', '') or ''
            belongs_to_agent = (
                agent_prefix in session_key
                or session_key.startswith(agent_prefix)
                or item_agent_id == agent_id
            )
            if not belongs_to_agent:
                continue

            usage = item.get('usage', {}) or {}
            # Token field names vary across versions
            input_tokens = int(
                usage.get('input_tokens', usage.get('inputTokens', usage.get('input', 0))) or 0
            )
            output_tokens = int(
                usage.get('output_tokens', usage.get('outputTokens', usage.get('output', 0))) or 0
            )
            total_tokens = int(
                usage.get('total_tokens', usage.get('totalTokens', input_tokens + output_tokens)) or 0
            )

            status = item.get('status', 'unknown') or 'unknown'
            results.append({
                'agent_id': agent_id,
                'job_id': item.get('jobId', filepath.stem),
                'job_name': item.get('jobName', item.get('jobId', filepath.stem)),
                'status': status,
                'error_message': item.get('error') or item.get('errorMessage'),
                'duration_ms': int(item.get('durationMs', 0) or 0),
                'input_tokens': input_tokens,
                'output_tokens': output_tokens,
                'total_tokens': total_tokens,
                'model': item.get('model'),
                'provider': item.get('provider'),
                'run_time': _parse_run_time(item.get('ts') or item.get('runTime') or item.get('timestamp')),
                'raw_json': json.dumps(item, ensure_ascii=False),
            })

    return results


def get_cron_jobs_config(agent_id: str) -> Dict[str, Any]:
    """
    Read cron/jobs.json and return per-agent cron job configuration summary.

    Returns a dict with jobs_total, jobs_enabled, avg_duration_ms,
    recent_errors list, runs_today, success_today fields.
    """
    jobs_file = OPENCLAW_ROOT / 'cron' / 'jobs.json'
    default: Dict[str, Any] = {
        'jobs_total': 0,
        'jobs_enabled': 0,
        'runs_today': 0,
        'success_today': 0,
        'avg_duration_ms': 0,
        'recent_errors': [],
    }

    if not jobs_file.exists():
        return default

    try:
        data = json.loads(jobs_file.read_text(encoding='utf-8'))
    except Exception:
        return default

    all_jobs = data.get('jobs', [])
    # Filter to this agent's jobs
    agent_jobs = [j for j in all_jobs if j.get('agentId') == agent_id]

    jobs_total = len(agent_jobs)
    jobs_enabled = sum(1 for j in agent_jobs if j.get('enabled'))

    return {
        'jobs_total': jobs_total,
        'jobs_enabled': jobs_enabled,
        'runs_today': 0,      # filled in by service after parsing logs
        'success_today': 0,
        'avg_duration_ms': 0,
        'recent_errors': [],
    }
