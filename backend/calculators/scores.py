from typing import Any, Dict


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    """Clamp a value to [low, high] and round to 2 decimal places."""
    return round(max(low, min(high, value)), 2)


def calc_efficiency_score(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Efficiency score (max 100):
      token_ratio (max 40):  output/input normalized; ratio of 0.5 = 40 pts
      cache_ratio (max 30):  cacheRead/(input+output) normalized
      speed       (max 30):  <5s=30, linear decay to 30s=5, >30s=5

    Formula: token_ratio(max40) + cache_ratio(max30) + speed(max30)
    """
    input_tokens = int(data.get('input_tokens', 0) or 0)
    output_tokens = int(data.get('output_tokens', 0) or 0)
    cache_read = int(data.get('cache_read', 0) or 0)
    avg_duration_ms = float(data.get('avg_duration_ms', 10000) or 10000)

    # Token ratio: output/input — ratio of 0.5 maps to perfect 40 pts
    token_ratio = output_tokens / max(input_tokens, 1)
    token_ratio_score = min(40.0, token_ratio * 80.0)

    # Cache ratio: cacheRead / (input+output) — 60% cache = perfect 30 pts
    total_tokens = max(input_tokens + output_tokens, 1)
    cache_ratio = cache_read / total_tokens
    cache_ratio_score = min(30.0, cache_ratio * 50.0)

    # Speed score: <5s=30, linear decay to 30s=5, >30s=5
    if avg_duration_ms < 5000:
        speed_score = 30.0
    elif avg_duration_ms < 30000:
        speed_score = max(5.0, 30.0 - (avg_duration_ms - 5000) / 1000.0)
    else:
        speed_score = 5.0

    value = clamp(token_ratio_score + cache_ratio_score + speed_score)
    
    # Build breakdown with formulas
    avg_duration_s = avg_duration_ms / 1000
    breakdown_items = [
        {
            'name': 'token_ratio_score',
            'value': round(token_ratio_score, 2),
            'formula': f'output/input × 80 = {round(token_ratio, 4)} × 80 = {round(token_ratio * 80, 2)} → max 40',
        },
        {
            'name': 'cache_ratio_score',
            'value': round(cache_ratio_score, 2),
            'formula': f'cache/(input+output) × 50 = {round(cache_ratio, 4)} × 50 = {round(cache_ratio * 50, 2)} → max 30',
        },
        {
            'name': 'speed_score',
            'value': round(speed_score, 2),
            'formula': f'avg_duration={round(avg_duration_s, 1)}s → {"<5s=30" if avg_duration_s < 5 else "5-30s decay" if avg_duration_s < 30 else ">30s=5"}',
        },
    ]
    
    return {
        'value': value,
        'breakdown': breakdown_items,
        'source_data': {
            'input_tokens': input_tokens,
            'output_tokens': output_tokens,
            'cache_read': cache_read,
            'avg_duration_ms': round(avg_duration_ms, 0),
            'token_ratio': round(token_ratio, 4),
            'cache_ratio': round(cache_ratio, 4),
        },
        'formula':    'token_ratio(max40) + cache_ratio(max30) + speed(max30)',
        'formula_zh': 'Token效率(max40) + 缓存效率(max30) + 速度(max30)',
    }


def calc_output_score(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Output score (max 100):
      output_token_score (max 40):  output_tokens/200, capped at 40 pts
      tool_call_score    (max 40):  tool_calls*2,      capped at 40 pts
      conversation_score (max 20):  conversations*5,   capped at 20 pts

    Formula: output_tokens(40) + tool_calls(40) + conversations(20)
    """
    output_tokens = int(data.get('output_tokens', 0) or 0)
    tool_calls = int(data.get('tool_calls', 0) or 0)
    conversations = int(data.get('conversations', 0) or 0)

    output_token_score = min(40.0, output_tokens / 200.0)
    tool_call_score    = min(40.0, tool_calls * 2.0)
    conversation_score = min(20.0, conversations * 5.0)

    # Normalize the sub-scores so that they represent proportional weight
    # (keep raw sub-scores for breakdown, use weighted formula for value)
    raw_output = min(100.0, output_tokens / 200.0)
    raw_tools  = min(100.0, tool_calls * 2.0)
    raw_convs  = min(100.0, conversations * 5.0)

    output_token_score_bd = round(raw_output * 0.4, 2)
    tool_call_score_bd    = round(raw_tools  * 0.4, 2)
    conversation_score_bd = round(raw_convs  * 0.2, 2)

    value = clamp(output_token_score_bd + tool_call_score_bd + conversation_score_bd)
    
    breakdown_items = [
        {
            'name': 'output_token_score',
            'value': output_token_score_bd,
            'formula': f'output/200 × 0.4 = {output_tokens}/200 × 0.4 = {round(output_tokens/200*0.4, 2)} → max 40',
        },
        {
            'name': 'tool_call_score',
            'value': tool_call_score_bd,
            'formula': f'tools × 2 × 0.4 = {tool_calls} × 2 × 0.4 = {round(tool_calls*2*0.4, 2)} → max 40',
        },
        {
            'name': 'conversation_score',
            'value': conversation_score_bd,
            'formula': f'convs × 5 × 0.2 = {conversations} × 5 × 0.2 = {round(conversations*5*0.2, 2)} → max 20',
        },
    ]
    
    return {
        'value': value,
        'breakdown': breakdown_items,
        'source_data': {
            'output_tokens': output_tokens,
            'tool_calls': tool_calls,
            'conversations': conversations,
        },
        'formula':    'output_tokens(40) + tool_calls(40) + conversations(20)',
        'formula_zh': '输出Token(40) + 工具调用(40) + 对话轮次(20)',
    }


def calc_automation_score(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Automation score (max 100):
      cron_volume_score  (max 40):  cron_runs*5, capped at 40 pts
      success_rate_score (max 60):  cron_success/cron_runs * 60 pts

    Formula: cron_volume×0.4 + success_rate×0.6
    """
    cron_runs    = int(data.get('cron_runs', 0) or 0)
    cron_success = int(data.get('cron_success', 0) or 0)

    raw_volume = min(100.0, cron_runs * 5.0)
    cron_volume_score = round(raw_volume * 0.4, 2)

    if cron_runs > 0:
        raw_success_rate = (cron_success / cron_runs) * 100.0
    else:
        raw_success_rate = 0.0
    success_rate_score = round(raw_success_rate * 0.6, 2)

    success_rate = (cron_success / cron_runs * 100) if cron_runs > 0 else 0.0
    value = clamp(cron_volume_score + success_rate_score)
    
    breakdown_items = [
        {
            'name': 'cron_volume_score',
            'value': cron_volume_score,
            'formula': f'runs × 5 × 0.4 = {cron_runs} × 5 × 0.4 = {round(cron_runs*5*0.4, 2)} → max 40',
        },
        {
            'name': 'success_rate_score',
            'value': success_rate_score,
            'formula': f'success/runs × 0.6 = {cron_success}/{cron_runs} × 100 × 0.6 = {round(success_rate*0.6, 2)} → max 60',
        },
    ]
    
    return {
        'value': value,
        'breakdown': breakdown_items,
        'source_data': {
            'cron_runs': cron_runs,
            'cron_success': cron_success,
            'success_rate': round(success_rate, 1),
        },
        'formula':    'cron_volume×0.4 + success_rate×0.6',
        'formula_zh': '任务执行量×0.4 + 成功率×0.6',
    }


def calc_collaboration_score(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Collaboration score (max 100):
      collab_volume_score  (max 30):  collaborations*10, capped → ×0.3
      diversity_score      (max 30):  collab_agents*15,  capped → ×0.3
      success_rate_score   (max 40):  collab_success/collaborations × 0.4

    Formula: collab_volume×0.3 + diversity×0.3 + success_rate×0.4
    """
    collaborations = int(data.get('collaborations', 0) or 0)
    collab_success = int(data.get('collab_success', 0) or 0)
    collab_agents  = int(data.get('collab_agents', 0) or 0)

    raw_volume    = min(100.0, collaborations * 10.0)
    raw_diversity = min(100.0, collab_agents  * 15.0)

    collab_volume_score = round(raw_volume    * 0.3, 2)
    diversity_score     = round(raw_diversity * 0.3, 2)

    if collaborations > 0:
        raw_success_rate = (collab_success / collaborations) * 100.0
    else:
        raw_success_rate = 0.0
    success_rate_score = round(raw_success_rate * 0.4, 2)

    collab_success_rate = (collab_success / collaborations * 100) if collaborations > 0 else 0.0
    value = clamp(collab_volume_score + diversity_score + success_rate_score)
    
    breakdown_items = [
        {
            'name': 'collab_volume_score',
            'value': collab_volume_score,
            'formula': f'collabs × 10 × 0.3 = {collaborations} × 10 × 0.3 = {round(collaborations*10*0.3, 2)} → max 30',
        },
        {
            'name': 'diversity_score',
            'value': diversity_score,
            'formula': f'agents × 15 × 0.3 = {collab_agents} × 15 × 0.3 = {round(collab_agents*15*0.3, 2)} → max 30',
        },
        {
            'name': 'success_rate_score',
            'value': success_rate_score,
            'formula': f'success/collabs × 0.4 = {collab_success}/{collaborations} × 100 × 0.4 = {round(collab_success_rate*0.4, 2)} → max 40',
        },
    ]
    
    return {
        'value': value,
        'breakdown': breakdown_items,
        'source_data': {
            'collaborations': collaborations,
            'collab_success': collab_success,
            'collab_agents': collab_agents,
            'success_rate': round(collab_success_rate, 1),
        },
        'formula':    'collab_volume×0.3 + diversity×0.3 + success_rate×0.4',
        'formula_zh': '协作次数×0.3 + 多样性×0.3 + 成功率×0.4',
    }


def calc_accumulation_score(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Accumulation score (max 100):
      skills_score          (max 35):  skills_count*2, capped → ×0.35
      memory_score          (max 20):  memories_count*5, capped → ×0.2
      learnings_score       (max 20):  learnings_count*2.5, capped → ×0.2
      memory_sections_score (max 25):  memory_sections*8, capped → ×0.25

    Formula: skills×0.35 + memories×0.2 + learnings×0.2 + memory_sections×0.25
    """
    skills_count    = int(data.get('skills_count', 0) or 0)
    memories_count  = int(data.get('memories_count', 0) or 0)
    learnings_count = int(data.get('learnings_count', 0) or 0)
    memory_sections = int(data.get('memory_sections', 0) or 0)

    raw_skills    = min(100.0, skills_count    * 2.0)
    raw_memories  = min(100.0, memories_count  * 5.0)
    raw_learnings = min(100.0, learnings_count * 2.5)
    raw_sections  = min(100.0, memory_sections * 8.0)

    skills_score          = round(raw_skills    * 0.35, 2)
    memory_score          = round(raw_memories  * 0.20, 2)
    learnings_score       = round(raw_learnings * 0.20, 2)
    memory_sections_score = round(raw_sections  * 0.25, 2)

    value = clamp(skills_score + memory_score + learnings_score + memory_sections_score)
    
    breakdown_items = [
        {
            'name': 'skills_score',
            'value': skills_score,
            'formula': f'skills × 2 × 0.35 = {skills_count} × 2 × 0.35 = {round(skills_count*2*0.35, 2)} → max 35',
        },
        {
            'name': 'memory_score',
            'value': memory_score,
            'formula': f'memories × 5 × 0.2 = {memories_count} × 5 × 0.2 = {round(memories_count*5*0.2, 2)} → max 20',
        },
        {
            'name': 'learnings_score',
            'value': learnings_score,
            'formula': f'learnings × 2.5 × 0.2 = {learnings_count} × 2.5 × 0.2 = {round(learnings_count*2.5*0.2, 2)} → max 20',
        },
        {
            'name': 'memory_sections_score',
            'value': memory_sections_score,
            'formula': f'sections × 8 × 0.25 = {memory_sections} × 8 × 0.25 = {round(memory_sections*8*0.25, 2)} → max 25',
        },
    ]
    
    return {
        'value': value,
        'breakdown': breakdown_items,
        'source_data': {
            'skills_count': skills_count,
            'memories_count': memories_count,
            'learnings_count': learnings_count,
            'memory_sections': memory_sections,
        },
        'formula':    'skills×0.35 + memories×0.2 + learnings×0.2 + memory_sections×0.25',
        'formula_zh': '技能×0.35 + 记忆×0.2 + 学习×0.2 + 记忆章节×0.25',
    }


def calc_total_score(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Total score (max 100):
      efficiency×0.25 + output×0.25 + automation×0.20 + collaboration×0.15 + accumulation×0.15

    Accepts pre-computed score dicts or raw data dict.
    """
    # Accept pre-computed score dicts (from service) or compute inline
    eff_score   = data.get('efficiency_score_val')
    out_score   = data.get('output_score_val')
    auto_score  = data.get('automation_score_val')
    collab_score = data.get('collaboration_score_val')
    accum_score  = data.get('accumulation_score_val')

    if eff_score is None:
        eff_score   = calc_efficiency_score(data)['value']
    if out_score is None:
        out_score   = calc_output_score(data)['value']
    if auto_score is None:
        auto_score  = calc_automation_score(data)['value']
    if collab_score is None:
        collab_score = calc_collaboration_score(data)['value']
    if accum_score is None:
        accum_score  = calc_accumulation_score(data)['value']

    efficiency_part    = round(eff_score    * 0.25, 2)
    output_part        = round(out_score    * 0.25, 2)
    automation_part    = round(auto_score   * 0.20, 2)
    collaboration_part = round(collab_score * 0.15, 2)
    accumulation_part  = round(accum_score  * 0.15, 2)

    value = clamp(efficiency_part + output_part + automation_part + collaboration_part + accumulation_part)
    return {
        'value': value,
        'breakdown': {
            'efficiency':    efficiency_part,
            'output':        output_part,
            'automation':    automation_part,
            'collaboration': collaboration_part,
            'accumulation':  accumulation_part,
        },
        'formula':    'efficiency×0.25 + output×0.25 + automation×0.20 + collaboration×0.15 + accumulation×0.15',
        'formula_zh': '效率×0.25 + 产出×0.25 + 自动化×0.20 + 协作×0.15 + 积累×0.15',
    }


# ---------------------------------------------------------------------------
# Crayfish color system — based on total score
# ---------------------------------------------------------------------------

COLORS = [
    {'min': 80, 'hex': '#E84B3A', 'name': 'red',    'name_zh': '红色'},
    {'min': 60, 'hex': '#F5A623', 'name': 'orange', 'name_zh': '橙色'},
    {'min': 40, 'hex': '#4DB8A4', 'name': 'teal',   'name_zh': '青绿'},
    {'min': 20, 'hex': '#5B9BD5', 'name': 'blue',   'name_zh': '蓝色'},
    {'min':  0, 'hex': '#9B5DE5', 'name': 'purple', 'name_zh': '紫色'},
]


def get_claw_color_info(avg_score: float) -> Dict[str, Any]:
    """Return the color entry for the given total score."""
    for c in COLORS:
        if avg_score >= c['min']:
            return c
    return COLORS[-1]
