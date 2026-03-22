# ClawGrowth 数据库设计

> **Version**: 3.1  
> **数据库**: SQLite  
> **文件位置**: `~/.openclaw/clawgrowth/clawgrowth.db`  
> **表数量**: 6 张

---

## 一、设计原则

1. **采集即存储** - 从原生数据采集后立即入库
2. **独立于原生** - 不依赖 OpenClaw 原生文件的持续存在
3. **可追溯** - 保留详细日志，支持历史分析

---

## 二、6 张表总览

| 表 | 用途 | 写入时机 | 保留策略 |
|----|------|---------|---------|
| **agent_profiles** | Agent 当前状态 | 每日更新 | 永久 |
| **daily_snapshots** | 每日汇总快照 | 每日写入 | 永久 |
| **tool_call_logs** | 工具调用日志 | 每小时采集 | 90天 |
| **cron_run_logs** | Cron 执行日志 | 每小时采集 | 90天 |
| **collection_state** | 采集进度 | 每小时更新 | 永久 |
| **achievements** | 成就记录 | 达成时写入 | 永久 |

---

## 三、表结构详细设计

### 3.1 agent_profiles（Agent 档案）

**用途**: 存储每个 Agent 的当前状态

**写入时机**: 每日 00:05 UPDATE

```sql
CREATE TABLE agent_profiles (
    agent_id TEXT PRIMARY KEY,
    
    -- 成长
    level INTEGER DEFAULT 1,
    total_xp INTEGER DEFAULT 0,
    stage TEXT DEFAULT 'baby',
    
    -- 五维评分
    efficiency_score INTEGER DEFAULT 50,
    output_score INTEGER DEFAULT 50,
    automation_score INTEGER DEFAULT 50,
    collaboration_score INTEGER DEFAULT 50,
    accumulation_score INTEGER DEFAULT 50,
    total_score INTEGER DEFAULT 50,
    
    -- 四状态
    energy INTEGER DEFAULT 100,
    health INTEGER DEFAULT 100,
    mood INTEGER DEFAULT 80,
    hunger INTEGER DEFAULT 50,
    
    -- 时间戳
    initialized_at TEXT,
    updated_at TEXT DEFAULT (datetime('now'))
);
```

---

### 3.2 daily_snapshots（每日快照）

**用途**: 每日汇总数据，用于成长曲线

**写入时机**: 每日 00:05 INSERT

