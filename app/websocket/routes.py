from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.websocket.manager import ws_manager
from app.core.logger import logger
import json

router = APIRouter()

@router.websocket("/ws/agent/{task_id}")
async def websocket_endpoint(websocket: WebSocket, task_id: str):
    await ws_manager.connect(websocket)
    try:
        while True:
            # Receive text or JSON messages from client if any (mostly for interactive commands or ping-pong)
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                logger.info(f"Received message from client: {message}")
                
                # Simple ping/pong echo fallback
                if message.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
            except json.JSONDecodeError:
                logger.warning(f"Received non-JSON message: {data}")
                await websocket.send_json({"type": "error", "message": "Invalid JSON format"})
                
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        ws_manager.disconnect(websocket)
