from fastapi import APIRouter
from app.api.endpoints import agent, results

api_router = APIRouter()

api_router.include_router(agent.router, prefix="/agent", tags=["Agent"])
api_router.include_router(results.router, prefix="/results", tags=["Results"])
