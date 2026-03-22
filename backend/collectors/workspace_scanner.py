import json
import re
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urlparse

from config import OPENCLAW_ROOT, SUBAGENT_RUNS_FILE


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _workspace_dir(agent_id: str) -> Path:
    # main agent uses 'workspace' without suffix
    if agent_id == 'main':
        return OPENCLAW_ROOT / 'workspace'
    return OPENCLAW_ROOT / f'workspace-{agent_id}'


def _count_h2_sections(filepath: Path) -> int:
    """Count '## ' section headers in a markdown file."""
    if not filepath.exists():
        return 0
    try:
        text = filepath.read_text(encoding='utf-8', errors='ignore')
        return sum(1 for line in text.splitlines() if line.startswith('## '))
    except Exception:
        return 0


def _file_words(filepath: Path) -> int:
    """Return character count of a file (used as word-count proxy)."""
    if not filepath.exists():
        return 0
    try:
        return len(filepath.read_text(encoding='utf-8', errors='ignore'))
    except Exception:
        return 0


def _today_str() -> str:
    return datetime.now().strftime('%Y-%m-%d')


def _mtime_days_ago(filepath: Path) -> int:
    """Return integer number of days since file was last modified."""
    if not filepath.exists():
        return 9999
    try:
        age_secs = time.time() - filepath.stat().st_mtime
        return int(age_secs / 86400)
    except Exception:
        return 9999


def _file_recent(filepath: Path, days: int = 7) -> bool:
    """Return True if the file was modified within the last N days."""
    return _mtime_days_ago(filepath) < days


# ---------------------------------------------------------------------------
# scan_workspace — per-agent workspace metrics
# ---------------------------------------------------------------------------

