# ClawGrowth 指标参考手册

ClawGrowth 采集和计算的所有指标完整列表。

---

## 📊 核心指标

### 今日活动

| 指标 | 说明 | 数据来源 |
|------|------|----------|
| `tool_calls` | 今日工具调用总数 | sessions/*.jsonl |
| `unique_tools` | 使用的不同工具数 | sessions/*.jsonl |
| `input_tokens` | 输入消耗的 Token | sessions/*.jsonl |
| `output_tokens` | 输出生成的 Token | sessions/*.jsonl |
| `cache_read` | 从缓存读取的 Token | sessions/*.jsonl |
| `cron_runs` | Cron 执行次数 | cron/runs/*.jsonl |
| `cron_success` | Cron 成功次数 | cron/runs/*.jsonl |
| `cron_error_count` | Cron 失败次数 | cron/runs/*.jsonl |
| `collaborations` | 多 Agent 协作次数 | subagents/runs.json |
| `collab_success` | 协作成功次数 | subagents/runs.json |
| `conversations` | 用户对话轮次 | sessions/*.jsonl |
| `tool_errors` | 工具调用失败数 | sessions/*.jsonl |

---

## 📈 衍生指标

| 指标 | 公式 | 说明 |
|------|------|------|
| `token_efficiency` | `output_tokens / input_tokens` | 输入输出比 |
| `cache_hit_rate` | `cache_read / (input_tokens + cache_read)` | 缓存命中率 |
| `cron_success_rate` | `cron_success / cron_runs * 100` | Cron 成功率 % |
| `tool_error_rate` | `tool_errors / tool_calls * 100` | 工具失败率 % |
| `tool_diversity` | `unique_tools / tool_calls` | 工具多样性 |
| `context_usage` | `total_tokens / context_max * 100` | 上下文使用率 % |

---

## 🎯 五维评分

### 效率分 (25% 权重)

| 分项 | 满分 | 衡量内容 |
|------|------|----------|
| Token 效率 | 40 | Token 使用效率 |
| 缓存命中率 | 30 | 缓存利用率 |
| 响应速度 | 30 | 平均响应时间 |

### 产出分 (25% 权重)

| 分项 | 满分 | 衡量内容 |
|------|------|----------|
| 输出 Token | 40 | Token 产出量 |
| 工具调用 | 40 | 工具调用量 |
| 对话轮次 | 20 | 用户交互深度 |

### 自动化分 (20% 权重)

| 分项 | 满分 | 衡量内容 |
|------|------|----------|
| 任务量 | 40 | Cron 执行次数 |
| 成功率 | 60 | Cron 成功率 |

### 协作分 (15% 权重)

| 分项 | 满分 | 衡量内容 |
|------|------|----------|
| 协作次数 | 30 | 多 Agent 交互数 |
| 多样性 | 30 | 协作伙伴数 |
| 成功率 | 40 | 协作成功率 |

### 积累分 (15% 权重)

| 分项 | 满分 | 衡量内容 |
|------|------|----------|
| 技能 | 35 | 已安装技能数 |
| 记忆 | 20 | 记忆文件数 |
| 学习 | 20 | 学习记录数 |
| MEMORY 章节 | 25 | 长期记忆深度 |

---

## 🏥 四状态指标

### 精力 Energy (0-100)

| 分项 | 权重 | 衡量内容 |
|------|------|----------|
| 上下文剩余 | 50% | 可用上下文窗口 |
| 压缩健康 | 30% | Token 使用效率 |
| 活动新鲜度 | 20% | 活动时间近度 |

### 健康 Health (0-100)

| 分项 | 权重 | 衡量内容 |
|------|------|----------|
| Cron 质量 | 40% | Cron 成功率 |
| 工具可靠性 | 35% | 工具错误率 |
| 错误趋势 | 25% | 错误数量趋势 |

### 心情 Mood (0-100)

| 分项 | 权重 | 衡量内容 |
|------|------|----------|
| 交互质量 | 40% | stop_reason 分布 |
| 活跃度 | 30% | 工具/对话量 |
| 输出丰富度 | 30% | 输出 Token 密度 |

### 饥饿 Hunger (0-100)

| 分项 | 权重 | 衡量内容 |
|------|------|----------|
| 学习新鲜度 | 50% | 距上次学习时间 |
| 深度 | 30% | 近期学习字数 |
| 广度 | 20% | 学习记录数 |

---

## 🎮 XP 来源

| 来源 | XP/单位 | 说明 |
|------|---------|------|
| 对话轮次 | 1 | 每次用户消息 |
| 工具调用 | 2 | 每次工具调用 |
| Cron 成功 | 10 | 每次成功执行 |
| 协作成功 | 20 | 每次成功协作 |
| 技能（超过20个） | 30 | 超过基础 20 个的技能 |
| 今日记忆 | 5 | 今日记忆文件存在 |
| 学习记录 | 10 | 每条学习记录 |

---

## 📁 工作空间指标

| 指标 | 说明 |
|------|------|
| `skills_count` | 已安装技能总数（私有+共享） |
| `memories_count` | /memory/ 目录文件数 |
| `memories_words` | 记忆文件总字数 |
| `has_today_memory` | 今日记忆文件是否存在 |
| `recent_memory_count` | 近 7 天记忆数 |
| `learnings_count` | .learnings/ 目录条目数 |
| `learnings_words` | 学习记录总字数 |
| `errors_count` | 错误记录数 |
| `feature_requests_count` | 功能请求数 |
| `memory_sections` | MEMORY.md 章节数 |
| `memory_words` | MEMORY.md 字数 |
| `workspace_completeness` | 核心文件完整性 % |

### 工作空间完整性检查文件

- AGENTS.md
- SOUL.md
- USER.md
- IDENTITY.md
- MEMORY.md
- TOOLS.md
- memory/ 目录
- .learnings/ 目录

---

## 🤝 共享工作空间指标

| 指标 | 说明 |
|------|------|
| `heartbeat_hours_ago` | 距上次心跳小时数 |
| `heartbeat_daily_count` | 24 小时内心跳数 |
| `last_task_hours_ago` | 距上次任务小时数 |
| `projects_active_count` | 活跃项目数 |
| `tasks_blocked` | 阻塞任务数 |
| `tasks_overdue` | 逾期任务数 |
| `decisions_count` | 决策记录总数 |
| `reports_count` | 报告总数 |
| `collections_count` | 收藏数 |

---

## ⏰ Cron 指标

| 指标 | 说明 |
|------|------|
| `jobs_total` | 配置的 Cron 任务总数 |
| `jobs_enabled` | 当前启用的任务数 |
| `runs_today` | 24 小时内运行次数 |
| `success_today` | 今日成功次数 |
| `avg_duration_ms` | 平均执行时长 |
| `recent_errors` | 最近 5 条错误 |

---

## 🛠️ 工具分类

| 分类 | 包含工具 |
|------|----------|
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

## 🎨 颜色阈值

| 总分 | 颜色 | 色值 |
|------|------|------|
| 80+ | 红色 | #E84B3A |
| 60-79 | 橙色 | #F5A623 |
| 40-59 | 青绿 | #4DB8A4 |
| 20-39 | 蓝色 | #5B9BD5 |
| 0-19 | 紫色 | #9B5DE5 |

---

## 📈 等级阈值

| 等级 | 所需 XP | 阶段 |
|------|---------|------|
| 1 | 0 | 幼苗 |
| 2 | 100 | 幼苗 |
| 3 | 250 | 幼苗 |
| 4 | 450 | 幼苗 |
| 5 | 700 | 成长 |
| 6 | 1,000 | 成长 |
| 7 | 1,400 | 成长 |
| 8 | 1,900 | 成长 |
| 9 | 2,500 | 成熟 |
| 10 | 3,200 | 成熟 |
| 11 | 4,000 | 成熟 |
| 12 | 5,000 | 成熟 |
| 13 | 6,200 | 专家 |
| 14 | 7,600 | 专家 |
| 15 | 9,200 | 专家 |
| 16 | 11,000 | 专家 |
| 17 | 13,000 | 传说 |
| 18 | 15,500 | 传说 |
| 19 | 18,500 | 传说 |
| 20 | 22,000 | 传说 |
| 21 | 26,000 | 传说 |
