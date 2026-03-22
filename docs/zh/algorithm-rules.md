# ClawGrowth 算法规则手册

> **原则**: 采集即存储，每个变量都能从 OpenClaw 原生数据提取并入库

---

## 零、数据存储概览

### 数据库表（6张）

| 表 | 用途 | 写入时机 |
|----|------|---------|
| **agent_profiles** | Agent 当前状态 | 每日 UPDATE |
| **daily_snapshots** | 每日汇总 | 每日 INSERT |
| **tool_call_logs** | 工具调用明细（含 stop_reason、is_error）| 每小时 INSERT |
| **cron_run_logs** | Cron 执行明细 | 每小时 INSERT |
| **collection_state** | 采集进度 | 每小时 UPDATE |
| **achievements** | 成就记录 | 达成时 INSERT |

### 数据流

```
OpenClaw 原生数据 (只读)
        │
        ▼ 每小时采集
┌───────────────────┐
│  tool_call_logs   │ ← sessions/*.jsonl（toolCall + toolResult + stopReason）
│  cron_run_logs    │ ← cron/runs/*.jsonl 中的 finished
│  collection_state │ ← 记录采集位置
└───────────────────┘
        │
        ▼ 每日 00:05 聚合
┌───────────────────┐
│  daily_snapshots  │ ← 从日志表 SELECT 聚合
│  agent_profiles   │ ← 计算评分 + 状态后更新（含 EMA 平滑）
│  achievements     │ ← 检测成就后写入
└───────────────────┘
```

详细表结构见: [database-design.md](database-design.md)

---

## 零.五、多 Agent 支持

### 0.5.1 Agent 枚举

ClawGrowth 不需要手动配置 Agent 列表，通过扫描 `agents/` 目录自动发现所有 Agent。

```python
from config import AGENTS_DIR

def discover_agents() -> list[str]:
    """
    枚举所有已部署的 Agent ID。
    规则：agents/ 下每个子目录名即为 agent_id，忽略非目录项。
    """
    if not AGENTS_DIR.exists():
        return []
    return sorted(
        d.name for d in AGENTS_DIR.iterdir()
        if d.is_dir()
    )
```

### 0.5.2 Workspace 定位

每个 Agent 有独立 workspace，同时存在所有 Agent 共享的全局 workspace：

```python
from config import OPENCLAW_ROOT

def get_workspace_dir(agent_id: str) -> Path:
    """返回 Agent 私有 workspace 路径（可能不存在）"""
    return OPENCLAW_ROOT / f'workspace-{agent_id}'

SHARED_WORKSPACE = OPENCLAW_ROOT / 'workspace'  # 共享 workspace（skills 等）
```

**Workspace 规则：**

| 路径 | 归属 |
|------|------|
| `workspace-<agent_id>/skills/` | Agent 私有技能 |
| `workspace/skills/` | 共享技能，计入每个 Agent 的 `skills_count` |
| `workspace-<agent_id>/memory/` | Agent 私有记忆 |
| `workspace-<agent_id>/.learnings/` | Agent 私有学习记录 |
| `workspace-<agent_id>/MEMORY.md` | Agent 私有长期记忆 |

### 0.5.3 跨 Agent 数据归属

```
cron/jobs.json        → job.agentId 字段决定归属
cron/runs/*.jsonl     → record.sessionKey 中 "agent:<id>:" 前缀归属
subagents/runs.json   → requesterSessionKey + childSessionKey 双向归属
sessions.json         → key 中含 "agent:<id>" 过滤
```

---

## 一、数据提取规范

### 1.1 Session JSONL 解析

**文件位置**: `~/.openclaw/agents/<agent_id>/sessions/*.jsonl`

```python
def parse_session_jsonl(filepath: str) -> dict:
    """解析单个 Session JSONL 文件"""
    stats = {
        'conversations': 0,
        'tool_calls': [],
        'tool_errors': 0,       # toolResult.is_error=true 计数
        'input_tokens': 0,
        'output_tokens': 0,
        'cache_read': 0,
        'cache_write': 0,
        'models': {},
        'stop_reasons': {},
    }

    with open(filepath, 'r') as f:
        for line in f:
            record = json.loads(line)
            if record.get('type') != 'message':
                continue

            msg = record.get('message', record)
            role = msg.get('role')

            if role == 'user':
                stats['conversations'] += 1
                # 提取 toolResult 错误
                content = msg.get('content', [])
                if isinstance(content, list):
                    for block in content:
                        if block.get('type') == 'toolResult' and block.get('is_error'):
                            stats['tool_errors'] += 1

            if role == 'assistant':
                usage = msg.get('usage', {})
                stats['input_tokens']  += usage.get('input', 0)
                stats['output_tokens'] += usage.get('output', 0)
                stats['cache_read']    += usage.get('cacheRead', 0)
                stats['cache_write']   += usage.get('cacheWrite', 0)

                model = msg.get('model', 'unknown')
                stats['models'][model] = stats['models'].get(model, 0) + 1

                stop = msg.get('stopReason', 'unknown')
                stats['stop_reasons'][stop] = stats['stop_reasons'].get(stop, 0) + 1

                content = msg.get('content', [])
                if isinstance(content, list):
                    for block in content:
                        if block.get('type') == 'toolCall':
                            stats['tool_calls'].append({
                                'name': block.get('name'),
                                'timestamp': record.get('timestamp'),
                            })

    return stats
```

### 1.2 Sessions.json 解析（最新 Session 优先）

**文件位置**: `~/.openclaw/agents/<agent_id>/sessions/sessions.json`

```python
def parse_sessions_index(filepath: str, agent_id: str) -> dict:
    """
    解析 Session 索引。
    同时返回：全局汇总数据 + 最新 Session 单条数据（供状态计算用）。
    """
    with open(filepath) as f:
        data = json.load(f)

    summary = {
        'session_count': 0,
        'compaction_count': 0,
        'cache_read_total': 0,
        'last_active': 0,
    }
    latest_session = None
    latest_updated_at = 0

    for key, session in data.items():
        if f'agent:{agent_id}' not in key:
            continue

        summary['session_count']    += 1
        summary['compaction_count'] += session.get('compactionCount', 0)
        summary['cache_read_total'] += session.get('cacheRead', 0)
        summary['last_active'] = max(summary['last_active'], session.get('updatedAt', 0))

        updated_at = session.get('updatedAt', 0)
        if updated_at > latest_updated_at:
            latest_updated_at = updated_at
            latest_session = session

    # 最新 Session 数据（供 Energy 计算使用）
    if latest_session:
        summary['latest_tokens']        = latest_session.get('totalTokens', 0)
        summary['latest_context_tokens'] = latest_session.get('contextTokens', 200000)
        summary['latest_compaction']    = latest_session.get('compactionCount', 0)
        summary['latest_updated_at']    = latest_updated_at
    else:
        summary['latest_tokens']        = 0
        summary['latest_context_tokens'] = 200000
        summary['latest_compaction']    = 0
        summary['latest_updated_at']    = 0

    return summary
```

### 1.3 Cron Runs 解析

**文件位置**: `~/.openclaw/cron/runs/*.jsonl`

