# ClawGrowth Algorithm Rules

> **Principle**: Collect and store, every variable can be extracted from OpenClaw native data

---

## 1. Overview

### Data Flow

```
OpenClaw Native Data (read-only)
        │
        ▼ Hourly Collection
┌───────────────────┐
│  tool_call_logs   │ ← sessions/*.jsonl (toolCall + toolResult + stopReason)
│  cron_run_logs    │ ← cron/runs/*.jsonl finished records
│  collection_state │ ← Track collection progress
└───────────────────┘
        │
        ▼ Daily Aggregation (00:05)
┌───────────────────┐
│  daily_snapshots  │ ← SELECT aggregates from log tables
│  agent_profiles   │ ← Calculate scores + status with EMA smoothing
│  achievements     │ ← Check and insert achievements
└───────────────────┘
```

---

## 2. Five-Dimension Scoring

### 2.1 Overview

| Dimension | Weight | Key Metrics |
|-----------|--------|-------------|
| **Efficiency** | 25% | Token efficiency, cache hit rate, response speed |
| **Output** | 25% | Output tokens, tool calls, conversations |
| **Automation** | 20% | Cron runs, success rate |
| **Collaboration** | 15% | Collaborations, diversity, success rate |
| **Accumulation** | 15% | Skills, memories, learnings |

### 2.2 Efficiency Score (max 100)

```python
# Token efficiency (max 40)
token_eff = min(40, (output_tokens / input_tokens) * 40) if input_tokens > 0 else 0

# Cache hit rate (max 30)
total_input = input_tokens + cache_read
cache_rate = (cache_read / total_input * 100) if total_input > 0 else 0
cache_score = min(30, cache_rate / 100 * 30)

# Response speed (max 30)
avg_duration_s = avg_duration_ms / 1000
if avg_duration_s < 5:
    speed_score = 30
elif avg_duration_s < 30:
    speed_score = 30 - (avg_duration_s - 5) * (25 / 25)
else:
    speed_score = 5

efficiency_score = token_eff + cache_score + speed_score
```

### 2.3 Output Score (max 100)

```python
# Output tokens (40%)
output_score_tokens = min(40, output_tokens / 200 * 40)

# Tool calls (40%)
output_score_tools = min(40, tool_calls * 2)

# Conversations (20%)
output_score_conv = min(20, conversations * 5)

output_score = output_score_tokens + output_score_tools + output_score_conv
```

### 2.4 Automation Score (max 100)

```python
# Task execution volume (40%)
volume_score = min(40, cron_runs * 4)

# Success rate (60%)
rate = (cron_success / cron_runs * 100) if cron_runs > 0 else 100
rate_score = rate * 0.6

automation_score = volume_score + rate_score
```

### 2.5 Collaboration Score (max 100)

```python
# Collaboration count (30%)
collab_score = min(30, collaborations * 3)

# Diversity (30%) - unique partners
diversity_score = min(30, collab_unique_agents * 10)

# Success rate (40%)
collab_rate = (collab_success / collaborations * 100) if collaborations > 0 else 100
rate_score = collab_rate * 0.4

collaboration_score = collab_score + diversity_score + rate_score
```

### 2.6 Accumulation Score (max 100)

```python
# Skills (35%)
skills_score = min(35, skills_count * 3.5)

# Memories (20%)
memory_score = min(20, memories_count * 2)

# Learnings (20%)
learning_score = min(20, learnings_count * 2)

# MEMORY.md sections (25%)
sections_score = min(25, memory_sections * 5)

accumulation_score = skills_score + memory_score + learning_score + sections_score
```

### 2.7 Total Score

```python
total_score = (
    efficiency_score * 0.25 +
    output_score * 0.25 +
    automation_score * 0.20 +
    collaboration_score * 0.15 +
    accumulation_score * 0.15
)
```

---

## 3. Four-Status System

### 3.1 Overview

| Status | Measures | Range |
|--------|----------|-------|
| **Energy** | Context capacity, compression health, freshness | 0-100 |
| **Health** | Cron quality, tool reliability, error trend | 0-100 |
| **Mood** | Interaction quality, activity, output richness | 0-100 |
| **Hunger** | Learning freshness, depth, breadth | 0-100 |

### 3.2 Energy Calculation

```python
# Context remaining (50%)
context_remaining = min(100, 100 - context_usage)
context_score = context_remaining * 0.5

# Compression health (30%) - based on total tokens used
compression_score = min(30, 30 * (1 - total_tokens / context_max / 2))

# Activity freshness (20%) - hours since last activity
freshness = max(0, 100 - hours_since_last_activity * 4)
freshness_score = freshness * 0.2

energy = context_score + compression_score + freshness_score
```

### 3.3 Health Calculation