def scan_workspace(agent_id: str, shared_workspace_dir: Optional[Path] = None) -> Dict[str, Any]:
    """
    Scan the agent workspace directory and return all workspace metrics.

    Workspace layout expected:
      ~/.openclaw/workspace-{agent_id}/
        skills/                  <- agent-specific skills
        memory/                  <- memory files (YYYY-MM-DD*.md)
        .learnings/
          LEARNINGS.md
          ERRORS.md
          FEATURE_REQUESTS.md
        MEMORY.md
        AGENTS.md, SOUL.md, TOOLS.md, IDENTITY.md
      ~/.openclaw/workspace/skills/  <- shared skills
    """
    root = _workspace_dir(agent_id)
    today = _today_str()

    # --- Skills count ---
    local_skills_dir = root / 'skills'
    shared_skills_dir = (
        shared_workspace_dir / 'skills'
        if shared_workspace_dir
        else OPENCLAW_ROOT / 'workspace' / 'skills'
    )
    skills_count = 0
    if local_skills_dir.exists():
        try:
            skills_count += sum(1 for _ in local_skills_dir.iterdir())
        except Exception:
            pass
    if shared_skills_dir.exists():
        try:
            skills_count += sum(1 for _ in shared_skills_dir.iterdir())
        except Exception:
            pass

    # --- Diary / memory files ---
    memory_dir = root / 'memory'
    memory_files: List[Path] = []
    if memory_dir.exists():
        try:
            memory_files = [f for f in memory_dir.glob('*.md') if f.is_file()]
        except Exception:
            memory_files = []

    memories_count = len(memory_files)
    memories_words = sum(_file_words(f) for f in memory_files)

    # has_today_memory: any memory filename contains today's date string
    has_today_memory = any(today in f.name for f in memory_files)

    # recent_memory_count: memory files modified in the last 7 days
    recent_memory_count = sum(1 for f in memory_files if _file_recent(f, days=7))

    # last_learning_mtime: most recent mtime across all memory files
    last_learning_mtime = 0.0
    if memory_files:
        try:
            last_learning_mtime = max(f.stat().st_mtime for f in memory_files)
        except Exception:
            pass

    # --- Learnings ---
    learnings_dir = root / '.learnings'
    learnings_md = learnings_dir / 'LEARNINGS.md'
    learnings_count = _count_h2_sections(learnings_md)
    learnings_words = _file_words(learnings_md)
    recent_learning_words = learnings_words if _file_recent(learnings_md, days=7) else 0

    if learnings_md.exists():
        try:
            lm = learnings_md.stat().st_mtime
            if lm > last_learning_mtime:
                last_learning_mtime = lm
        except Exception:
            pass

    # --- Errors ---
    errors_md = learnings_dir / 'ERRORS.md'
    errors_count = _count_h2_sections(errors_md)

    # --- Feature requests ---
    feature_requests_md = learnings_dir / 'FEATURE_REQUESTS.md'
    feature_requests_count = _count_h2_sections(feature_requests_md)
    recent_feature_requests = 0
    if feature_requests_md.exists():
        try:
            text = feature_requests_md.read_text(encoding='utf-8', errors='ignore')
            # Count sections added within last 7 days by looking for date annotations
            # Fallback: count all if modified recently
            if _file_recent(feature_requests_md, days=7):
                recent_feature_requests = feature_requests_count
        except Exception:
            pass

    # --- MEMORY.md (memory sections and word count) ---
    memory_md = root / 'MEMORY.md'
    memory_sections = _count_h2_sections(memory_md)
    memory_words = _file_words(memory_md)

    if memory_md.exists():
        try:
            mm = memory_md.stat().st_mtime
            if mm > last_learning_mtime:
                last_learning_mtime = mm
        except Exception:
            pass

    # --- TOOLS.md analysis ---
    tools_md = root / 'TOOLS.md'
    tools_skills_installed = 0
    tools_external_integrations = 0
    tools_md_updated_days_ago = _mtime_days_ago(tools_md)

    if tools_md.exists():
        try:
            tools_text = tools_md.read_text(encoding='utf-8', errors='ignore')

            # Count installed skills: lines containing the installed marker (Chinese: "已安装：")
            tools_skills_installed = tools_text.count('已安装：')

            # Count unique external hostnames from http(s):// URLs
            hostnames: Set[str] = set()
            for url_match in re.finditer(r'https?://[^\s\)\]\"\'<>]+', tools_text):
                try:
                    parsed = urlparse(url_match.group())
                    if parsed.hostname:
                        hostnames.add(parsed.hostname)
                except Exception:
                    pass
            tools_external_integrations = len(hostnames)

            # Try to parse update date from markdown: "_更新于：YYYY-MM-DD_" (Chinese: "Updated on")
            date_match = re.search(r'更新于[：:]\s*(\d{4}-\d{2}-\d{2})', tools_text)
            if date_match:
                try:
                    update_date = datetime.strptime(date_match.group(1), '%Y-%m-%d')
                    now = datetime.now()
                    tools_md_updated_days_ago = (now - update_date).days
                except Exception:
                    pass
        except Exception:
            pass

    # --- Workspace completeness ---
    workspace_completeness = {
        'AGENTS.md':   (root / 'AGENTS.md').exists(),
        'SOUL.md':     (root / 'SOUL.md').exists(),
        'TOOLS.md':    tools_md.exists(),
        'MEMORY.md':   memory_md.exists(),
        'IDENTITY.md': (root / 'IDENTITY.md').exists(),
    }

    return {
        'skills_count':                skills_count,
        'memories_count':              memories_count,
        'memories_words':              memories_words,
        'has_today_memory':             has_today_memory,
        'recent_memory_count':          recent_memory_count,
        'learnings_count':             learnings_count,
        'learnings_words':             learnings_words,
        'recent_learning_words':       recent_learning_words,
        'errors_count':                errors_count,
        'feature_requests_count':      feature_requests_count,
        'recent_feature_requests':     recent_feature_requests,
        'memory_sections':             memory_sections,
        'memory_words':                memory_words,
        'tools_skills_installed':      tools_skills_installed,
        'tools_external_integrations': tools_external_integrations,
        'tools_md_updated_days_ago':   tools_md_updated_days_ago,
        'workspace_completeness':      workspace_completeness,
        'last_learning_mtime':         last_learning_mtime,
    }


# ---------------------------------------------------------------------------
# scan_shared_workspace — commander / shared workspace stats
# ---------------------------------------------------------------------------

