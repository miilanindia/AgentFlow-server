from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from typing import List, Optional, Dict, Any
import uuid

from app.database.session import get_db
from app.database.models import Task, JobResult, TimelineEvent, User
from app.core.auth import get_current_user

router = APIRouter()

@router.get("/")
async def get_all_results(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(Task)
        .where(Task.user_id == current_user.id)
        .options(selectinload(Task.job_result), selectinload(Task.timeline_events))
    )
    tasks = result.scalars().all()
    return [
        {
            "task_id": str(t.id),
            "description": t.description,
            "prompt": t.description,  # Frontend expected key
            "status": t.status,
            "created_at": t.created_at,
            "job_result": t.job_result.output if t.job_result else None,
            "error_message": t.job_result.error_message if t.job_result else None,
            "timeline_events_count": len(t.timeline_events),
            "itemsCount": len(t.job_result.output.get("jobs", [])) if (t.job_result and isinstance(t.job_result.output, dict) and "jobs" in t.job_result.output) else 0  # Frontend expected key
        }
        for t in tasks
    ]

@router.get("/{task_id}")
async def get_result_by_id(
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    try:
        task_uuid = uuid.UUID(task_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid task UUID format")
        
    result = await db.execute(
        select(Task)
        .where(Task.id == task_uuid, Task.user_id == current_user.id)
        .options(selectinload(Task.job_result), selectinload(Task.timeline_events))
    )
    task = result.scalars().first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found or unauthorized")
        
    return {
        "task_id": str(task.id),
        "description": task.description,
        "status": task.status,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
        "job_result": task.job_result.output if task.job_result else None,
        "error_message": task.job_result.error_message if task.job_result else None,
        "timeline_events": [
            {
                "event_type": ev.event_type,
                "details": ev.details,
                "created_at": ev.created_at
            }
            for ev in task.timeline_events
        ]
    }