```python
# Cron quality (40%)
cron_rate = (cron_success / cron_runs * 100) if cron_runs > 0 else 100
cron_score = cron_rate * 0.4

# Tool reliability (35%)
tool_rate = 100 - tool_error_rate
tool_score = tool_rate * 0.35

# Error trend (25%) - decreasing errors = healthy
error_trend_score = min(25, 25 - error_today * 5)

health = cron_score + tool_score + error_trend_score
```

### 3.4 Mood Calculation

```python
# Interaction quality (40%) - stop_reason distribution
good_stops = end_turn_count + stop_count
total_stops = tool_calls
quality = (good_stops / total_stops * 100) if total_stops > 0 else 70
quality_score = quality * 0.4

# Activity level (30%)
activity = min(100, tool_calls * 2 + conversations * 10)
activity_score = activity * 0.3

# Output richness (30%)
richness = min(100, output_tokens / 100)
richness_score = richness * 0.3

mood = quality_score + activity_score + richness_score
```

### 3.5 Hunger Calculation

```python
# Learning freshness (50%) - hours since last learning
hours = hours_since_last_learning
freshness = max(0, 100 - hours * 4)
freshness_score = freshness * 0.5

# Depth (30%) - learning words
depth = min(100, recent_learning_words / 100)
depth_score = depth * 0.3

# Breadth (20%) - learning entries
breadth = min(100, learnings_count * 10)
breadth_score = breadth * 0.2

hunger = freshness_score + depth_score + breadth_score
```

### 3.6 EMA Smoothing

All status values use Exponential Moving Average to prevent sudden jumps:

```python
ALPHA = 0.3
new_value = ALPHA * calculated_value + (1 - ALPHA) * previous_value
```

---

## 4. XP & Level System

### 4.1 XP Sources

| Source | XP per Unit |
|--------|-------------|
| Conversations | 1 |
| Tool calls | 2 |
| Cron success | 10 |
| Collaboration success | 20 |
| New skills (above base 20) | 30 |
| Today memory | 5 |
| Learnings | 10 |

### 4.2 XP Calculation

```python
xp_conversations = conversations * 1
xp_tools = tool_calls * 2
xp_cron = cron_success * 10
xp_collab = collab_success * 20
xp_skills = max(0, skills_count - 20) * 30
xp_memory = 5 if has_today_memory else 0
xp_learnings = learnings_count * 10

total_xp = sum([xp_conversations, xp_tools, xp_cron, xp_collab, xp_skills, xp_memory, xp_learnings])
```

### 4.3 Level Thresholds

```python
LEVEL_THRESHOLDS = [
    0, 100, 250, 450, 700, 1000,      # Levels 1-6
    1400, 1900, 2500, 3200, 4000,     # Levels 7-11
    5000, 6200, 7600, 9200, 11000,    # Levels 12-16
    13000, 15500, 18500, 22000, 26000 # Levels 17-21
]

def get_level(xp: int) -> int:
    for i, threshold in enumerate(LEVEL_THRESHOLDS):
        if xp < threshold:
            return i
    return len(LEVEL_THRESHOLDS)
```

### 4.4 Growth Stages

| Level Range | Stage |
|-------------|-------|
| 1-4 | Baby |
| 5-8 | Growing |
| 9-12 | Mature |
| 13-16 | Expert |
| 17+ | Legend |

---

## 5. Color System

Color reflects the agent's total score:

| Score Range | Color | Name |
|-------------|-------|------|
| 80+ | #E84B3A | Red |
| 60-79 | #F5A623 | Orange |
| 40-59 | #4DB8A4 | Teal |
| 20-39 | #5B9BD5 | Blue |
| 0-19 | #9B5DE5 | Purple |

```python
CLAW_COLORS = [
    {'min': 80, 'hex': '#E84B3A', 'name': 'red'},
    {'min': 60, 'hex': '#F5A623', 'name': 'orange'},
    {'min': 40, 'hex': '#4DB8A4', 'name': 'teal'},
    {'min': 20, 'hex': '#5B9BD5', 'name': 'blue'},
    {'min':  0, 'hex': '#9B5DE5', 'name': 'purple'},
]

def get_claw_color(score: float) -> dict:
    for c in CLAW_COLORS:
        if score >= c['min']:
            return c
    return CLAW_COLORS[-1]
```

---

## 6. Tool Categories

| Category | Tools |
|----------|-------|
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

## 7. Data Retention

| Table | Retention | Cleanup |
|-------|-----------|---------|
| tool_call_logs | 7 days | Daily at 03:00 |
| cron_run_logs | 30 days | Daily at 03:00 |
| daily_snapshots | Permanent | - |
| agent_profiles | Permanent | - |

---

For database schema details, see [database-design.md](database-design.md).
