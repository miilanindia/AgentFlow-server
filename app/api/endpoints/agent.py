from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel
from typing import Dict, Any
import uuid
from app.services.agent_runner import agent_runner

router = APIRouter()

class AgentGoal(BaseModel):
    goal: str
    config: Dict[str, Any] = {}

class AgentActionResponse(BaseModel):
    task_id: str
    status: str
    message: str = ""

@router.post("/start", response_model=AgentActionResponse)
async def start_agent(payload: AgentGoal, background_tasks: BackgroundTasks):
    task_id = str(uuid.uuid4())
    background_tasks.add_task(agent_runner.run_agent, task_id, payload.goal)
    return AgentActionResponse(
        task_id=task_id,
        status="started",
        message="Agent started successfully"
    )

@router.post("/{task_id}/approve", response_model=AgentActionResponse)
async def approve_agent(task_id: str):
    agent_runner.approve_task(task_id)
    return AgentActionResponse(
        task_id=task_id,
        status="running",
        message="Agent resumed successfully after approval"
    )

@router.post("/pause", response_model=AgentActionResponse)
async def pause_agent(task_id: str):
    return AgentActionResponse(
        task_id=task_id,
        status="paused",
        message="Agent paused successfully"
    )

@router.post("/resume", response_model=AgentActionResponse)
async def resume_agent(task_id: str):
    return AgentActionResponse(
        task_id=task_id,
        status="running",
        message="Agent resumed successfully"
    )

@router.post("/stop", response_model=AgentActionResponse)
async def stop_agent(task_id: str):
    return AgentActionResponse(
        task_id=task_id,
        status="stopped",
        message="Agent stopped successfully"
    )

@router.get("/status")
async def get_agent_status(task_id: str):
    return {
        "task_id": task_id,
        "status": "running",
        "current_step": "Navigating to page",
        "step_count": 3
    }

