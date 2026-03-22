from fastapi import APIRouter
from service import build_agents_overview

router = APIRouter(tags=['agents'])

@router.get('/api/agents')
def get_agents():
    return build_agents_overview()