```python
def parse_cron_runs(runs_dir: str, agent_id: str = None) -> dict:
    stats = {
        'total_runs': 0,
        'success_runs': 0,
        'error_runs': 0,
        'total_tokens': 0,
        'total_duration_ms': 0,
        'runs': [],
    }

    for jsonl_file in Path(runs_dir).glob('*.jsonl'):
        with open(jsonl_file) as f:
            for line in f:
                record = json.loads(line)
                if record.get('action') != 'finished':
                    continue
                if agent_id:
                    if f'agent:{agent_id}' not in record.get('sessionKey', ''):
                        continue

                stats['total_runs'] += 1
                if record.get('status') == 'ok':
                    stats['success_runs'] += 1
                else:
                    stats['error_runs'] += 1

                usage = record.get('usage', {})
                stats['total_tokens']      += usage.get('total_tokens', 0)
                stats['total_duration_ms'] += record.get('durationMs', 0)
                stats['runs'].append({
                    'job_id':      record.get('jobId'),
                    'status':      record.get('status'),
                    'duration_ms': record.get('durationMs'),
                    'tokens':      usage.get('total_tokens', 0),
                    'timestamp':   record.get('ts'),
                })

    return stats
```

### 1.4 Cron Jobs 解析

**文件位置**: `~/.openclaw/cron/jobs.json`

```python
def parse_cron_jobs(filepath: str, agent_id: str = None) -> dict:
    with open(filepath) as f:
        data = json.load(f)
    jobs = data.get('jobs', [])
    stats = {'total_jobs': 0, 'enabled_jobs': 0, 'jobs_by_agent': {}}
    for job in jobs:
        if agent_id and job.get('agentId') != agent_id:
            continue
        stats['total_jobs'] += 1
        if job.get('enabled'):
            stats['enabled_jobs'] += 1
        agent = job.get('agentId', 'unknown')
        stats['jobs_by_agent'][agent] = stats['jobs_by_agent'].get(agent, 0) + 1
    return stats
```

### 1.5 Subagent Runs 解析

**文件位置**: `~/.openclaw/subagents/runs.json`

```python
def parse_subagent_runs(filepath: str, agent_id: str = None) -> dict:
    """
    解析协作记录。
    agent_id 过滤规则：同时检查 requesterSessionKey 和 childSessionKey，
    双向匹配，确保 A 派遣 B、以及 A 被 C 派遣 的情形均被记录。
    agent_id=None 时返回全局协作统计（用于协作网络图）。
    """
    with open(filepath) as f:
        data = json.load(f)
    runs = data.get('runs', {})
    stats = {
        'total': 0, 'success': 0, 'error': 0,
        'total_duration_ms': 0,
        'collab_agents': set(),
        'collaborations': [],
    }
    for run_id, run in runs.items():
        if agent_id:
            child_key = run.get('childSessionKey', '')
            requester_key = run.get('requesterSessionKey', '')
            if agent_id not in child_key and agent_id not in requester_key:
                continue
        stats['total'] += 1
        outcome = run.get('outcome', {})
        if outcome.get('status') == 'ok':
            stats['success'] += 1
        else:
            stats['error'] += 1
        started = run.get('startedAt', 0)
        ended   = run.get('endedAt', 0)
        if started and ended:
            stats['total_duration_ms'] += ended - started
        parts = run.get('childSessionKey', '').split(':')
        if len(parts) >= 2:
            stats['collab_agents'].add(parts[1])
        stats['collaborations'].append({
            'task': run.get('task', '')[:100],
            'status': outcome.get('status'),
            'duration_ms': ended - started if started and ended else 0,
        })
    stats['collab_agents'] = list(stats['collab_agents'])
    return stats
```

### 1.6 工作空间扫描

**目录位置**: `~/.openclaw/workspace-<agent_id>/`

```python
import time

def scan_workspace(workspace_dir: str, shared_workspace_dir: str = None) -> dict:
    """
    扫描工作空间，包含 mtime 信息供状态计算使用。
    shared_workspace_dir: ~/.openclaw/workspace/（共享技能目录），可为 None。
    skills_count 包含私有技能 + 共享技能总数。

    返回字段说明：
      skills_count                私有技能 + 共享技能目录数
      memories_count              记忆文件数（memory/*.md）
      memories_words              记忆总字数（所有文件合计）
      has_today_memory             今日是否写记忆（文件名含 YYYY-MM-DD 今日日期）
      recent_memory_count          近7天新增记忆数（mtime 在7天内的文件数）
      learnings_count             LEARNINGS.md 章节数
      recent_learning_words       LEARNINGS.md 7天内修改时取全文字数，否则 0
      errors_count                ERRORS.md 章节数
      feature_requests_count      FEATURE_REQUESTS.md 章节数
      recent_feature_requests     FEATURE_REQUESTS.md 7天内修改时取章节数，否则 0
      memory_sections             MEMORY.md ## 章节数
      memory_words                MEMORY.md 总字数
      last_learning_mtime         四类文件中最新 mtime（unix 秒）
      workspace_completeness      核心文件存在状态字典
      tools_skills_installed      TOOLS.md 中 "✅ 已安装：" 行数
      tools_external_integrations TOOLS.md 中独立 http(s):// 配置块数
      tools_md_updated_days_ago   TOOLS.md 中 "_更新于：YYYY-MM-DD_" 与今日差（无标记取 mtime）
    """
    import datetime as _dt
    workspace = Path(workspace_dir)
    today_str = _dt.date.today().strftime('%Y-%m-%d')

    stats = {
        'skills_count': 0, 'skills': [],
        'memories_count': 0, 'memories_words': 0,
        'has_today_memory': False, 'recent_memory_count': 0,
        'learnings_count': 0, 'recent_learning_words': 0,
        'errors_count': 0,
        'feature_requests_count': 0, 'recent_feature_requests': 0,
        'memory_sections': 0, 'memory_words': 0,
        'last_learning_mtime': 0.0,
        'workspace_completeness': {},
        'tools_skills_installed': 0,
        'tools_external_integrations': 0,
        'tools_md_updated_days_ago': None,
    }

    now = time.time()
    seven_days = 7 * 86400
    mtimes = []

    # ── 私有技能 ─────────────────────────────────────────────────────
    skills_dir = workspace / 'skills'
    if skills_dir.exists():
        for skill in skills_dir.iterdir():
            if skill.is_dir() and (skill / 'SKILL.md').exists():
                stats['skills_count'] += 1
                stats['skills'].append(skill.name)
                try:
                    mtimes.append(skill.stat().st_mtime)
                except Exception:
                    pass

    # ── 共享技能（~/.openclaw/workspace/skills/） ──────────────────
    if shared_workspace_dir:
        shared_skills = Path(shared_workspace_dir) / 'skills'
        if shared_skills.exists():
            for skill in shared_skills.iterdir():
                if skill.is_dir():
                    stats['skills_count'] += 1
                    if skill.name not in stats['skills']:
                        stats['skills'].append(f'[shared]{skill.name}')

    # ── 记忆（memory/*.md） ───────────────────────────────────────
    memory_dir = workspace / 'memory'
    if memory_dir.exists():
        for md in memory_dir.glob('*.md'):
            stats['memories_count'] += 1
            text = md.read_text(errors='ignore')
            stats['memories_words'] += len(text)
            # 今日记忆判定：文件名含今日日期字符串
            if today_str in md.name:
                stats['has_today_memory'] = True
            try:
                mtime = md.stat().st_mtime
                mtimes.append(mtime)
                if now - mtime < seven_days:
                    stats['recent_memory_count'] += 1
            except Exception:
                pass

    # ── 学习记录（.learnings/LEARNINGS.md） ────────────────────────
    learnings_dir = workspace / '.learnings'
    if learnings_dir.exists():
        learnings_md = learnings_dir / 'LEARNINGS.md'
        if learnings_md.exists():
            content = learnings_md.read_text(errors='ignore')
            stats['learnings_count'] = content.count('\n## ') + content.count('\n### ')
            try:
                mtime = learnings_md.stat().st_mtime
                mtimes.append(mtime)
                if now - mtime < seven_days:
                    stats['recent_learning_words'] = len(content)
            except Exception:
                pass

        errors_md = learnings_dir / 'ERRORS.md'
        if errors_md.exists():
            content = errors_md.read_text(errors='ignore')
            stats['errors_count'] = content.count('\n## ') + content.count('\n### ')

        # FEATURE_REQUESTS.md（第三个学习记录文件）
        feature_md = learnings_dir / 'FEATURE_REQUESTS.md'
        if feature_md.exists():
            content = feature_md.read_text(errors='ignore')
            count = content.count('\n## ') + content.count('\n### ')
            stats['feature_requests_count'] = count
            try:
                mtime = feature_md.stat().st_mtime
                mtimes.append(mtime)
                if now - mtime < seven_days:
                    stats['recent_feature_requests'] = count
            except Exception:
                pass

    # ── TOOLS.md（工具清单） ─────────────────────────────────────
    tools_md = workspace / 'TOOLS.md'
    if tools_md.exists():
        content = tools_md.read_text(errors='ignore')
        # 已安装技能数：✅ 已安装：行计数
        stats['tools_skills_installed'] = content.count('✅ 已安装：')
        # 外部集成数：独立 http(s):// 配置块（行首有配置标识符）
        import re as _re
        integrations = set()
        for line in content.splitlines():
            m = _re.search(r'https?://([^\s/]+)', line)
            if m:
                integrations.add(m.group(1))
        stats['tools_external_integrations'] = len(integrations)
        # 更新日期：从 _更新于：YYYY-MM-DD_ 提取
        m = _re.search(r'_更新于[：:]\s*(\d{4}-\d{2}-\d{2})_', content)
        if m:
            import datetime as _dt2
            updated = _dt2.date.fromisoformat(m.group(1))
            stats['tools_md_updated_days_ago'] = (
                _dt2.date.today() - updated
            ).days
        else:
            try:
                mtime = tools_md.stat().st_mtime
                stats['tools_md_updated_days_ago'] = int((now - mtime) / 86400)
            except Exception:
                pass

    # ── MEMORY.md ────────────────────────────────────────────────
    memory_md = workspace / 'MEMORY.md'
    if memory_md.exists():
        content = memory_md.read_text(errors='ignore')
        stats['memory_sections'] = content.count('\n## ')
        stats['memory_words']    = len(content)
        try:
            mtimes.append(memory_md.stat().st_mtime)
        except Exception:
            pass

    # ── 核心文件完整度 ───────────────────────────────────────────
    stats['workspace_completeness'] = {
        'AGENTS.md':   (workspace / 'AGENTS.md').exists(),
        'SOUL.md':     (workspace / 'SOUL.md').exists(),
        'TOOLS.md':    (workspace / 'TOOLS.md').exists(),
        'MEMORY.md':   memory_md.exists(),
        'IDENTITY.md': (workspace / 'IDENTITY.md').exists(),
    }

    stats['last_learning_mtime'] = max(mtimes) if mtimes else 0.0
    return stats
```

