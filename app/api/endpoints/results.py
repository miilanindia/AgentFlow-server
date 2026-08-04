from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime

router = APIRouter()

# class JobResultMockResponse(BaseModel):
#     id: uuid.UUID
#     task_id: uuid.UUID
#     status: str
#     output: Optional[Dict[str, Any]] = None
#     error_message: Optional[str] = None
#     created_at: datetime

# @router.get("", response_model=List[JobResultMockResponse])
# async def get_results(limit: int = 10):
#     # Return mock results list
#     mock_id = uuid.uuid4()
#     mock_task_id = uuid.uuid4()
#     return [
#         JobResultMockResponse(
#             id=mock_id,
#             task_id=mock_task_id,
#             status="completed",
#             output={"extracted_data": "example data", "screenshot_url": "/mock/screenshot.png"},
#             error_message=None,
#             created_at=datetime.utcnow()
#         )
#     ]

@router.get("/")
async def get_all_results():
    return {"message": "Results are streamed live via WebSocket. No static mock data."}