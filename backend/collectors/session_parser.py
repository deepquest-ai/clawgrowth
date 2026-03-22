import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import AGENTS_DIR

# Map tool names to broad categories
TOOL_CATEGORY_MAP = {
    'read':              'file',
    'write':             'file',
    'edit':              'file',
    'exec':              'exec',
    'process':           'exec',
    'web_search':        'search',
    'web_fetch':         'search',
    'browser':           'browser',
    'nodes':             'nodes',
    'message':           'message',
    'tts':               'message',
    'sessions_list':     'session',
    'sessions_history':  'session',
    'sessions_send':     'session',
    'sessions_spawn':    'session',
    'subagents':         'session',
    'agents_list':       'session',
    'image':             'media',
    'pdf':               'media',
    'canvas':            'media',
    'session_status':    'system',
}


def _session_dir(agent_id: str) -> Path:
    return AGENTS_DIR / agent_id / 'sessions'


def get_session_files(agent_id: str) -> List[Path]:
    """Return sorted list of .jsonl session files for an agent."""
    sd = _session_dir(agent_id)
    if not sd.exists():
        return []
    return sorted(sd.glob('*.jsonl'))


def _parse_iso(value: Optional[str]) -> str:
    """Parse an ISO timestamp string; return current UTC time string on failure."""
    if not value:
        return datetime.now(timezone.utc).isoformat()
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00')).isoformat()
    except Exception:
        return datetime.now(timezone.utc).isoformat()


def parse_session_file(filepath: Path, agent_id: str) -> List[Dict[str, Any]]:
    """
    Parse a single session JSONL file and return a list of tool call events.

    Each event contains:
      session_id, tool_name, tool_category, input_tokens, output_tokens,
      cache_read, stop_reason, is_error, call_time, raw_json
    """
    tool_calls: List[Dict[str, Any]] = []
    session_id = filepath.stem

    try:
        with filepath.open('r', encoding='utf-8') as f:
            lines = f.readlines()
    except Exception:
        return tool_calls

    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue

        if item.get('type') != 'message':
            continue

        message = item.get('message', {}) or {}
        if message.get('role') != 'assistant':
            continue

        usage = message.get('usage', {}) or {}
        contents = message.get('content', []) or []
        stop_reason = message.get('stopReason', '') or ''
        ts = _parse_iso(item.get('timestamp'))

        for content in contents:
            content_type = content.get('type', '')

            # Capture tool calls
            if content_type == 'toolCall':
                tool_name = content.get('name', 'unknown')
                tool_calls.append({
                    'session_id': session_id,
                    'tool_name': tool_name,
                    'tool_category': TOOL_CATEGORY_MAP.get(tool_name, 'other'),
                    'input_tokens': int(usage.get('input', 0) or 0),
                    'output_tokens': int(usage.get('output', 0) or 0),
                    'cache_read': int(usage.get('cacheRead', 0) or 0),
                    'stop_reason': stop_reason,
                    'is_error': 0,
                    'call_time': ts,
                    'raw_json': json.dumps(content, ensure_ascii=False),
                })

            # Capture tool result errors — attach is_error flag to the most recent tool call
            elif content_type == 'toolResult':
                is_err = 1 if content.get('is_error') else 0
                if is_err and tool_calls:
                    tool_calls[-1]['is_error'] = is_err

    return tool_calls


def collect_session_logs(agent_id: str) -> List[Dict[str, Any]]:
    """Collect all tool call events from all session JSONL files for an agent."""
    logs: List[Dict[str, Any]] = []
    for filepath in get_session_files(agent_id):
        logs.extend(parse_session_file(filepath, agent_id))
    return logs


def parse_sessions_index(agent_id: str) -> Dict[str, Any]:
    """
    Read sessions.json and return stats for the CURRENT (most recent) session only.

    sessions.json structure:
      {
        "agent:coding-assistant:abc123": {
          "totalTokens": 45000,
          "contextTokens": 200000,
          "updatedAt": 1711008000000,   <- millisecond timestamp OR ISO string
          "compactionCount": 1
        },
        ...
      }

    Bug fix: the old code treated sessions.json as {"sessions": [...]} list.
    The real format is a flat dict keyed by session key strings.
    We filter by agent_id prefix and pick the entry with the MAX updatedAt.
    """
    default: Dict[str, Any] = {
        'total_tokens': 0,
        'context_tokens': 200000,
        'context_usage': 0.0,
        'compaction_count': 0,
        'updated_at': None,
        'hours_since_active': 24.0,
    }

    index_file = _session_dir(agent_id) / 'sessions.json'
    if not index_file.exists():
        return default

    try:
        data = json.loads(index_file.read_text(encoding='utf-8'))
    except Exception:
        return default

    if not isinstance(data, dict):
        return default

    prefix = f'agent:{agent_id}:'
    best_entry: Optional[Dict[str, Any]] = None
    best_updated_at: Any = None  # can be int (ms) or str

    for key, session in data.items():
        if not isinstance(session, dict):
            continue
        if prefix not in key and not key.startswith(prefix):
            continue
        updated_at = session.get('updatedAt')
        if updated_at is None:
            continue
        if best_updated_at is None or updated_at > best_updated_at:
            best_updated_at = updated_at
            best_entry = session

    if best_entry is None:
        return default

    total_tokens = int(best_entry.get('totalTokens', 0) or 0)
    context_tokens = int(best_entry.get('contextTokens', 200000) or 200000)
    compaction_count = int(best_entry.get('compactionCount', 0) or 0)

    # Convert updatedAt to ISO string and compute hours since active
    updated_at_iso: Optional[str] = None
    hours_since_active = 24.0
    if best_updated_at:
        try:
            if isinstance(best_updated_at, (int, float)):
                # Millisecond epoch timestamp
                dt = datetime.fromtimestamp(best_updated_at / 1000, tz=timezone.utc)
            else:
                dt = datetime.fromisoformat(str(best_updated_at).replace('Z', '+00:00'))
            updated_at_iso = dt.isoformat()
            now = datetime.now(timezone.utc)
            hours_since_active = max(0.0, (now - dt).total_seconds() / 3600)
        except Exception:
            pass

    context_usage = round((total_tokens / context_tokens) * 100, 2) if context_tokens > 0 else 0.0

    return {
        'total_tokens': total_tokens,
        'context_tokens': context_tokens,
        'context_usage': min(100.0, context_usage),
        'compaction_count': compaction_count,
        'updated_at': updated_at_iso,
        'hours_since_active': round(hours_since_active, 2),
    }