### 1.7 共享工作空间扫描

**目录位置**: `~/.openclaw/workspace/`（无 agent_id 前缀，团队主控 Agent 的共享空间）

**归属**: 指标归属于系统中的主控/总指挥 Agent（agent_id 从 `AGENTS.md` 中识别，或使用 `__shared__`）

```python
import re
import json
import time
import datetime

def scan_shared_workspace(shared_dir: str) -> dict:
    """
    扫描共享工作空间，提取团队级指标。
    返回字段：
      heartbeat_hours_ago       距最后一次心跳的小时数（来自 memory/heartbeat-state.json）
      heartbeat_daily_count     今日心跳次数（从 notes 提取 "第 N 次心跳"）
      last_task_hours_ago       距上次任务的小时数（来自 heartbeat-state.json.lastTaskTime）
      projects_active_count     活跃项目数（PROJECT_STATUS.md 状态为 🟡/🟢 的行数）
      tasks_blocked             阻塞任务数（PROJECT_STATUS.md 中 **阻塞**: N 行）
      tasks_overdue             逾期任务数（PROJECT_STATUS.md 中 **逾期**: N 行）
      decisions_count           DECISIONS.md 总决策条数（- ** 行计数）
      recent_decisions_count    近7天新增决策数
      reports_count             reports/ 目录下文件总数
      recent_reports_count      reports/ 目录下近7天新增文件数
      collections_count         collections/ 目录下 .md 文件数
      handoffs_count            handoffs/ 直接子 .md 文件数（不含子目录）
    """
    workspace = Path(shared_dir)
    now = time.time()
    seven_days = 7 * 86400
    today = datetime.date.today()
    stats = {
        'heartbeat_hours_ago': None, 'heartbeat_daily_count': 0,
        'last_task_hours_ago': None,
        'projects_active_count': 0, 'tasks_blocked': 0, 'tasks_overdue': 0,
        'decisions_count': 0, 'recent_decisions_count': 0,
        'reports_count': 0, 'recent_reports_count': 0,
        'collections_count': 0, 'handoffs_count': 0,
    }

    # ── heartbeat-state.json ─────────────────────────────────────
    hb_file = workspace / 'memory' / 'heartbeat-state.json'
    if hb_file.exists():
        try:
            hb = json.loads(hb_file.read_text(errors='ignore'))
            # lastHeartbeat: "2026-03-21T16:28:00+08:00"
            from datetime import datetime as _dt, timezone
            def _parse_iso(s):
                # Python 3.7+ fromisoformat 不支持 +08:00，手动处理
                try:
                    return _dt.fromisoformat(s)
                except ValueError:
                    # 去掉最后 6 位时区
                    return _dt.fromisoformat(s[:-6]).replace(
                        tzinfo=timezone.utc
                    )
            lb = hb.get('lastHeartbeat')
            if lb:
                lb_dt = _parse_iso(lb)
                now_dt = _dt.now(tz=lb_dt.tzinfo or timezone.utc)
                stats['heartbeat_hours_ago'] = round(
                    (now_dt - lb_dt).total_seconds() / 3600, 1
                )
            lt = hb.get('lastTaskTime')
            if lt:
                lt_dt = _parse_iso(lt)
                now_dt = _dt.now(tz=lt_dt.tzinfo or timezone.utc)
                stats['last_task_hours_ago'] = round(
                    (now_dt - lt_dt).total_seconds() / 3600, 1
                )
            notes = hb.get('notes', '')
            m = re.search(r'第\s*(\d+)\s*次心跳', notes)
            if m:
                stats['heartbeat_daily_count'] = int(m.group(1))
        except Exception:
            pass

    # ── PROJECT_STATUS.md ────────────────────────────────────────
    ps_file = workspace / 'PROJECT_STATUS.md'
    if ps_file.exists():
        content = ps_file.read_text(errors='ignore')
        # 活跃项目：表格行含 🟡 或 🟢
        stats['projects_active_count'] = len(
            re.findall(r'\|[^|]*[🟡🟢][^|]*\|', content)
        )
        # 阻塞/逾期：**阻塞**: N 或 **逾期**: N
        m = re.search(r'\*\*阻塞\*\*[：:]\s*(\d+)', content)
        if m: stats['tasks_blocked'] = int(m.group(1))
        m = re.search(r'\*\*逾期\*\*[：:]\s*(\d+)', content)
        if m: stats['tasks_overdue'] = int(m.group(1))

    # ── DECISIONS.md ─────────────────────────────────────────────
    dec_file = workspace / 'DECISIONS.md'
    if dec_file.exists():
        content = dec_file.read_text(errors='ignore')
        # 总决策数：以 "- **" 开头的行
        decisions = re.findall(r'^\s*- \*\*', content, re.MULTILINE)
        stats['decisions_count'] = len(decisions)
        # 近7天：在近7天日期章节下（### YYYY-MM-DD 节点下的决策）
        cutoff = today - datetime.timedelta(days=7)
        current_date = None
        recent = 0
        for line in content.splitlines():
            m = re.match(r'###\s+(\d{4}-\d{2}-\d{2})', line)
            if m:
                current_date = datetime.date.fromisoformat(m.group(1))
            elif current_date and current_date >= cutoff:
                if re.match(r'\s*- \*\*', line):
                    recent += 1
        stats['recent_decisions_count'] = recent

    # ── reports/ ─────────────────────────────────────────────────
    reports_dir = workspace / 'reports'
    if reports_dir.exists():
        for f in reports_dir.iterdir():
            if f.is_file():
                stats['reports_count'] += 1
                try:
                    if now - f.stat().st_mtime < seven_days:
                        stats['recent_reports_count'] += 1
                except Exception:
                    pass

    # ── collections/ ─────────────────────────────────────────────
    coll_dir = workspace / 'collections'
    if coll_dir.exists():
        stats['collections_count'] = sum(
            1 for f in coll_dir.glob('*.md') if f.is_file()
        )

    # ── handoffs/ ────────────────────────────────────────────────
    handoffs_dir = workspace / 'handoffs'
    if handoffs_dir.exists():
        stats['handoffs_count'] = sum(
            1 for f in handoffs_dir.glob('*.md') if f.is_file()
        )

    return stats
```