```sql
CREATE TABLE daily_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id TEXT NOT NULL,
    date TEXT NOT NULL,  -- YYYY-MM-DD
    
    -- 汇总指标（从日志表聚合）
    conversations INTEGER DEFAULT 0,
    tool_calls INTEGER DEFAULT 0,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    cache_read INTEGER DEFAULT 0,
    cron_runs INTEGER DEFAULT 0,
    cron_success INTEGER DEFAULT 0,
    collaborations INTEGER DEFAULT 0,
    collab_success INTEGER DEFAULT 0,
    skills_count INTEGER DEFAULT 0,
    -- memory 相关
    memories_count INTEGER DEFAULT 0,
    memories_words INTEGER DEFAULT 0,       -- 记忆总字数
    has_today_memory INTEGER DEFAULT 0,      -- 当日是否写记忆（0/1）
    recent_memory_count INTEGER DEFAULT 0,   -- 近7天新增记忆数
    learnings_count INTEGER DEFAULT 0,
    learnings_words INTEGER DEFAULT 0,      -- 近7天学习字数（供 Hunger 深度趋势）
    errors_count INTEGER DEFAULT 0,         -- ERRORS.md 章节数
    feature_requests_count INTEGER DEFAULT 0,  -- FEATURE_REQUESTS.md 章节数
    recent_feature_requests INTEGER DEFAULT 0, -- 近7天功能请求数
    memory_sections INTEGER DEFAULT 0,
    memory_words INTEGER DEFAULT 0,         -- MEMORY.md 总字数
    -- TOOLS.md 指标
    tools_skills_installed INTEGER DEFAULT 0,      -- ✅ 已安装 行数
    tools_external_integrations INTEGER DEFAULT 0, -- 外部 http(s):// 集成数
    tools_md_updated_days_ago INTEGER,             -- TOOLS.md 距今天数（NULL=未知）
    -- 共享工作空间团队指标（agent_id='__shared__' 或主控 agent）
    heartbeat_hours_ago REAL,               -- 心跳距今小时数
    heartbeat_daily_count INTEGER DEFAULT 0,-- 今日心跳次数
    last_task_hours_ago REAL,               -- 上次任务距今小时数
    projects_active_count INTEGER DEFAULT 0,-- 活跃项目数
    tasks_blocked INTEGER DEFAULT 0,        -- 阻塞任务数
    tasks_overdue INTEGER DEFAULT 0,        -- 逾期任务数
    decisions_count INTEGER DEFAULT 0,      -- 总决策数
    recent_decisions_count INTEGER DEFAULT 0, -- 近7天新增决策数
    reports_count INTEGER DEFAULT 0,        -- 报告总数
    recent_reports_count INTEGER DEFAULT 0, -- 近7天新增报告数
    collections_count INTEGER DEFAULT 0,    -- 信息集合数
    handoffs_count INTEGER DEFAULT 0,       -- 交接记录数

    -- 评分
    efficiency_score INTEGER,
    output_score INTEGER,
    automation_score INTEGER,
    collaboration_score INTEGER,
    accumulation_score INTEGER,
    total_score INTEGER,
    
    -- XP
    xp_gained INTEGER DEFAULT 0,
    
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(agent_id, date)
);

CREATE INDEX idx_snapshots_agent_date ON daily_snapshots(agent_id, date DESC);
```

---

### 3.3 tool_call_logs（工具调用日志）⭐ 新增

**用途**: 存储每次工具调用的详细记录

**写入时机**: 每小时增量采集时 INSERT

**数据来源**: `~/.openclaw/agents/<id>/sessions/*.jsonl` 中的 `toolCall`

```sql
CREATE TABLE tool_call_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id TEXT NOT NULL,
    session_id TEXT,              -- Session ID

    -- 工具信息
    tool_name TEXT NOT NULL,      -- exec/read/write/browser...
    tool_category TEXT,           -- file/exec/search/browser/session...

    -- Token 消耗（该轮对话的）
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    cache_read INTEGER DEFAULT 0,

    -- 健康指标（供 Health 状态计算）
    stop_reason TEXT,             -- stop/end_turn/tool_use/max_tokens/error/timeout
    is_error INTEGER DEFAULT 0,   -- toolResult.is_error=true → 1

    -- 时间
    call_time TEXT NOT NULL,      -- ISO 格式时间戳

    -- 原始数据（用于去重和调试）
    raw_json TEXT,

    created_at TEXT DEFAULT (datetime('now')),

    -- 防重复：同一 session + 同一工具 + 同一时间点只插入一次
    UNIQUE(agent_id, session_id, tool_name, call_time)
);

CREATE INDEX idx_tool_logs_agent_time ON tool_call_logs(agent_id, call_time DESC);
CREATE INDEX idx_tool_logs_tool ON tool_call_logs(tool_name);
CREATE INDEX idx_tool_logs_stop ON tool_call_logs(agent_id, stop_reason);
```

