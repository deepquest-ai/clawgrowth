"""
app.py — ClawGrowth FastAPI application entry point.

All routes are defined inline here. No separate router files are needed.

Endpoints:
  GET  /health                           — liveness check
  GET  /api/agents                       — all agents overview
  GET  /api/agent/{agent_id}             — full agent detail
  GET  /api/agent/{agent_id}/history     — historical snapshots (?days=30)
  GET  /api/shared                       — shared workspace stats
  POST /api/collect/{agent_id}           — trigger manual collection
  POST /api/collect-all                  — trigger collection for all agents
  POST /api/cleanup                      — cleanup old data
  GET  /api/scheduler/status             — scheduler status

Built-in Scheduler:
  - Hourly: collect data for all agents
  - Daily 03:00: cleanup old data (7d tools, 30d crons) + vacuum
"""
import asyncio
import logging
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Query, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from starlette.requests import Request
from pydantic import BaseModel

from config import (
    AGENTS_DIR, HOST, PORT,
    SCHEDULER_ENABLED, COLLECT_HOURLY, CLEANUP_HOUR,
    TOOL_RETENTION_DAYS, CRON_RETENTION_DAYS,
    create_session, verify_token, revoke_token, change_password,
)
from database import init_db
from service import (
    build_agent_detail,
    build_agents_overview,
    build_history,
    cleanup_old_data,
    run_collection,
    run_collection_with_persist,
    vacuum_database,
)
from collectors.workspace_scanner import scan_shared_workspace

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
logger = logging.getLogger('clawgrowth')


# ---------------------------------------------------------------------------
# Scheduler State
# ---------------------------------------------------------------------------

class SchedulerState:
    """Track scheduler status for API exposure."""
    def __init__(self):
        self.enabled = True
        self.last_collect: Optional[str] = None
        self.last_cleanup: Optional[str] = None
        self.collect_count = 0
        self.cleanup_count = 0
        self.last_collect_result: Optional[dict] = None
        self.last_cleanup_result: Optional[dict] = None

scheduler_state = SchedulerState()


# ---------------------------------------------------------------------------
# Background Tasks
# ---------------------------------------------------------------------------

def discover_agents() -> list:
    """Discover all agent directories."""
    if not AGENTS_DIR.exists():
        return []
    return sorted(d.name for d in AGENTS_DIR.iterdir() if d.is_dir())


async def collect_all_agents() -> dict:
    """Run collection for all agents (async wrapper)."""
    agent_ids = discover_agents()
    results = []
    
    for agent_id in agent_ids:
        try:
            result = run_collection_with_persist(agent_id)
            results.append(result)
        except Exception as e:
            results.append({'ok': False, 'agent_id': agent_id, 'error': str(e)})
    
    summary = {
        'ok': True,
        'agents_total': len(agent_ids),
        'agents_success': sum(1 for r in results if r.get('ok')),
        'tool_logs_inserted': sum(r.get('tool_logs_inserted', 0) for r in results if r.get('ok')),
        'cron_logs_inserted': sum(r.get('cron_logs_inserted', 0) for r in results if r.get('ok')),
        'timestamp': datetime.now().isoformat(),
    }
    
    scheduler_state.last_collect = summary['timestamp']
    scheduler_state.collect_count += 1
    scheduler_state.last_collect_result = summary
    
    return summary


async def run_cleanup() -> dict:
    """Run cleanup task (async wrapper)."""
    result = cleanup_old_data(tool_days=TOOL_RETENTION_DAYS, cron_days=CRON_RETENTION_DAYS)
    
    if result.get('ok'):
        vac_result = vacuum_database()
        result['vacuum'] = vac_result.get('ok', False)
    
    result['timestamp'] = datetime.now().isoformat()
    
    scheduler_state.last_cleanup = result['timestamp']
    scheduler_state.cleanup_count += 1
    scheduler_state.last_cleanup_result = result
    
    return result


async def scheduler_loop():
    """
    Background scheduler running hourly collection and daily cleanup.
    
    Schedule (configurable via environment):
      - Every hour at :00 → collect all agents (if COLLECT_HOURLY)
      - Every day at CLEANUP_HOUR:00 → cleanup + vacuum
    """
    if not SCHEDULER_ENABLED:
        logger.info('[Scheduler] Scheduler disabled via config')
        return
    
    logger.info(f'[Scheduler] Started (collect_hourly={COLLECT_HOURLY}, cleanup_hour={CLEANUP_HOUR}:00)')
    
    while scheduler_state.enabled:
        try:
            now = datetime.now()
            
            # Hourly collection (at minute 0)
            if COLLECT_HOURLY and now.minute == 0:
                logger.info('[Scheduler] Running hourly collection...')
                result = await collect_all_agents()
                logger.info(f'[Scheduler] Collection done: {result["agents_success"]}/{result["agents_total"]} agents, '
                           f'+{result["tool_logs_inserted"]} tools, +{result["cron_logs_inserted"]} crons')
            
            # Daily cleanup at configured hour
            if now.hour == CLEANUP_HOUR and now.minute == 0:
                logger.info('[Scheduler] Running daily cleanup...')
                result = await run_cleanup()
                logger.info(f'[Scheduler] Cleanup done: deleted {result.get("tool_call_logs_deleted", 0)} tools, '
                           f'{result.get("cron_run_logs_deleted", 0)} crons, vacuum={result.get("vacuum", False)}')
            
            # Sleep until next minute
            await asyncio.sleep(60 - datetime.now().second)
            
        except asyncio.CancelledError:
            logger.info('[Scheduler] Scheduler cancelled')
            break
        except Exception as e:
            logger.error(f'[Scheduler] Error: {e}')
            await asyncio.sleep(60)


