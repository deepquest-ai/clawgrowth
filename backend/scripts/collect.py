#!/usr/bin/env python3
"""
ClawGrowth Data Collection Script

Features:
  1. Iterate through all agents
  2. Incrementally collect log data
  3. Update daily_snapshots and agent_profiles

Usage:
  python3 scripts/collect.py [agent_id]
  
  If agent_id is not specified, collect for all agents

Recommended cron schedule:
  0 * * * *  cd /path/to/backend && python3 scripts/collect.py
"""
import sys
import time
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import AGENTS_DIR
from service import run_collection_with_persist


def discover_agents() -> list:
    """Discover all agents."""
    if not AGENTS_DIR.exists():
        return []
    return sorted(d.name for d in AGENTS_DIR.iterdir() if d.is_dir())


def main():
    start = time.time()
    
    # Get list of agents to collect
    if len(sys.argv) > 1:
        agent_ids = [sys.argv[1]]
    else:
        agent_ids = discover_agents()
    
    print(f"[collect] Starting collection for {len(agent_ids)} agents...")
    
    results = []
    for agent_id in agent_ids:
        agent_start = time.time()
        result = run_collection_with_persist(agent_id)
        elapsed = time.time() - agent_start
        
        if result['ok']:
            print(f"  ✓ {agent_id}: +{result['tool_logs_inserted']} tools, "
                  f"+{result['cron_logs_inserted']} crons ({elapsed:.2f}s)")
        else:
            print(f"  ✗ {agent_id}: {result.get('error', 'unknown error')}")
        
        results.append(result)
    
    # Summary statistics
    success = sum(1 for r in results if r.get('ok'))
    total_tools = sum(r.get('tool_logs_inserted', 0) for r in results if r.get('ok'))
    total_crons = sum(r.get('cron_logs_inserted', 0) for r in results if r.get('ok'))
    
    print(f"[collect] Done: {success}/{len(agent_ids)} agents, "
          f"+{total_tools} tools, +{total_crons} crons "
          f"({time.time()-start:.2f}s total)")


if __name__ == '__main__':
    main()
