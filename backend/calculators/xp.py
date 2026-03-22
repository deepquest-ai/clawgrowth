from typing import Any, Dict, Tuple


def calc_daily_xp(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Calculate daily XP and return a full breakdown dict.

    XP sources:
      conversations  × 1
      tool_calls     × 2
      cron_success   × 10
      collab_success × 20
      skills above 20 threshold × 30 each
      has_today_memory (bool/int) × 5   — fixed: was min(1, memories_count)×5
      learnings_count × 10

    Returns dict with total and per-source breakdown.
    """
    c    = int(data.get('conversations', 0) or 0)
    tc   = int(data.get('tool_calls', 0) or 0)
    cs   = int(data.get('cron_success', 0) or 0)
    cls_ = int(data.get('collab_success', 0) or 0)

    # Skills above threshold: each skill beyond 20 base earns XP
    skills_count = int(data.get('skills_count', 0) or 0)
    skills = max(0, skills_count - 20)

    # Bug fix: old code used min(1, memories_count)*5 which always fires
    # if any memory exists regardless of date. Use has_today_memory instead.
    has_memory = data.get('has_today_memory', False)
    memory_today = 1 if has_memory else 0

    learn = int(data.get('learnings_count', 0) or 0)

    from_conversations = c    * 1
    from_tools         = tc   * 2
    from_cron_success  = cs   * 10
    from_collaborations = cls_ * 20
    from_skills        = skills * 30
    from_memory         = memory_today  * 5
    from_learnings     = learn  * 10

    total = (
        from_conversations
        + from_tools
        + from_cron_success
        + from_collaborations
        + from_skills
        + from_memory
        + from_learnings
    )

    # Build breakdown with formulas
    breakdown = [
        {
            'name': 'from_conversations',
            'value': from_conversations,
            'formula': f'{c} × 1 = +{from_conversations}',
        },
        {
            'name': 'from_tools',
            'value': from_tools,
            'formula': f'{tc} × 2 = +{from_tools}',
        },
        {
            'name': 'from_cron_success',
            'value': from_cron_success,
            'formula': f'{cs} × 10 = +{from_cron_success}',
        },
        {
            'name': 'from_collaborations',
            'value': from_collaborations,
            'formula': f'{cls_} × 20 = +{from_collaborations}',
        },
        {
            'name': 'from_skills',
            'value': from_skills,
            'formula': f'({skills_count} - 20) × 30 = {skills} × 30 = +{from_skills}',
        },
        {
            'name': 'from_memory',
            'value': from_memory,
            'formula': f'has_today_memory={1 if has_memory else 0} × 5 = +{from_memory}',
        },
        {
            'name': 'from_learnings',
            'value': from_learnings,
            'formula': f'{learn} × 10 = +{from_learnings}',
        },
    ]

    return {
        'total':               total,
        'from_conversations':  from_conversations,
        'from_tools':          from_tools,
        'from_cron_success':   from_cron_success,
        'from_collaborations': from_collaborations,
        'from_skills':         from_skills,
        'from_memory':          from_memory,
        'from_learnings':      from_learnings,
        'breakdown':           breakdown,
        'source_data': {
            'conversations': c,
            'tool_calls': tc,
            'cron_success': cs,
            'collab_success': cls_,
            'skills_count': skills_count,
            'skills_above_base': skills,
            'has_today_memory': has_memory,
            'learnings_count': learn,
        },
        'formula': 'conversations×1 + tools×2 + cron×10 + collab×20 + skills×30 + memory×5 + learnings×10',
        'formula_zh': '对话×1 + 工具×2 + Cron成功×10 + 协作×20 + 技能×30 + 记忆×5 + 学习×10',
    }


def calc_level(total_xp: int) -> Tuple[int, str, int]:
    """
    Compute level, stage and next level XP threshold from cumulative XP.

    Returns (level, stage, next_level_xp).
    
    Level thresholds (per algorithm-rules.md §3.2):
    Level 1-5:   0, 100, 250, 450, 700        (baby)
    Level 6-10:  1000, 1400, 1900, 2500, 3200 (growing)
    Level 11-15: 4000, 5000, 6200, 7600, 9200 (mature)
    Level 16-20: 11000, 13000, 15500, 18500, 22000 (expert)
    Level 21+:   26000                        (legend)
    """
    thresholds = [
        0,      # Level 1
        100,    # Level 2
        250,    # Level 3
        450,    # Level 4
        700,    # Level 5
        1000,   # Level 6
        1400,   # Level 7
        1900,   # Level 8
        2500,   # Level 9
        3200,   # Level 10
        4000,   # Level 11
        5000,   # Level 12
        6200,   # Level 13
        7600,   # Level 14
        9200,   # Level 15
        11000,  # Level 16
        13000,  # Level 17
        15500,  # Level 18
        18500,  # Level 19
        22000,  # Level 20
        26000,  # Level 21
    ]
    
    level = 1
    for idx, threshold in enumerate(thresholds, start=1):
        if total_xp >= threshold:
            level = idx

    if level <= 5:
        stage = 'baby'
    elif level <= 10:
        stage = 'growing'
    elif level <= 15:
        stage = 'mature'
    elif level <= 20:
        stage = 'expert'
    else:
        stage = 'legend'

    # next_level_xp is the threshold for the NEXT level
    if level < len(thresholds):
        next_threshold = thresholds[level]  # level is 1-indexed, thresholds is 0-indexed
    else:
        next_threshold = thresholds[-1]  # Already max level
    
    return level, stage, next_threshold
