from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
import uuid
from app.database.session import get_db
from app.database.models import Task, User
from app.core.auth import get_current_user
from app.services.agent_runner import agent_runner
from app.agent.control import task_control
from app.tasks.celery_tasks import run_agent_task

router = APIRouter()

class AgentGoal(BaseModel):
    goal: str


async def _get_owned_task(task_id: str, current_user: User, db: AsyncSession) -> Task:
    """Helper: task fetch karo aur confirm karo ki wo isi user ka hai."""
    try:
        task_uuid = uuid.UUID(task_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid task UUID format")

    result = await db.execute(select(Task).where(Task.id == task_uuid, Task.user_id == current_user.id))
    task = result.scalars().first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found or unauthorized")
    return task

@router.post("/start")
async def start_agent(payload: AgentGoal,
    current_user: User = Depends(get_current_user)):
    task_id = str(uuid.uuid4())
    
    # Agent ko sirf goal bhej rahe hain, baaki LLM khud decide karega
    run_agent_task.delay(task_id, payload.goal, user_id=str(current_user.id))
    
    return {"task_id": task_id, "status": "started"}

@router.post("/{task_id}/approve")
async def approve_agent(task_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)):

    await _get_owned_task(task_id, current_user, db)
    await agent_runner.approve_task(task_id)
    return {"task_id": task_id, "status": "approved"}

@router.post("/{task_id}/reject")
async def reject_agent(task_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)):

    await _get_owned_task(task_id, current_user, db)
    await agent_runner.reject_task(task_id)
    return {"task_id": task_id, "status": "rejected"}

@router.post("/{task_id}/pause")
async def pause_agent(
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    await _get_owned_task(task_id, current_user, db)
    await task_control.pause(task_id)
    return {"task_id": task_id, "status": "paused"}


@router.post("/{task_id}/resume")
async def resume_agent(
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    await _get_owned_task(task_id, current_user, db)
    await task_control.resume(task_id)
    return {"task_id": task_id, "status": "resumed"}


@router.post("/{task_id}/cancel")
async def cancel_agent(
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    await _get_owned_task(task_id, current_user, db)
    await task_control.cancel(task_id)
    await agent_runner.reject_task(task_id) # Also unblock if waiting at approval node
    return {"task_id": task_id, "status": "cancelled"}