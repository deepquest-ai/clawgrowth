from fastapi import APIRouter

from service import build_today_stats, build_extended_stats, run_collection

router = APIRouter(tags=['stats'])


@router.get('/api/stats/{agent_id}/today')
def get_today_stats(agent_id: str):
    return build_extended_stats(agent_id)


@router.post('/api/collect/{agent_id}')
def collect_now(agent_id: str):
    return run_collection(agent_id)