---

## 二、评分算法

### 2.1 效率分

**数据来源**: sessions/*.jsonl → tokens; cron/runs/*.jsonl → durationMs

```python
def calc_efficiency_score(data: dict) -> int:
    """效率分 = Token效率(40) + 缓存效率(30) + 响应速度(30)"""
    input_tokens  = data.get('input_tokens', 0)
    output_tokens = data.get('output_tokens', 0)
    total_tokens  = data.get('total_tokens', 0)
    cache_read    = data.get('cache_read', 0)
    avg_duration  = data.get('avg_duration_ms', 10000)

    token_score = min(40, (output_tokens / max(input_tokens, 1)) * 80)
    cache_score = min(30, (cache_read / max(total_tokens, 1)) * 50)

    if avg_duration < 5000:
        speed_score = 30
    elif avg_duration < 30000:
        speed_score = 30 - (avg_duration - 5000) / 1000
    else:
        speed_score = 5

    return max(0, min(100, int(token_score + cache_score + speed_score)))
```

### 2.2 产出分

```python
def calc_output_score(data: dict) -> int:
    """产出分 = 输出Token(30) + 任务完成(40) + 工具调用(30)"""
    output_score = min(30, data.get('output_tokens', 0) / 1000)
    tasks = data.get('cron_success', 0) + data.get('collab_success', 0)
    task_score   = min(40, tasks * 2)
    tool_score   = min(30, data.get('tool_calls_count', 0) * 0.5)
    return max(0, min(100, int(output_score + task_score + tool_score)))
```

### 2.3 自动化分

```python
def calc_automation_score(data: dict) -> int:
    """自动化分 = Cron任务数(30) + 执行率(35) + 成功率(35)"""
    enabled_jobs  = data.get('cron_jobs_enabled', 0)
    cron_runs     = data.get('cron_runs', 0)
    cron_expected = data.get('cron_expected', cron_runs) or 1
    cron_success  = data.get('cron_success', 0)

    job_score     = min(30, enabled_jobs * 3)
    exec_score    = min(35, cron_runs / cron_expected * 35)
    success_score = (cron_success / cron_runs * 35) if cron_runs > 0 else 0

    return max(0, min(100, int(job_score + exec_score + success_score)))
```

### 2.4 协作分

```python
def calc_collaboration_score(data: dict) -> int:
    """协作分 = 协作次数(40) + 协作多样性(30) + 成功率(30)"""
    collaborations = data.get('collaborations', 0)
    collab_agents  = data.get('collab_agents_count', 0)
    collab_success = data.get('collab_success', 0)

    collab_score  = min(40, collaborations * 4)
    agent_score   = min(30, collab_agents * 6)
    success_score = (collab_success / collaborations * 30) if collaborations > 0 else 0

    return max(0, min(100, int(collab_score + agent_score + success_score)))
```

### 2.5 积累分

```python
def calc_accumulation_score(data: dict) -> int:
    """积累分 = 技能(25) + 记忆(25) + 学习(25) + MEMORY(25)"""
    skill_score    = min(25, data.get('skills_count', 0) * 2.5)
    memory_score   = min(25, data.get('memories_count', 0) * 0.8)
    learning_score = min(25, data.get('learnings_count', 0) * 2.5)
    section_score  = min(25, data.get('memory_sections', 0) * 2.5)
    return max(0, min(100, int(skill_score + memory_score + learning_score + section_score)))
```

### 2.6 综合评分

```python
def calc_total_score(data: dict) -> int:
    return int(
        calc_efficiency_score(data)    * 0.25 +
        calc_output_score(data)        * 0.25 +
        calc_automation_score(data)    * 0.20 +
        calc_collaboration_score(data) * 0.15 +
        calc_accumulation_score(data)  * 0.15
    )
```

---

## 三、XP 系统

### 3.1 XP 计算

```python
def calc_daily_xp(data: dict, yesterday_data: dict = None) -> int:
    xp = 0
    xp += data.get('conversations', 0)        * 1
    xp += data.get('tool_calls_count', 0)     * 2
    xp += data.get('cron_success', 0)         * 10
    xp += data.get('collab_success', 0)       * 20
    if yesterday_data:
        new_skills = max(0, data.get('skills_count', 0) - yesterday_data.get('skills_count', 0))
        xp += new_skills * 30
        new_learnings = max(0, data.get('learnings_count', 0) - yesterday_data.get('learnings_count', 0))
        xp += new_learnings * 10
    if data.get('has_today_memory', False):
        xp += 5
    return xp
```

### 3.2 等级计算

```python
LEVEL_THRESHOLDS = [
    (1, 0), (2, 100), (3, 250), (4, 450), (5, 700),
    (6, 1000), (7, 1400), (8, 1900), (9, 2500), (10, 3200),
    (11, 4000), (12, 5000), (13, 6200), (14, 7600), (15, 9200),
    (16, 11000), (17, 13000), (18, 15500), (19, 18500), (20, 22000),
    (21, 26000),
]

def calc_level(total_xp: int) -> tuple:
    level = 1
    for lv, threshold in LEVEL_THRESHOLDS:
        if total_xp >= threshold:
            level = lv
        else:
            break
    stage = (
        'baby'    if level <= 5  else
        'growing' if level <= 10 else
        'mature'  if level <= 15 else
        'expert'  if level <= 20 else
        'legend'
    )
    current_threshold = LEVEL_THRESHOLDS[level - 1][1]
    if level < len(LEVEL_THRESHOLDS):
        next_threshold = LEVEL_THRESHOLDS[level][1]
        progress = (total_xp - current_threshold) / (next_threshold - current_threshold) * 100
    else:
        progress = 100
    return level, stage, int(progress)
```

---

## 四、状态系统

### 4.1 辅助函数

#### 时间衰减加权 stop_reason 统计

```python
import math

def weighted_stop_reasons(events: list, decay_hours: float = 12.0) -> dict:
    """
    对 stop_reason 事件列表做指数时间衰减加权。
    越近的事件权重越高，半衰期 = decay_hours。
    events: [(unix_timestamp, stop_reason), ...]
    """
    now = time.time()
    good, bad = 0.0, 0.0
    for ts, stop_reason in events:
        hours_ago = (now - ts) / 3600
        weight = math.exp(-hours_ago / decay_hours)
        if stop_reason in ('stop', 'end_turn', 'tool_use'):
            good += weight
        elif stop_reason in ('max_tokens', 'error', 'timeout'):
            bad += weight
    total = good + bad
    return {'good': good, 'bad': bad, 'total': total}
```

#### 近期 stop_reason 从 JSONL 提取

```python
def get_recent_stop_reasons(agent_id: str, hours: float, with_timestamps: bool = False):
    """
    从 sessions/*.jsonl 提取近 hours 小时内的 stop_reason 事件。
    返回事件列表：[(timestamp, stop_reason), ...]
    """
    from config import AGENTS_DIR
    session_dir = AGENTS_DIR / agent_id / 'sessions'
    if not session_dir.exists():
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    events = []

    for fp in session_dir.glob('*.jsonl'):
        try:
            with fp.open('r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    item = json.loads(line)
                    if item.get('type') != 'message':
                        continue
                    msg = item.get('message', item)
                    if msg.get('role') != 'assistant':
                        continue
                    stop = msg.get('stopReason', '')
                    if not stop:
                        continue
                    ts_str = item.get('timestamp', '')
                    ts = None
                    if ts_str:
                        try:
                            ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                            if ts < cutoff:
                                continue
                        except Exception:
                            pass
                    unix_ts = ts.timestamp() if ts else time.time()
                    events.append((unix_ts, stop))
        except Exception:
            continue

    return events
```

#### 工具类别探索广度

```python
TOOL_CATEGORIES = {
    'file': ['read', 'write', 'edit'],
    'exec': ['exec', 'process'],
    'search': ['web_search', 'web_fetch'],
    'browser': ['browser'],
    'nodes': ['nodes'],
    'message': ['message', 'tts'],
    'session': ['sessions_list', 'sessions_send', 'sessions_spawn',
                'sessions_history', 'subagents', 'agents_list'],
    'media': ['image', 'pdf', 'canvas'],
    'system': ['session_status'],
}
TOTAL_CATEGORIES = len(TOOL_CATEGORIES)  # 9

def get_recent_tool_category_count(agent_id: str, days: int = 7) -> int:
    """统计近 days 天内使用过的不同工具类别数"""
    from config import AGENTS_DIR
    session_dir = AGENTS_DIR / agent_id / 'sessions'
    if not session_dir.exists():
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    used_categories = set()
    for fp in session_dir.glob('*.jsonl'):
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
                            ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                            if ts < cutoff:
                                continue
                        except Exception:
                            pass
                    msg = item.get('message', item)
                    for block in msg.get('content', []):
                        if block.get('type') == 'toolCall':
                            name = block.get('name', '')
                            for cat, tools in TOOL_CATEGORIES.items():
                                if name in tools:
                                    used_categories.add(cat)
                                    break
        except Exception:
            continue
    return len(used_categories)
```

---

### 4.2 四状态计算

```python
import time
import math

def clamp(v: float, lo: float = 0, hi: float = 100) -> float:
    return round(max(lo, min(hi, v)), 2)

def calc_status(agent_id: str, workspace_stats: dict, db,
                prev_status: dict = None) -> dict:
    """
    计算四个状态值，范围 0-100。
    workspace_stats: scan_workspace() 的返回值
    prev_status: 上次存储的状态（用于 EMA 平滑），可为 None
    """

    # ══════════════════════════════════════════════════════════════════
    # 1. Energy：工作负荷综合评估
    #    上下文剩余(50%) + 压缩疲惫(30%) + Session新鲜度(20%)
    # ══════════════════════════════════════════════════════════════════
    current_tokens  = workspace_stats.get('latest_tokens', 0)
    context_tokens  = workspace_stats.get('latest_context_tokens', 200000)
    compaction      = workspace_stats.get('latest_compaction', 0)
    latest_updated  = workspace_stats.get('latest_updated_at', 0)

    context_remaining = clamp(100 - current_tokens / max(context_tokens, 1) * 100)
    compaction_score  = clamp(100 - compaction * 15)   # 每压缩1次扣15分

    session_age_h = (time.time() - latest_updated / 1000) / 3600 if latest_updated else 99
    freshness_score = clamp(max(5, 100 - max(0, session_age_h - 8) * 3))

    energy = clamp(
        context_remaining * 0.5 +
        compaction_score  * 0.3 +
        freshness_score   * 0.2
    )

    # ══════════════════════════════════════════════════════════════════
    # 2. Health：综合任务完成质量（近7天）
    #    Cron质量(40%) + 工具健康(35%) + 错误日志趋势(25%)
    # ══════════════════════════════════════════════════════════════════
    # Cron 成功率（近7天，从数据库）
    cron_row = db.execute("""
        SELECT COUNT(*) as runs,
               SUM(CASE WHEN status='ok' THEN 1 ELSE 0 END) as success
        FROM cron_run_logs
        WHERE agent_id=? AND run_time >= datetime('now','-7 days')
    """, (agent_id,)).fetchone()
    cron_runs    = cron_row['runs']    or 0
    cron_success = cron_row['success'] or 0

    # 工具健康：近7天 tool_call_logs 中的错误率
    tool_row = db.execute("""
        SELECT COUNT(*) as total,
               SUM(CASE WHEN is_error=1 THEN 1 ELSE 0 END) as errors
        FROM tool_call_logs
        WHERE agent_id=? AND call_time >= datetime('now','-7 days')
    """, (agent_id,)).fetchone()
    tool_total  = tool_row['total']  or 0
    tool_errors = tool_row['errors'] or 0
    tool_health = clamp((1 - tool_errors / max(tool_total, 1)) * 100)

    # 错误日志趋势：workspace ERRORS.md 近期新增条目
    recent_error_entries = workspace_stats.get('errors_count', 0)
    error_trend_score = clamp(100 - recent_error_entries * 10)

    if cron_runs > 0:
        cron_quality = cron_success / cron_runs * 100
        health = clamp(cron_quality * 0.4 + tool_health * 0.35 + error_trend_score * 0.25)
    else:
        # 无 Cron：工具健康 + 错误趋势，不给默认满分
        health = clamp(tool_health * 0.6 + error_trend_score * 0.4)

    # ══════════════════════════════════════════════════════════════════
    # 3. Mood：近期交互质量与活跃状态（近24小时）
    #    交互质量(40%) + 近期活跃度(30%) + 产出丰富度(30%)
    # ══════════════════════════════════════════════════════════════════
    # 交互质量：时间衰减加权 stop_reason（近24h）
    events_24h = get_recent_stop_reasons(agent_id, hours=24)
    if events_24h:
        sr = weighted_stop_reasons(events_24h, decay_hours=12)
        interaction_quality = clamp(sr['good'] / sr['total'] * 100) if sr['total'] > 0 else 85
    else:
        interaction_quality = 85.0

    # 近期活跃度：今日对话数 vs 7日日均
    today_convs_row = db.execute("""
        SELECT COUNT(DISTINCT session_id) as cnt
        FROM tool_call_logs
        WHERE agent_id=? AND date(call_time)=date('now')
    """, (agent_id,)).fetchone()
    today_convs = today_convs_row['cnt'] or 0

    weekly_avg_row = db.execute("""
        SELECT COUNT(DISTINCT session_id) * 1.0 / 7 as avg
        FROM tool_call_logs
        WHERE agent_id=? AND call_time >= datetime('now','-7 days')
    """, (agent_id,)).fetchone()
    weekly_avg = weekly_avg_row['avg'] or 1.0
    activity_ratio = today_convs / max(weekly_avg, 1)
    activity_score = clamp(activity_ratio * 60 + 20)  # 均值=80，无活动=20

    # 产出丰富度：近24h output/input token 比
    token_row = db.execute("""
        SELECT SUM(input_tokens) as inp, SUM(output_tokens) as out
        FROM tool_call_logs
        WHERE agent_id=? AND call_time >= datetime('now','-1 day')
    """, (agent_id,)).fetchone()
    inp = token_row['inp'] or 0
    out = token_row['out'] or 0
    output_richness = clamp((out / max(inp, 1)) * 150)

    mood = clamp(
        interaction_quality * 0.4 +
        activity_score      * 0.3 +
        output_richness     * 0.3
    )

    # ══════════════════════════════════════════════════════════════════
    # 4. Hunger：知识新鲜度与探索欲
    #    时间新鲜度(50%) + 学习深度趋势(30%) + 工具探索广度(20%)
    # ══════════════════════════════════════════════════════════════════
    last_mtime = workspace_stats.get('last_learning_mtime', 0.0)
    if last_mtime > 0:
        hours_since = max(0, (time.time() - last_mtime) / 3600)
        time_freshness = clamp(100 - hours_since * 2)
    else:
        time_freshness = 0.0

    # 学习深度趋势：近7天字数 vs 历史均值
    recent_words = workspace_stats.get('recent_learning_words', 0)
    hist_row = db.execute("""
        SELECT AVG(learnings_words) as avg
        FROM daily_snapshots
        WHERE agent_id=? AND date >= date('now','-30 days')
    """, (agent_id,)).fetchone()
    baseline_words = (hist_row['avg'] or 0) if hist_row else 0
    if baseline_words > 0:
        depth_ratio = recent_words / baseline_words
        depth_score = clamp(depth_ratio * 70 + 15)
    else:
        depth_score = 50.0  # 无历史基线时中性值

    # 工具探索广度：近7天工具类别数
    tool_cat_count = get_recent_tool_category_count(agent_id, days=7)
    breadth_score = clamp(tool_cat_count / TOTAL_CATEGORIES * 100)

    hunger = clamp(
        time_freshness * 0.5 +
        depth_score    * 0.3 +
        breadth_score  * 0.2
    )

    # ══════════════════════════════════════════════════════════════════
    # 5. 状态联动修正
    # ══════════════════════════════════════════════════════════════════
    # 能量低时心情打折（疲惫会影响心情）
    if energy < 30:
        mood = clamp(mood * 0.85)

    # 长期饥饿影响健康（超过72小时不学习）
    hours_since_any = (time.time() - last_mtime) / 3600 if last_mtime > 0 else 999
    if hunger < 20 and hours_since_any > 72:
        health = clamp(health * 0.90)

    # ══════════════════════════════════════════════════════════════════
    # 6. EMA 平滑（防止单次失败导致状态剧烈跳变）
    # ══════════════════════════════════════════════════════════════════
    ALPHA = 0.3
    if prev_status:
        energy = clamp(ALPHA * energy + (1 - ALPHA) * prev_status.get('energy', energy))
        health = clamp(ALPHA * health + (1 - ALPHA) * prev_status.get('health', health))
        mood   = clamp(ALPHA * mood   + (1 - ALPHA) * prev_status.get('mood',   mood))
        hunger = clamp(ALPHA * hunger + (1 - ALPHA) * prev_status.get('hunger', hunger))

    return {
        'energy': energy,
        'health': health,
        'mood':   mood,
        'hunger': hunger,
    }
```

---

### 4.3 状态到龙虾表情映射

```python
def get_claw_state(status: dict) -> str:
    """根据四状态按优先级返回龙虾表情状态"""
    energy = status['energy']
    health = status['health']
    mood   = status['mood']
    hunger = status['hunger']
    avg    = (energy + health + mood + hunger) / 4

    if health < 30:                return 'sick'       # 🤒 任务频繁失败
    if energy < 15:                return 'tired'      # 😴 上下文接近满载
    if hunger < 20:                return 'hungry'     # 🍽️ 超过40小时未学习
    if mood < 30:                  return 'sad'        # 😢 近24h多次异常中断
    if avg >= 85 and energy >= 65: return 'energetic'  # ⭐ 全面亢奋
    if avg >= 65:                  return 'happy'      # 😊 整体良好
    if avg >= 35:                  return 'normal'     # 🦞 普通状态
    return 'tired'                                     # 😴 四维全低兜底
```

### 4.4 龙虾颜色映射

颜色基于四状态平均值，与表情状态独立计算，反映「整体健康程度」。

```python
# 五档离散颜色（用于 ESP32、状态标签等低精度场景）
CRAYFISH_COLORS = [
    (80, '#E84B3A', 'red',    'Excellent!'),  # 原色赤红
    (60, '#F5A623', 'orange', 'Good'),         # 橙黄色
    (40, '#4DB8A4', 'teal',   'Normal'),       # 蓝绿色
    (20, '#5B9BD5', 'blue',   'Tired'),        # 青蓝色
    ( 0, '#9B5DE5', 'purple', 'Danger!'),      # 紫红色
]

def get_claw_color(status: dict) -> dict:
    """
    根据四状态平均值返回龙虾颜色信息。
    与 get_claw_state() 独立运行，两套系统互补：
      - get_claw_state() → 优先级诊断（哪个维度出问题）
      - get_claw_color() → 整体健康仪表盘（好不好）
    """
    avg = (status['energy'] + status['health'] +
           status['mood'] + status['hunger']) / 4

    for threshold, hex_color, name, label in CRAYFISH_COLORS:
        if avg >= threshold:
            return {
                'avg':      round(avg, 2),
                'hex':      hex_color,
                'name':     name,
                'label':    label,
                'threshold': threshold,
            }
    # avg < 0 兜底（理论上不会触发）
    return {'avg': round(avg, 2), 'hex': '#9B5DE5',
            'name': 'purple', 'label': 'Danger!', 'threshold': 0}


def get_claw_color_smooth(status: dict) -> str:
    """
    连续平滑颜色插值（用于 Web 前端 SVG 渲染）。
    在相邻两档颜色之间按 avg 线性插值，返回 hex 字符串。
    """
    avg = (status['energy'] + status['health'] +
           status['mood'] + status['hunger']) / 4
    avg = max(0, min(100, avg))

    # 找到所在区间
    thresholds = [(t, h) for t, h, _, _ in CRAYFISH_COLORS]
    for i in range(len(thresholds) - 1):
        t_hi, hex_hi = thresholds[i]
        t_lo, hex_lo = thresholds[i + 1]
        if avg >= t_lo:
            # 在 [t_lo, t_hi] 区间内线性插值
            ratio = (avg - t_lo) / (t_hi - t_lo) if t_hi != t_lo else 1.0
            return _lerp_hex(hex_lo, hex_hi, ratio)

    return thresholds[-1][1]  # 最低档兜底


def _lerp_hex(hex_a: str, hex_b: str, t: float) -> str:
    """在两个 hex 颜色间线性插值，t=0 → hex_a，t=1 → hex_b"""
    def parse(h):
        h = h.lstrip('#')
        return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))
    ra, ga, ba = parse(hex_a)
    rb, gb, bb = parse(hex_b)
    r = int(ra + (rb - ra) * t)
    g = int(ga + (gb - ga) * t)
    b = int(ba + (bb - ba) * t)
    return f'#{r:02X}{g:02X}{b:02X}'
```

**两套系统协作示例：**

```python
status = {'energy': 5, 'health': 90, 'mood': 90, 'hunger': 90}

state = get_claw_state(status)   # → 'tired'（energy 触发优先级2）
color = get_claw_color(status)   # → {'hex': '#F5A623', 'label': 'Good', 'avg': 68.75}

# 传达：上下文快满了，但整体状态还不错
```

| avg 区间 | 颜色 | Hex | 标签 | 语义 |
|----------|------|-----|------|------|
| ≥ 80 | 赤红 | `#E84B3A` | Excellent! | 龙虾原色，精力充沛 |
| ≥ 60 | 橙黄 | `#F5A623` | Good | 状态良好 |
| ≥ 40 | 蓝绿 | `#4DB8A4` | Normal | 正常运转 |
| ≥ 20 | 青蓝 | `#5B9BD5` | Tired | 开始疲惫 |
| < 20 | 紫红 | `#9B5DE5` | Danger! | 全面告警 |

### 4.5 各状态含义速查

| 状态 | 表情 | 触发条件 | 建议行动 |
|------|------|---------|---------|
| sick | 🤒 | health < 30 | 检查 Cron 报错 / 工具错误 |
| tired | 😴 | energy < 15 或 avg < 35 | 开新 Session / 休息 |
| hungry | 🍽️ | hunger < 20（约40h未学习）| 写记忆、学习、探索新工具 |
| sad | 😢 | mood < 30 | 检查 max_tokens / error 原因 |
| energetic | ⭐ | avg ≥ 85 且 energy ≥ 65 | 状态极佳，正常工作 |
| happy | 😊 | avg ≥ 65 | 状态良好 |
| normal | 🦞 | avg 35-64 | 正常工作 |

---

## 五、工具使用分析

### 5.1 工具分类统计

```python
def categorize_tools(tool_calls: list) -> dict:
    stats = {cat: 0 for cat in TOOL_CATEGORIES}
    stats['other'] = 0
    for call in tool_calls:
        tool_name = call.get('name', '')
        categorized = False
        for category, tools in TOOL_CATEGORIES.items():
            if tool_name in tools:
                stats[category] += 1
                categorized = True
                break
        if not categorized:
            stats['other'] += 1
    return stats
```

### 5.2 工具多样性指标

```python
def calc_tool_diversity(tool_calls: list) -> float:
    """工具多样性 = 使用的不同工具数 / 总调用数，范围 0-1"""
    if not tool_calls:
        return 0
    unique_tools = set(call.get('name') for call in tool_calls)
    return round(len(unique_tools) / len(tool_calls), 3)
```

---

## 六、协作网络分析

```python
def build_collaboration_graph(subagent_runs: dict) -> dict:
    graph = {'nodes': set(), 'edges': []}
    for run_id, run in subagent_runs.get('runs', {}).items():
        requester = extract_agent_id(run.get('requesterSessionKey', ''))
        child     = extract_agent_id(run.get('childSessionKey', ''))
        if requester and child:
            graph['nodes'].add(requester)
            graph['nodes'].add(child)
            graph['edges'].append({
                'from': requester,
                'to': child,
                'success': run.get('outcome', {}).get('status') == 'ok',
            })
    graph['nodes'] = list(graph['nodes'])
    return graph

def extract_agent_id(session_key: str) -> str:
    """从 session key 提取 agent_id，格式: agent:<id>:xxx"""
    parts = session_key.split(':')
    if len(parts) >= 2 and parts[0] == 'agent':
        return parts[1]
    return None
```

---

## 七、采集调度

### 7.0 多 Agent 调度入口

所有采集和快照操作均以 `discover_agents()` 为起点，按 agent_id 逐个处理：

```python
def run_all_agents_collection(db):
    """每小时：采集所有 Agent 的增量数据"""
    agent_ids = discover_agents()
    results = []
    for agent_id in agent_ids:
        try:
            result = hourly_collect(agent_id, db)
            results.append({'agent_id': agent_id, 'ok': True, **result})
        except Exception as e:
            results.append({'agent_id': agent_id, 'ok': False, 'error': str(e)})
    return results


def run_all_agents_snapshot(db):
    """每日 00:05：为所有 Agent 生成快照"""
    agent_ids = discover_agents()
    for agent_id in agent_ids:
        try:
            daily_snapshot(agent_id, db)
        except Exception as e:
            log_error(f'snapshot failed for {agent_id}: {e}')
```

**新增 Agent 无需配置**：只要 `agents/` 下新建了目录，下次采集时自动被纳入。

---

### 7.1 增量采集

```python
class IncrementalCollector:
    def __init__(self, state_file: str):
        self.state_file = state_file
        self.state = self._load_state()

    def _load_state(self) -> dict:
        if os.path.exists(self.state_file):
            with open(self.state_file) as f:
                return json.load(f)
        return {'session_offsets': {}, 'cron_offsets': {}}

    def _save_state(self):
        with open(self.state_file, 'w') as f:
            json.dump(self.state, f)

    def collect_session_incremental(self, filepath: str) -> dict:
        offset = self.state['session_offsets'].get(filepath, 0)
        stats = {'new_lines': 0, 'tool_calls': [], 'tool_errors': 0, 'stop_reasons': {}}
        with open(filepath, 'r') as f:
            f.seek(offset)
            for line in f:
                # 解析新行（tool_calls + tool_errors + stop_reasons）
                stats['new_lines'] += 1
            new_offset = f.tell()
        self.state['session_offsets'][filepath] = new_offset
        self._save_state()
        return stats
```

### 7.2 每日快照

```python
def generate_daily_snapshot(agent_id: str, db) -> dict:
    sessions   = collect_sessions(agent_id)
    cron       = collect_cron(agent_id)
    subagents  = collect_subagents(agent_id)
    workspace  = scan_workspace(get_workspace_dir(agent_id))

    data = {**sessions, **cron, **subagents, **workspace}

    scores = {
        'efficiency':    calc_efficiency_score(data),
        'output':        calc_output_score(data),
        'automation':    calc_automation_score(data),
        'collaboration': calc_collaboration_score(data),
        'accumulation':  calc_accumulation_score(data),
    }
    scores['total'] = calc_total_score(data)

    yesterday  = get_yesterday_snapshot(agent_id, db)
    xp_gained  = calc_daily_xp(data, yesterday)

    prev_status = get_prev_status(agent_id, db)
    status = calc_status(agent_id, workspace, db, prev_status)

    return {
        'agent_id':  agent_id,
        'date':      datetime.now().strftime('%Y-%m-%d'),
        'raw_data':  data,
        'scores':    scores,
        'xp_gained': xp_gained,
        'status':    status,
    }
```

---

## 八、指标验证清单

| 指标 | 数据文件 | 字段路径 | 验证命令 |
|------|---------|---------|---------|
| 对话轮次 | sessions/*.jsonl | `type=message, role=user` | `grep -c '"role":"user"'` |
| 工具调用 | sessions/*.jsonl | `content[].type=toolCall` | `grep -c 'toolCall'` |
| 工具报错 | sessions/*.jsonl | `content[].type=toolResult, is_error=true` | `grep -c 'is_error.*true'` |
| 输入Token | sessions/*.jsonl | `usage.input` | `jq '.message.usage.input'` |
| 输出Token | sessions/*.jsonl | `usage.output` | `jq '.message.usage.output'` |
| 缓存命中 | sessions/*.jsonl | `usage.cacheRead` | `jq '.message.usage.cacheRead'` |
| 当前Session Token | sessions.json | 最新条目 `totalTokens` | `jq 'to_entries | max_by(.value.updatedAt) | .value.totalTokens'` |
| 压缩次数 | sessions.json | 最新条目 `compactionCount` | `jq 'to_entries | max_by(.value.updatedAt) | .value.compactionCount'` |
| Cron任务数 | jobs.json | `jobs.length` | `jq '.jobs | length'` |
| Cron执行 | runs/*.jsonl | `action=finished` | `grep -c 'finished'` |
| 协作次数 | subagents/runs.json | `runs.length` | `jq '.runs | length'` |
| 技能数 | workspace/skills/ | 目录计数 | `ls -d skills/*/ | wc -l` |
| 记忆数 | workspace/memory/ | 文件计数 | `ls memory/*.md | wc -l` |
| 错误条目 | workspace/.learnings/ERRORS.md | `## ` 计数 | `grep -c '^## ' ERRORS.md` |

---

## 九、数据库写入逻辑

### 9.1 每小时采集写入

```python
def hourly_collect(agent_id: str, db):
    cursor = db.execute(
        "SELECT session_offsets, cron_offsets FROM collection_state WHERE agent_id=?",
        (agent_id,)
    )
    row = cursor.fetchone()
    session_offsets = json.loads(row[0]) if row else {}
    cron_offsets    = json.loads(row[1]) if row else {}

    for filepath in get_session_files(agent_id):
        offset = session_offsets.get(filepath, 0)
        tool_calls, new_offset = parse_session_incremental(filepath, offset)
        for call in tool_calls:
            db.execute("""
                INSERT INTO tool_call_logs
                (agent_id, session_id, tool_name, tool_category,
                 input_tokens, output_tokens, cache_read,
                 stop_reason, is_error, call_time)
                VALUES (?,?,?,?,?,?,?,?,?,?)
            """, (
                agent_id, call['session_id'], call['tool_name'],
                categorize_tool(call['tool_name']),
                call['input_tokens'], call['output_tokens'], call['cache_read'],
                call.get('stop_reason'), call.get('is_error', False),
                call['timestamp']
            ))
        session_offsets[filepath] = new_offset

    for filepath in get_cron_files(agent_id):
        offset = cron_offsets.get(filepath, 0)
        runs, new_offset = parse_cron_incremental(filepath, offset, agent_id)
        for run in runs:
            db.execute("""
                INSERT INTO cron_run_logs
                (agent_id, job_id, job_name, status, error_message,
                 duration_ms, input_tokens, output_tokens, total_tokens,
                 model, provider, run_time)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                agent_id, run['job_id'], run.get('job_name'),
                run['status'], run.get('error'),
                run['duration_ms'], run['input_tokens'],
                run['output_tokens'], run['total_tokens'],
                run['model'], run['provider'], run['timestamp']
            ))
        cron_offsets[filepath] = new_offset

    db.execute("""
        INSERT OR REPLACE INTO collection_state
        (agent_id, session_offsets, cron_offsets, last_collected_at)
        VALUES (?,?,?,datetime('now'))
    """, (agent_id, json.dumps(session_offsets), json.dumps(cron_offsets)))
    db.commit()
```

### 9.2 每日快照写入

```python
def daily_snapshot(agent_id: str, db):
    target_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

    tool_stats = dict(db.execute("""
        SELECT COUNT(*) as tool_calls,
               COUNT(DISTINCT tool_name) as unique_tools,
               SUM(input_tokens) as input_tokens,
               SUM(output_tokens) as output_tokens,
               SUM(cache_read) as cache_read,
               SUM(is_error) as tool_errors
        FROM tool_call_logs
        WHERE agent_id=? AND date(call_time)=?
    """, (agent_id, target_date)).fetchone())

    cron_stats = dict(db.execute("""
        SELECT COUNT(*) as cron_runs,
               SUM(CASE WHEN status='ok' THEN 1 ELSE 0 END) as cron_success,
               AVG(duration_ms) as avg_duration
        FROM cron_run_logs
        WHERE agent_id=? AND date(run_time)=?
    """, (agent_id, target_date)).fetchone())

    workspace_stats = scan_workspace(get_workspace_dir(agent_id))
    data = {**tool_stats, **cron_stats, **workspace_stats}

    scores = {k: fn(data) for k, fn in [
        ('efficiency',    calc_efficiency_score),
        ('output',        calc_output_score),
        ('automation',    calc_automation_score),
        ('collaboration', calc_collaboration_score),
        ('accumulation',  calc_accumulation_score),
    ]}
    scores['total'] = calc_total_score(data)

    xp_gained = calc_daily_xp(data, get_yesterday_snapshot(agent_id, db))

    prev_status = get_prev_status(agent_id, db)
    status = calc_status(agent_id, workspace_stats, db, prev_status)

    db.execute("""
        INSERT INTO daily_snapshots
        (agent_id, date, conversations, tool_calls, tool_errors,
         input_tokens, output_tokens, cache_read,
         cron_runs, cron_success, collaborations, collab_success,
         skills_count, memories_count, learnings_count,
         efficiency_score, output_score, automation_score,
         collaboration_score, accumulation_score, total_score, xp_gained)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        agent_id, target_date,
        data.get('conversations', 0), data.get('tool_calls', 0), data.get('tool_errors', 0),
        data.get('input_tokens', 0),  data.get('output_tokens', 0), data.get('cache_read', 0),
        data.get('cron_runs', 0),     data.get('cron_success', 0),
        data.get('collaborations', 0), data.get('collab_success', 0),
        data.get('skills_count', 0),  data.get('memories_count', 0), data.get('learnings_count', 0),
        scores['efficiency'], scores['output'], scores['automation'],
        scores['collaboration'], scores['accumulation'], scores['total'], xp_gained
    ))

    cursor = db.execute("SELECT total_xp FROM agent_profiles WHERE agent_id=?", (agent_id,))
    row = cursor.fetchone()
    total_xp = (row[0] if row else 0) + xp_gained
    level, stage, _ = calc_level(total_xp)

    db.execute("""
        INSERT OR REPLACE INTO agent_profiles
        (agent_id, level, total_xp, stage,
         efficiency_score, output_score, automation_score,
         collaboration_score, accumulation_score, total_score,
         energy, health, mood, hunger, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'))
    """, (
        agent_id, level, total_xp, stage,
        scores['efficiency'], scores['output'], scores['automation'],
        scores['collaboration'], scores['accumulation'], scores['total'],
        status['energy'], status['health'], status['mood'], status['hunger']
    ))

    check_and_unlock_achievements(agent_id, data, db)
    db.commit()
```

### 9.3 每周清理

```python
def weekly_cleanup(db):
    db.execute("DELETE FROM tool_call_logs WHERE call_time < datetime('now','-90 days')")
    db.execute("DELETE FROM cron_run_logs  WHERE run_time  < datetime('now','-90 days')")
    db.execute("VACUUM")
    db.commit()
```

---

_ClawGrowth | 采集即存储，每个变量都有明确数据来源和入库逻辑_