def scan_shared_workspace() -> Dict[str, Any]:
    """
    Scan the shared ~/.openclaw/workspace/ directory for cross-agent stats.

    Returns SharedWorkspaceStats fields matching the API contract.
    """
    workspace = OPENCLAW_ROOT / 'workspace'
    now_ts = time.time()

    result: Dict[str, Any] = {
        'heartbeat_hours_ago':    None,
        'heartbeat_daily_count':  0,
        'last_task_hours_ago':    None,
        'last_task':              None,
        'projects_active_count':  0,
        'tasks_blocked':          0,
        'tasks_overdue':          0,
        'decisions_count':        0,
        'recent_decisions_count': 0,
        'reports_count':          0,
        'recent_reports_count':   0,
        'collections_count':      0,
        'handoffs_count':         0,
    }

    # --- Heartbeat state ---
    heartbeat_file = workspace / 'memory' / 'heartbeat-state.json'
    if not heartbeat_file.exists():
        # Try alternative locations
        heartbeat_file = workspace / 'heartbeat-state.json'

    if heartbeat_file.exists():
        try:
            hb = json.loads(heartbeat_file.read_text(encoding='utf-8'))
            last_beat = hb.get('lastHeartbeat') or hb.get('updatedAt')
            if last_beat:
                if isinstance(last_beat, (int, float)):
                    beat_ts = last_beat / 1000 if last_beat > 1e10 else last_beat
                else:
                    beat_ts = datetime.fromisoformat(
                        str(last_beat).replace('Z', '+00:00')
                    ).timestamp()
                result['heartbeat_hours_ago'] = round((now_ts - beat_ts) / 3600, 2)

            daily_count = hb.get('dailyCount') or hb.get('todayCount') or 0
            result['heartbeat_daily_count'] = int(daily_count)

            last_task = hb.get('lastTask') or hb.get('lastActivity')
            if last_task:
                if isinstance(last_task, str):
                    result['last_task'] = last_task
                elif isinstance(last_task, dict):
                    result['last_task'] = last_task.get('description') or str(last_task)

            last_task_ts = hb.get('lastTaskTime') or hb.get('lastActivityTime')
            if last_task_ts:
                if isinstance(last_task_ts, (int, float)):
                    lt_ts = last_task_ts / 1000 if last_task_ts > 1e10 else last_task_ts
                else:
                    lt_ts = datetime.fromisoformat(
                        str(last_task_ts).replace('Z', '+00:00')
                    ).timestamp()
                result['last_task_hours_ago'] = round((now_ts - lt_ts) / 3600, 2)
        except Exception:
            pass

    # --- Project status ---
    project_status_md = workspace / 'PROJECT_STATUS.md'
    if project_status_md.exists():
        try:
            ps_text = project_status_md.read_text(encoding='utf-8', errors='ignore')
            # Count rows with active status indicators (🟡 or 🟢)
            active_count = sum(
                1 for line in ps_text.splitlines()
                if ('🟡' in line or '🟢' in line)
            )
            result['projects_active_count'] = active_count

            # Extract blocked/overdue counts from bold annotations (Chinese: "阻塞"=blocked, "逾期"=overdue)
            blocked_match = re.search(r'\*\*阻塞\*\*[：:]\s*(\d+)', ps_text)
            if blocked_match:
                result['tasks_blocked'] = int(blocked_match.group(1))

            overdue_match = re.search(r'\*\*逾期\*\*[：:]\s*(\d+)', ps_text)
            if overdue_match:
                result['tasks_overdue'] = int(overdue_match.group(1))
        except Exception:
            pass

    # --- Decisions ---
    decisions_md = workspace / 'DECISIONS.md'
    if decisions_md.exists():
        try:
            dec_text = decisions_md.read_text(encoding='utf-8', errors='ignore')
            # Total decisions: count "- **" bullet lines
            all_decision_lines = [l for l in dec_text.splitlines() if l.startswith('- **')]
            result['decisions_count'] = len(all_decision_lines)

            # Recent decisions: within last 7 days
            # Sections are marked with "### YYYY-MM-DD" headers
            cutoff = datetime.now() - timedelta(days=7)
            in_recent_section = False
            recent_count = 0
            for line in dec_text.splitlines():
                h3_match = re.match(r'### (\d{4}-\d{2}-\d{2})', line)
                if h3_match:
                    try:
                        section_date = datetime.strptime(h3_match.group(1), '%Y-%m-%d')
                        in_recent_section = section_date >= cutoff
                    except Exception:
                        in_recent_section = False
                elif in_recent_section and line.startswith('- **'):
                    recent_count += 1
            result['recent_decisions_count'] = recent_count
        except Exception:
            pass

    # --- Reports ---
    reports_dir = workspace / 'reports'
    if reports_dir.exists():
        try:
            report_files = [f for f in reports_dir.iterdir() if f.is_file() and not f.name.startswith('.')]
            result['reports_count'] = len(report_files)
            cutoff_ts = now_ts - 7 * 86400
            result['recent_reports_count'] = sum(
                1 for f in report_files
                if f.stat().st_mtime > cutoff_ts
            )
        except Exception:
            pass

    # --- Collections ---
    collections_dir = workspace / 'collections'
    if collections_dir.exists():
        try:
            result['collections_count'] = sum(
                1 for f in collections_dir.glob('*.md')
            )
        except Exception:
            pass

    # --- Handoffs (files only, not subdirs) ---
    handoffs_dir = workspace / 'handoffs'
    if handoffs_dir.exists():
        try:
            result['handoffs_count'] = sum(
                1 for f in handoffs_dir.iterdir()
                if f.is_file() and not f.name.startswith('.')
            )
        except Exception:
            pass

    return result


