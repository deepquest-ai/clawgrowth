# ClawGrowth Metrics Reference

A complete list of all metrics collected and calculated by ClawGrowth.

---

## 📊 Core Metrics

### Today's Activity

| Metric | Description | Source |
|--------|-------------|--------|
| `tool_calls` | Total tool invocations today | sessions/*.jsonl |
| `unique_tools` | Distinct tools used | sessions/*.jsonl |
| `input_tokens` | Tokens consumed as input | sessions/*.jsonl |
| `output_tokens` | Tokens generated as output | sessions/*.jsonl |
| `cache_read` | Tokens served from cache | sessions/*.jsonl |
| `cron_runs` | Cron jobs executed | cron/runs/*.jsonl |
| `cron_success` | Successful cron runs | cron/runs/*.jsonl |
| `cron_error_count` | Failed cron runs | cron/runs/*.jsonl |
| `collaborations` | Multi-agent interactions | subagents/runs.json |
| `collab_success` | Successful collaborations | subagents/runs.json |
| `conversations` | User conversation turns | sessions/*.jsonl |
| `tool_errors` | Tool call failures | sessions/*.jsonl |

---

## 📈 Derived Metrics

| Metric | Formula | Description |
|--------|---------|-------------|
| `token_efficiency` | `output_tokens / input_tokens` | Output-to-input ratio |
| `cache_hit_rate` | `cache_read / (input_tokens + cache_read)` | Cache effectiveness |
| `cron_success_rate` | `cron_success / cron_runs * 100` | Cron reliability % |
| `tool_error_rate` | `tool_errors / tool_calls * 100` | Tool failure % |
| `tool_diversity` | `unique_tools / tool_calls` | Tool variety ratio |
| `context_usage` | `total_tokens / context_max * 100` | Context window usage % |

---

## 🎯 Five-Dimension Scores

### Efficiency Score (25% weight)

| Component | Max | Measures |
|-----------|-----|----------|
| Token Efficiency | 40 | How efficiently tokens are used |
| Cache Hit Rate | 30 | Cache utilization |
| Response Speed | 30 | Average response time |

### Output Score (25% weight)

| Component | Max | Measures |
|-----------|-----|----------|
| Output Tokens | 40 | Raw token production |
| Tool Calls | 40 | Tool invocation volume |
| Conversations | 20 | User interaction depth |

### Automation Score (20% weight)

| Component | Max | Measures |
|-----------|-----|----------|
| Task Volume | 40 | Number of cron runs |
| Success Rate | 60 | Cron success percentage |

### Collaboration Score (15% weight)

| Component | Max | Measures |
|-----------|-----|----------|
| Collab Count | 30 | Multi-agent interactions |
| Diversity | 30 | Unique collaboration partners |
| Success Rate | 40 | Collaboration success % |

### Accumulation Score (15% weight)

| Component | Max | Measures |
|-----------|-----|----------|
| Skills | 35 | Installed skills count |
| Memories | 20 | Memory file count |
| Learnings | 20 | Learning entries |
| MEMORY Sections | 25 | Long-term memory depth |

---

## 🏥 Four-Status Indicators

### Energy (0-100)

| Component | Weight | Measures |
|-----------|--------|----------|
| Context Remaining | 50% | Available context window |
| Compression Health | 30% | Token usage efficiency |
| Activity Freshness | 20% | Recency of activity |

### Health (0-100)

| Component | Weight | Measures |
|-----------|--------|----------|
| Cron Quality | 40% | Cron success rate |
| Tool Reliability | 35% | Tool error rate |
| Error Trend | 25% | Error count trend |

### Mood (0-100)

| Component | Weight | Measures |
|-----------|--------|----------|
| Interaction Quality | 40% | Stop reason distribution |
| Activity Level | 30% | Tool/conversation volume |
| Output Richness | 30% | Output token density |

### Hunger (0-100)

| Component | Weight | Measures |
|-----------|--------|----------|
| Learning Freshness | 50% | Time since last learning |
| Depth | 30% | Recent learning word count |
| Breadth | 20% | Learning entry count |

---

## 🎮 XP Sources

| Source | XP/Unit | Description |
|--------|---------|-------------|
| Conversations | 1 | Each user message turn |
| Tool Calls | 2 | Each tool invocation |
| Cron Success | 10 | Each successful cron run |
| Collab Success | 20 | Each successful collaboration |
| Skills (above 20) | 30 | Each skill beyond base 20 |
| Today Memory | 5 | Daily memory file exists |
| Learnings | 10 | Each learning entry |

---

## 📁 Workspace Metrics

| Metric | Description |
|--------|-------------|
| `skills_count` | Total installed skills (private + shared) |
| `memories_count` | Memory files in /memory/ |
| `memories_words` | Total words across memories |
| `has_today_memory` | Today's memory file exists |
| `recent_memory_count` | Memories in last 7 days |
| `learnings_count` | Entries in .learnings/ |
| `learnings_words` | Total words in learnings |
| `errors_count` | Errors logged |
| `feature_requests_count` | Feature requests logged |
| `memory_sections` | Sections in MEMORY.md |
| `memory_words` | Words in MEMORY.md |
| `workspace_completeness` | % of core files present |

### Workspace Completeness Files

- AGENTS.md
- SOUL.md
- USER.md
- IDENTITY.md
- MEMORY.md
- TOOLS.md
- memory/ directory
- .learnings/ directory

---

## 🤝 Shared Workspace Metrics

| Metric | Description |
|--------|-------------|
| `heartbeat_hours_ago` | Hours since last heartbeat |
| `heartbeat_daily_count` | Heartbeats in last 24h |
| `last_task_hours_ago` | Hours since last task |
| `projects_active_count` | Active projects count |
| `tasks_blocked` | Blocked tasks count |
| `tasks_overdue` | Overdue tasks count |
| `decisions_count` | Total decisions logged |
| `reports_count` | Total reports |
| `collections_count` | Collections/bookmarks |

---

## ⏰ Cron Metrics

| Metric | Description |
|--------|-------------|
| `jobs_total` | Total configured cron jobs |
| `jobs_enabled` | Currently enabled jobs |
| `runs_today` | Runs in last 24 hours |
| `success_today` | Successful runs today |
| `avg_duration_ms` | Average run duration |
| `recent_errors` | Last 5 error messages |

---

## 🛠️ Tool Categories

| Category | Tools Included |
|----------|----------------|
| file | read, write, edit |
| exec | exec, process |
| search | web_search, web_fetch |
| browser | browser |
| nodes | nodes, canvas |
| message | message |
| session | sessions_spawn, sessions_send, subagents |
| media | image, pdf, tts |
| system | session_status, agents_list |

---

## 📊 Session Metrics

| Metric | Description |
|--------|-------------|
| `total_sessions` | Total session count |
| `recent_sessions` | Sessions in last 7 days |
| `avg_session_tokens` | Average tokens per session |
| `context_max` | Maximum context window |
| `last_activity` | Last session timestamp |

---

## 🎨 Color Thresholds

| Total Score | Color | Hex |
|-------------|-------|-----|
| 80+ | Red | #E84B3A |
| 60-79 | Orange | #F5A623 |
| 40-59 | Teal | #4DB8A4 |
| 20-39 | Blue | #5B9BD5 |
| 0-19 | Purple | #9B5DE5 |

---

## 📈 Level Thresholds

| Level | XP Required | Stage |
|-------|-------------|-------|
| 1 | 0 | Baby |
| 2 | 100 | Baby |
| 3 | 250 | Baby |
| 4 | 450 | Baby |
| 5 | 700 | Growing |
| 6 | 1,000 | Growing |
| 7 | 1,400 | Growing |
| 8 | 1,900 | Growing |
| 9 | 2,500 | Mature |
| 10 | 3,200 | Mature |
| 11 | 4,000 | Mature |
| 12 | 5,000 | Mature |
| 13 | 6,200 | Expert |
| 14 | 7,600 | Expert |
| 15 | 9,200 | Expert |
| 16 | 11,000 | Expert |
| 17 | 13,000 | Legend |
| 18 | 15,500 | Legend |
| 19 | 18,500 | Legend |
| 20 | 22,000 | Legend |
| 21 | 26,000 | Legend |
