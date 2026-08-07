from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from app.websocket.manager import ws_manager
from app.core.logger import logger
from app.core.auth import decode_access_token
from app.database.database import AsyncSessionLocal
from app.database.models import Task
from sqlalchemy.future import select
import json
import uuid
import asyncio

router = APIRouter()


async def _authorize_ws(websocket: WebSocket, task_id: str) -> bool:
    """Token query param se user verify karo, aur check karo ki task usi user ka hai."""
    token = websocket.query_params.get("token")
    if not token:
        return False
    try:
        payload = decode_access_token(token)
    except Exception:
        return False

    user_id = payload.get("sub")
    if not user_id:
        return False

    try:
        task_uuid = uuid.UUID(task_id)
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        return False

    for attempt in range(10):
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Task).where(Task.id == task_uuid)
            )
            task = result.scalars().first()

        if task is not None:
            return task.user_id == user_uuid

        await asyncio.sleep(0.5)

    return False
@router.websocket("/ws/agent/{task_id}")
async def websocket_endpoint(websocket: WebSocket, task_id: str):
    authorized = await _authorize_ws(websocket, task_id)
    if not authorized:
        # Connection accept karne se pehle hi reject karo
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        logger.warning(f"Unauthorized WS connection attempt for Task: {task_id}")
        return

    await ws_manager.connect(websocket, task_id)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                logger.info(f"Received message from client: {message}")
                if message.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
            except json.JSONDecodeError:
                logger.warning(f"Received non-JSON message: {data}")
                await websocket.send_json({"type": "error", "message": "Invalid JSON format"})

    except WebSocketDisconnect:
        ws_manager.disconnect(task_id)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        ws_manager.disconnect(task_id)