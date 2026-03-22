from fastapi import APIRouter

from service import build_history

router = APIRouter(tags=['history'])


@router.get('/api/history/{agent_id}')
def get_history(agent_id: str, days: int = 30):
    return build_history(agent_id, days)
