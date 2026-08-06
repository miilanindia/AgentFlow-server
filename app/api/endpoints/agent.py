from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel
import uuid
from app.services.agent_runner import agent_runner
from app.agent.control import task_control

router = APIRouter()

class AgentGoal(BaseModel):
    goal: str

@router.post("/start")
async def start_agent(payload: AgentGoal, background_tasks: BackgroundTasks):
    task_id = str(uuid.uuid4())
    
    # Agent ko sirf goal bhej rahe hain, baaki LLM khud decide karega
    background_tasks.add_task(agent_runner.run_agent, task_id, payload.goal)
    
    return {"task_id": task_id, "status": "started"}

@router.post("/{task_id}/approve")
async def approve_agent(task_id: str):
    agent_runner.approve_task(task_id)
    return {"task_id": task_id, "status": "approved"}

@router.post("/{task_id}/reject")
async def reject_agent(task_id: str):
    agent_runner.reject_task(task_id)
    return {"task_id": task_id, "status": "rejected"}

@router.post("/{task_id}/pause")
async def pause_agent(task_id: str):
    task_control.pause(task_id)
    return {"task_id": task_id, "status": "paused"}

@router.post("/{task_id}/resume")
async def resume_agent(task_id: str):
    task_control.resume(task_id)
    return {"task_id": task_id, "status": "resumed"}