# ---------------------------------------------------------------------------
# App initialization
# ---------------------------------------------------------------------------

app = FastAPI(
    title='ClawGrowth API',
    version='2.1.0',
    description='OpenClaw Agent Growth & Metrics Dashboard',
)

# Store scheduler task reference
_scheduler_task: Optional[asyncio.Task] = None


@app.on_event('startup')
async def startup_event():
    """Startup lifecycle."""
    global _scheduler_task
    init_db()
    logger.info('[Startup] Database initialized')
    
    # Start scheduler (use ensure_future for Python 3.6 compatibility)
    _scheduler_task = asyncio.ensure_future(scheduler_loop())
    logger.info('[Startup] Scheduler started')


@app.on_event('shutdown')
async def shutdown_event():
    """Shutdown lifecycle."""
    global _scheduler_task
    scheduler_state.enabled = False
    if _scheduler_task:
        _scheduler_task.cancel()
        try:
            await _scheduler_task
        except asyncio.CancelledError:
            pass
    logger.info('[Shutdown] Scheduler stopped')

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get('/health')
def health() -> dict:
    """Liveness probe."""
    return {'ok': True}


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    password: str

class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


def get_current_token(authorization: str = Header(None)) -> str:
    """Extract and verify token from Authorization header."""
    if not authorization:
        raise HTTPException(status_code=401, detail='Authorization header required')
    
    # Support both "Bearer <token>" and plain "<token>"
    token = authorization
    if authorization.startswith('Bearer '):
        token = authorization[7:]
    
    if not verify_token(token):
        raise HTTPException(status_code=401, detail='Invalid or expired token')
    
    return token


@app.post('/api/auth/login')
def login(req: LoginRequest) -> dict:
    """Login and get session token."""
    success, result = create_session(req.password)
    if not success:
        raise HTTPException(status_code=401, detail=result)
    return {'ok': True, 'token': result}


@app.post('/api/auth/logout')
def logout(authorization: str = Header(None)) -> dict:
    """Logout and revoke token."""
    if authorization:
        token = authorization[7:] if authorization.startswith('Bearer ') else authorization
        revoke_token(token)
    return {'ok': True}


@app.post('/api/auth/change-password')
def api_change_password(req: ChangePasswordRequest, token: str = None) -> dict:
    """Change password (requires valid token or correct old password)."""
    success, message = change_password(req.old_password, req.new_password)
    if not success:
        raise HTTPException(status_code=400, detail=message)
    return {'ok': True, 'message': message}


@app.get('/api/auth/check')
def check_auth(authorization: str = Header(None)) -> dict:
    """Check if token is valid."""
    if not authorization:
        return {'authenticated': False}
    
    token = authorization[7:] if authorization.startswith('Bearer ') else authorization
    return {'authenticated': verify_token(token)}


# ---------------------------------------------------------------------------
# Agents overview
# ---------------------------------------------------------------------------

@app.get('/api/agents')
def get_agents_overview() -> dict:
    """Return an overview of all agents with summary stats."""
    return build_agents_overview()


# ---------------------------------------------------------------------------
# Agent detail
# ---------------------------------------------------------------------------

@app.get('/api/agent/{agent_id}')
def get_agent_detail(agent_id: str) -> dict:
    """Return full detail for a single agent including scores, status, XP, workspace."""
    return build_agent_detail(agent_id)


# ---------------------------------------------------------------------------
# Agent history
# ---------------------------------------------------------------------------

@app.get('/api/agent/{agent_id}/history')
def get_agent_history(
    agent_id: str,
    days: int = Query(default=30, ge=1, le=365),
) -> dict:
    """Return historical daily snapshots for an agent."""
    return build_history(agent_id, days)


# ---------------------------------------------------------------------------
# Shared workspace stats
# ---------------------------------------------------------------------------

@app.get('/api/shared')
def get_shared() -> dict:
    """Return shared workspace stats (commander / cross-agent)."""
    return scan_shared_workspace()


# ---------------------------------------------------------------------------
# Trigger collection
# ---------------------------------------------------------------------------

@app.post('/api/collect/{agent_id}')
def collect(agent_id: str) -> dict:
    """Trigger a manual data collection cycle for an agent."""
    return run_collection(agent_id)


@app.post('/api/collect-all')
async def collect_all() -> dict:
    """Trigger collection for all agents."""
    return await collect_all_agents()


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

@app.post('/api/cleanup')
async def cleanup(
    tool_days: int = Query(default=7, ge=1, le=365),
    cron_days: int = Query(default=30, ge=1, le=365),
    vacuum: bool = Query(default=False),
) -> dict:
    """Cleanup old data from database."""
    result = cleanup_old_data(tool_days=tool_days, cron_days=cron_days)
    if vacuum and result.get('ok'):
        vac_result = vacuum_database()
        result['vacuum'] = vac_result.get('ok', False)
    return result


# ---------------------------------------------------------------------------
# Scheduler status
# ---------------------------------------------------------------------------

@app.get('/api/scheduler/status')
def get_scheduler_status() -> dict:
    """Return scheduler status."""
    return {
        'enabled': scheduler_state.enabled,
        'collect_count': scheduler_state.collect_count,
        'cleanup_count': scheduler_state.cleanup_count,
        'last_collect': scheduler_state.last_collect,
        'last_cleanup': scheduler_state.last_cleanup,
        'last_collect_result': scheduler_state.last_collect_result,
        'last_cleanup_result': scheduler_state.last_cleanup_result,
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT)