# ---------------------------------------------------------------------------
# scan_collaboration — per-agent collaboration stats
# ---------------------------------------------------------------------------

def scan_collaboration(agent_id: str) -> Dict[str, Any]:
    """
    Parse subagent runs.json and return per-agent collaboration stats.

    Bug fix: the old code returned totals for ALL agents.
    Now we filter by runs where requesterSessionKey OR childSessionKey
    contains 'agent:{agent_id}:'.
    """
    if not SUBAGENT_RUNS_FILE.exists():
        return {'collaborations': 0, 'collab_success': 0, 'collab_agents': 0}

    try:
        data = json.loads(SUBAGENT_RUNS_FILE.read_text(encoding='utf-8'))
    except Exception:
        return {'collaborations': 0, 'collab_success': 0, 'collab_agents': 0}

    runs = data.get('runs', {}) if isinstance(data, dict) else {}
    agent_prefix = f'agent:{agent_id}:'
    total = 0
    success = 0
    other_agents: Set[str] = set()

    for run in runs.values():
        if not isinstance(run, dict):
            continue
        requester_key = run.get('requesterSessionKey', '') or ''
        child_key = run.get('childSessionKey', '') or ''

        # Include if this agent is either the requester or the child
        is_requester = agent_prefix in requester_key or requester_key.startswith(agent_prefix)
        is_child = agent_prefix in child_key or child_key.startswith(agent_prefix)

        if not (is_requester or is_child):
            continue

        total += 1

        # Determine success from outcome or status field
        outcome = run.get('outcome', {}) or {}
        status = outcome.get('status') or run.get('status') or ''
        if status in {'ok', 'done', 'completed', 'completed successfully', 'success'}:
            success += 1

        # Track the other agent in the collaboration
        if is_requester and child_key:
            parts = child_key.split(':')
            if len(parts) >= 2 and parts[0] == 'agent':
                other_agents.add(parts[1])
        if is_child and requester_key:
            parts = requester_key.split(':')
            if len(parts) >= 2 and parts[0] == 'agent':
                other_agents.add(parts[1])

    return {
        'collaborations': total,
        'collab_success': success,
        'collab_agents': len(other_agents),
    }


# ---------------------------------------------------------------------------
# Build full collaboration graph (for agents overview)
# ---------------------------------------------------------------------------

def build_collab_graph() -> Dict[str, Any]:
    """Build the full collaboration graph across all agents."""
    if not SUBAGENT_RUNS_FILE.exists():
        return {'nodes': [], 'edges': []}
    try:
        data = json.loads(SUBAGENT_RUNS_FILE.read_text(encoding='utf-8'))
    except Exception:
        return {'nodes': [], 'edges': []}

    runs = data.get('runs', {}) if isinstance(data, dict) else {}
    nodes: Set[str] = set()
    edges: List[Dict[str, Any]] = []

    for run in runs.values():
        if not isinstance(run, dict):
            continue
        requester = _extract_agent_id(run.get('requesterSessionKey', ''))
        child = _extract_agent_id(run.get('childSessionKey', ''))
        if requester and child:
            nodes.add(requester)
            nodes.add(child)
            outcome = run.get('outcome', {}) or {}
            status = outcome.get('status') or run.get('status') or ''
            edges.append({
                'from': requester,
                'to': child,
                'success': status in {'ok', 'done', 'completed', 'success'},
            })

    return {'nodes': list(nodes), 'edges': edges}


def _extract_agent_id(session_key: str) -> Optional[str]:
    """Extract agent_id from 'agent:{agent_id}:{session}' key format."""
    if not session_key:
        return None
    parts = session_key.split(':')
    if len(parts) >= 2 and parts[0] == 'agent':
        return parts[1]
    return None


# ---------------------------------------------------------------------------
# Utility for service
# ---------------------------------------------------------------------------

def hours_since_last_activity(updated_at: Optional[str]) -> float:
    """Compute hours since an ISO timestamp string."""
    if not updated_at:
        return 24.0
    try:
        dt = datetime.fromisoformat(updated_at.replace('Z', '+00:00'))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - dt).total_seconds() / 3600)
    except Exception:
        return 24.0
