from fastapi import APIRouter, HTTPException

from service import build_agent_profile

router = APIRouter(prefix='/api/agent', tags=['agent'])


@router.get('/{agent_id}')
def get_agent(agent_id: str):
    profile = build_agent_profile(agent_id)
    if not profile:
        raise HTTPException(status_code=404, detail='Agent not found')
    return profile