**工具分类**:

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
}
```

---

### 3.4 cron_run_logs（Cron 执行日志）⭐ 新增

**用途**: 存储每次 Cron 执行的详细记录

**写入时机**: 每小时增量采集时 INSERT

**数据来源**: `~/.openclaw/cron/runs/*.jsonl` 中的 `action=finished`

```sql
CREATE TABLE cron_run_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id TEXT NOT NULL,
    job_id TEXT NOT NULL,         -- Cron 任务 ID
    job_name TEXT,                -- 任务名称
    
    -- 执行结果
    status TEXT NOT NULL,         -- ok/error
    error_message TEXT,           -- 错误信息（如有）
    duration_ms INTEGER,          -- 执行时长
    
    -- Token 消耗
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    
    -- 模型
    model TEXT,
    provider TEXT,
    
    -- 时间
    run_time TEXT NOT NULL,       -- 执行时间
    
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX idx_cron_logs_agent_time ON cron_run_logs(agent_id, run_time DESC);
CREATE INDEX idx_cron_logs_job ON cron_run_logs(job_id);
CREATE INDEX idx_cron_logs_status ON cron_run_logs(status);
```

---

### 3.5 collection_state（采集状态）

**用途**: 记录增量采集的进度

**写入时机**: 每小时采集后 UPDATE

```sql
CREATE TABLE collection_state (
    agent_id TEXT PRIMARY KEY,
    session_offsets TEXT DEFAULT '{}',  -- JSON: {filepath: byte_offset}
    cron_offsets TEXT DEFAULT '{}',     -- JSON: {filepath: byte_offset}
    last_collected_at TEXT,
    last_snapshot_at TEXT
);
```

---

### 3.6 achievements（成就记录）

**用途**: 记录解锁的成就

**写入时机**: 每日快照时检测，达成则 INSERT

```sql
CREATE TABLE achievements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id TEXT NOT NULL,
    achievement_id TEXT NOT NULL,
    achievement_name TEXT,
    category TEXT,
    unlocked_at TEXT DEFAULT (datetime('now')),
    UNIQUE(agent_id, achievement_id)
);

CREATE INDEX idx_achievements_agent ON achievements(agent_id);
```

---

## 四、数据流与写入时机

```
┌─────────────────────────────────────────────────────────────┐
│                 每小时增量采集（xx:00）                       │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  1. 读取 collection_state 获取上次位置                       │
│                                                              │
│  2. 增量解析 sessions/*.jsonl                                │
│     └─ 提取 toolCall → INSERT tool_call_logs                │
│                                                              │
│  3. 增量解析 cron/runs/*.jsonl                               │
│     └─ 提取 finished → INSERT cron_run_logs                 │
│                                                              │
│  4. UPDATE collection_state（保存新位置）                     │
│                                                              │
│  写入表: tool_call_logs, cron_run_logs, collection_state    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                 每日快照（00:05）                             │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  1. 从 tool_call_logs 聚合当日工具统计                       │
│     SELECT agent_id, COUNT(*), SUM(input_tokens)...         │
│     WHERE date(call_time) = date('now', '-1 day')           │
│                                                              │
│  2. 从 cron_run_logs 聚合当日 Cron 统计                      │
│     SELECT agent_id, COUNT(*), SUM(CASE status='ok')...     │
│     WHERE date(run_time) = date('now', '-1 day')            │
│                                                              │
│  3. 扫描工作空间（skills, memory, .learnings）               │
│                                                              │
│  4. 计算五维评分 + XP + 状态                                  │
│                                                              │
│  5. INSERT daily_snapshots                                   │
│  6. UPDATE agent_profiles                                    │
│  7. 检测成就 → INSERT achievements                           │
│                                                              │
│  写入表: daily_snapshots, agent_profiles, achievements      │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                 每周清理（周日 03:00）                        │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  DELETE FROM tool_call_logs                                  │
│  WHERE call_time < datetime('now', '-90 days')              │
│                                                              │
│  DELETE FROM cron_run_logs                                   │
│  WHERE run_time < datetime('now', '-90 days')               │
│                                                              │
│  VACUUM;  -- 压缩数据库                                      │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 五、存储预估

| 表 | 单条大小 | 日增量 | 90天数据 | 年增长 |
|----|---------|--------|---------|--------|
| agent_profiles | ~500B | 更新 | ~5KB | ~5KB |
| daily_snapshots | ~500B | 10条 | - | ~1.8MB |
| **tool_call_logs** | ~200B | ~500条 | ~9MB | ~9MB（滚动） |
| **cron_run_logs** | ~300B | ~50条 | ~1.3MB | ~1.3MB（滚动） |
| collection_state | ~1KB | 更新 | ~10KB | ~10KB |
| achievements | ~100B | 0-5条 | - | ~50KB |
| **总计** | - | - | **~10MB** | **~12MB** |

---

## 六、查询示例

### 6.1 查询某 Agent 今日工具使用情况

```sql
SELECT 
    tool_name,
    tool_category,
    COUNT(*) as call_count,
    SUM(input_tokens) as total_input,
    SUM(output_tokens) as total_output
FROM tool_call_logs
WHERE agent_id = 'coding-assistant'
  AND date(call_time) = date('now')
GROUP BY tool_name, tool_category
ORDER BY call_count DESC;
```

### 6.2 查询某 Agent 本周 Cron 执行统计

```sql
SELECT 
    date(run_time) as run_date,
    COUNT(*) as total_runs,
    SUM(CASE WHEN status = 'ok' THEN 1 ELSE 0 END) as success,
    SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) as errors,
    AVG(duration_ms) as avg_duration,
    SUM(total_tokens) as total_tokens
FROM cron_run_logs
WHERE agent_id = 'yunying'
  AND run_time >= datetime('now', '-7 days')
GROUP BY date(run_time)
ORDER BY run_date;
```

### 6.3 查询工具使用趋势（近30天）

```sql
SELECT 
    date(call_time) as call_date,
    tool_category,
    COUNT(*) as calls
FROM tool_call_logs
WHERE agent_id = 'coding-assistant'
  AND call_time >= datetime('now', '-30 days')
GROUP BY date(call_time), tool_category
ORDER BY call_date, calls DESC;
```

### 6.4 生成每日快照时的聚合查询

```sql
-- 汇总工具调用
SELECT 
    agent_id,
    COUNT(*) as tool_calls,
    COUNT(DISTINCT tool_name) as unique_tools,
    SUM(input_tokens) as input_tokens,
    SUM(output_tokens) as output_tokens,
    SUM(cache_read) as cache_read
FROM tool_call_logs
WHERE date(call_time) = :target_date
GROUP BY agent_id;

-- 汇总 Cron 执行
SELECT 
    agent_id,
    COUNT(*) as cron_runs,
    SUM(CASE WHEN status = 'ok' THEN 1 ELSE 0 END) as cron_success,
    SUM(total_tokens) as cron_tokens,
    AVG(duration_ms) as avg_duration
FROM cron_run_logs
WHERE date(run_time) = :target_date
GROUP BY agent_id;
```

### 6.5 多 Agent 排行（总览页）

```sql
-- 按综合评分排行所有 Agent
SELECT
    agent_id,
    level,
    stage,
    total_xp,
    total_score,
    energy,
    health,
    mood,
    hunger,
    updated_at
FROM agent_profiles
ORDER BY total_score DESC;
```

### 6.6 多 Agent 当日活跃统计

```sql
-- 今日各 Agent 工具调用量对比
SELECT
    agent_id,
    COUNT(*) as tool_calls,
    SUM(input_tokens) as input_tokens,
    SUM(output_tokens) as output_tokens,
    SUM(CASE WHEN is_error=1 THEN 1 ELSE 0 END) as tool_errors
FROM tool_call_logs
WHERE date(call_time) = date('now')
GROUP BY agent_id
ORDER BY tool_calls DESC;
```

### 6.7 协作网络查询

```sql
-- 查询某 Agent 的协作伙伴（被谁调用 + 调用了谁）
-- 需要结合 subagents/runs.json 解析结果
-- ClawGrowth 在 agent_profiles 中存储 collaborations 汇总
SELECT
    s.agent_id,
    p.level,
    s.collaborations,
    s.collab_success,
    ROUND(s.collab_success * 100.0 / MAX(s.collaborations, 1), 1) as success_rate
FROM daily_snapshots s
JOIN agent_profiles p ON s.agent_id = p.agent_id
WHERE s.date >= date('now', '-7 days')
GROUP BY s.agent_id
ORDER BY s.collaborations DESC;
```

### 6.8 共享工作空间团队健康查询

```sql
-- 最新共享工作空间状态（团队总指挥）
SELECT
    date,
    heartbeat_hours_ago,
    heartbeat_daily_count,
    last_task_hours_ago,
    projects_active_count,
    tasks_blocked,
    tasks_overdue,
    decisions_count,
    recent_decisions_count,
    reports_count,
    recent_reports_count,
    collections_count,
    handoffs_count
FROM daily_snapshots
WHERE agent_id = '__shared__'
ORDER BY date DESC
LIMIT 7;
```

### 6.9 工具生态成熟度查询

```sql
-- 各 Agent 工具成熟度对比
SELECT
    s.agent_id,
    s.date,
    s.tools_skills_installed,
    s.tools_external_integrations,
    s.tools_md_updated_days_ago,
    s.feature_requests_count,
    s.recent_feature_requests
FROM daily_snapshots s
WHERE s.date = date('now', '-1 day')
ORDER BY s.tools_skills_installed DESC;
```

---

## 七、初始化脚本

```python
import sqlite3
from pathlib import Path

def init_database(db_path: str = "~/.openclaw/clawgrowth/clawgrowth.db"):
    """初始化 ClawGrowth 数据库 - 6张表"""
    db_path = Path(db_path).expanduser()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    cursor.executescript('''
        -- 1. Agent 档案
        CREATE TABLE IF NOT EXISTS agent_profiles (
            agent_id TEXT PRIMARY KEY,
            level INTEGER DEFAULT 1,
            total_xp INTEGER DEFAULT 0,
            stage TEXT DEFAULT 'baby',
            efficiency_score INTEGER DEFAULT 50,
            output_score INTEGER DEFAULT 50,
            automation_score INTEGER DEFAULT 50,
            collaboration_score INTEGER DEFAULT 50,
            accumulation_score INTEGER DEFAULT 50,
            total_score INTEGER DEFAULT 50,
            energy INTEGER DEFAULT 100,
            health INTEGER DEFAULT 100,
            mood INTEGER DEFAULT 80,
            hunger INTEGER DEFAULT 50,
            initialized_at TEXT,
            updated_at TEXT DEFAULT (datetime('now'))
        );
        
        -- 2. 每日快照
        CREATE TABLE IF NOT EXISTS daily_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id TEXT NOT NULL,
            date TEXT NOT NULL,
            conversations INTEGER DEFAULT 0,
            tool_calls INTEGER DEFAULT 0,
            input_tokens INTEGER DEFAULT 0,
            output_tokens INTEGER DEFAULT 0,
            cache_read INTEGER DEFAULT 0,
            cron_runs INTEGER DEFAULT 0,
            cron_success INTEGER DEFAULT 0,
            collaborations INTEGER DEFAULT 0,
            collab_success INTEGER DEFAULT 0,
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
            tools_md_updated_days_ago INTEGER,
            heartbeat_hours_ago REAL,
            heartbeat_daily_count INTEGER DEFAULT 0,
            last_task_hours_ago REAL,
            projects_active_count INTEGER DEFAULT 0,
            tasks_blocked INTEGER DEFAULT 0,
            tasks_overdue INTEGER DEFAULT 0,
            decisions_count INTEGER DEFAULT 0,
            recent_decisions_count INTEGER DEFAULT 0,
            reports_count INTEGER DEFAULT 0,
            recent_reports_count INTEGER DEFAULT 0,
            collections_count INTEGER DEFAULT 0,
            handoffs_count INTEGER DEFAULT 0,
            efficiency_score INTEGER,
            output_score INTEGER,
            automation_score INTEGER,
            collaboration_score INTEGER,
            accumulation_score INTEGER,
            total_score INTEGER,
            xp_gained INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE(agent_id, date)
        );
        CREATE INDEX IF NOT EXISTS idx_snapshots_agent_date 
            ON daily_snapshots(agent_id, date DESC);
        
        -- 3. 工具调用日志
        CREATE TABLE IF NOT EXISTS tool_call_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id TEXT NOT NULL,
            session_id TEXT,
            tool_name TEXT NOT NULL,
            tool_category TEXT,
            input_tokens INTEGER DEFAULT 0,
            output_tokens INTEGER DEFAULT 0,
            cache_read INTEGER DEFAULT 0,
            stop_reason TEXT,
            is_error INTEGER DEFAULT 0,
            call_time TEXT NOT NULL,
            raw_json TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE(agent_id, session_id, tool_name, call_time)
        );
        CREATE INDEX IF NOT EXISTS idx_tool_logs_agent_time
            ON tool_call_logs(agent_id, call_time DESC);
        CREATE INDEX IF NOT EXISTS idx_tool_logs_tool
            ON tool_call_logs(tool_name);
        CREATE INDEX IF NOT EXISTS idx_tool_logs_stop
            ON tool_call_logs(agent_id, stop_reason);
        
        -- 4. Cron 执行日志
        CREATE TABLE IF NOT EXISTS cron_run_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id TEXT NOT NULL,
            job_id TEXT NOT NULL,
            job_name TEXT,
            status TEXT NOT NULL,
            error_message TEXT,
            duration_ms INTEGER,
            input_tokens INTEGER DEFAULT 0,
            output_tokens INTEGER DEFAULT 0,
            total_tokens INTEGER DEFAULT 0,
            model TEXT,
            provider TEXT,
            run_time TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_cron_logs_agent_time 
            ON cron_run_logs(agent_id, run_time DESC);
        CREATE INDEX IF NOT EXISTS idx_cron_logs_job 
            ON cron_run_logs(job_id);
        CREATE INDEX IF NOT EXISTS idx_cron_logs_status 
            ON cron_run_logs(status);
        
        -- 5. 采集状态
        CREATE TABLE IF NOT EXISTS collection_state (
            agent_id TEXT PRIMARY KEY,
            session_offsets TEXT DEFAULT '{}',
            cron_offsets TEXT DEFAULT '{}',
            last_collected_at TEXT,
            last_snapshot_at TEXT
        );
        
        -- 6. 成就记录
        CREATE TABLE IF NOT EXISTS achievements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id TEXT NOT NULL,
            achievement_id TEXT NOT NULL,
            achievement_name TEXT,
            category TEXT,
            unlocked_at TEXT DEFAULT (datetime('now')),
            UNIQUE(agent_id, achievement_id)
        );
        CREATE INDEX IF NOT EXISTS idx_achievements_agent 
            ON achievements(agent_id);
    ''')
    
    conn.commit()
    conn.close()
    
    print(f"Database initialized: {db_path}")
    print("Tables: agent_profiles, daily_snapshots, tool_call_logs, cron_run_logs, collection_state, achievements")
    return str(db_path)


if __name__ == "__main__":
    init_database()
```

---

## 八、数据保留策略

| 表 | 保留策略 | 清理 SQL |
|----|---------|---------|
| agent_profiles | 永久 | 不清理 |
| daily_snapshots | 永久 | 不清理 |
| **tool_call_logs** | **90天** | `DELETE WHERE call_time < datetime('now', '-90 days')` |
| **cron_run_logs** | **90天** | `DELETE WHERE run_time < datetime('now', '-90 days')` |
| collection_state | 永久 | 不清理 |
| achievements | 永久 | 不清理 |

**每周清理脚本**:

```sql
-- 清理90天前的日志
DELETE FROM tool_call_logs WHERE call_time < datetime('now', '-90 days');
DELETE FROM cron_run_logs WHERE run_time < datetime('now', '-90 days');

-- 压缩数据库
VACUUM;
```

---

_Version 3.1 | 6张表，采集即存储_
