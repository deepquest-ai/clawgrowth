#!/usr/bin/env python3
"""
ClawGrowth Data Cleanup Script

Features:
  1. Clean expired tool_call_logs (default: keep 7 days)
  2. Clean expired cron_run_logs (default: keep 30 days)
  3. Run VACUUM to reclaim disk space

Usage:
  python3 scripts/cleanup.py [--tool-days N] [--cron-days N] [--vacuum]

Recommended cron schedule:
  0 3 * * *  cd /path/to/backend && python3 scripts/cleanup.py --vacuum
"""
import argparse
import sys
import time
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from service import cleanup_old_data, vacuum_database
from config import DB_PATH


def main():
    parser = argparse.ArgumentParser(description='ClawGrowth Data Cleanup')
    parser.add_argument('--tool-days', type=int, default=7,
                        help='Days to keep tool_call_logs (default: 7)')
    parser.add_argument('--cron-days', type=int, default=30,
                        help='Days to keep cron_run_logs (default: 30)')
    parser.add_argument('--vacuum', action='store_true',
                        help='Run VACUUM after cleanup to reclaim space')
    args = parser.parse_args()
    
    start = time.time()
    
    # Show current database size
    if DB_PATH.exists():
        size_mb = DB_PATH.stat().st_size / 1024 / 1024
        print(f"[cleanup] Database size before: {size_mb:.2f} MB")
    
    # Clean expired data
    print(f"[cleanup] Cleaning data older than {args.tool_days} days (tools) "
          f"and {args.cron_days} days (crons)...")
    
    result = cleanup_old_data(tool_days=args.tool_days, cron_days=args.cron_days)
    
    if result['ok']:
        print(f"  ✓ Deleted {result['tool_call_logs_deleted']} tool logs, "
              f"{result['cron_run_logs_deleted']} cron logs")
    else:
        print(f"  ✗ Error: {result.get('error', 'unknown')}")
        return 1
    
    # Run VACUUM
    if args.vacuum:
        print("[cleanup] Running VACUUM...")
        vac_result = vacuum_database()
        if vac_result['ok']:
            print("  ✓ VACUUM completed")
        else:
            print(f"  ✗ VACUUM failed: {vac_result.get('error', 'unknown')}")
    
    # Show size after cleanup
    if DB_PATH.exists():
        size_mb = DB_PATH.stat().st_size / 1024 / 1024
        print(f"[cleanup] Database size after: {size_mb:.2f} MB")
    
    print(f"[cleanup] Done ({time.time()-start:.2f}s)")
    return 0


if __name__ == '__main__':
    sys.exit(main())
