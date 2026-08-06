from typing import Dict, Any
from fastapi import WebSocket
from app.core.logger import logger

class ConnectionManager:
    def __init__(self):
        # Dictionary to map task_id to websocket connection
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, task_id: str):
        await websocket.accept()
        self.active_connections[task_id] = websocket
        logger.info(f"New client connected for Task: {task_id}")

    def disconnect(self, task_id: str):
        if task_id in self.active_connections:
            del self.active_connections[task_id]
            logger.info(f"Client disconnected for Task: {task_id}")

    async def send_timeline_event(self, task_id: str, event_type: str, details: Dict[str, Any]):
        if task_id in self.active_connections:
            ws = self.active_connections[task_id]
            event = {
                "type": "timeline_event",
                "task_id": task_id,
                "event_type": event_type,  # info, action, error, approval_required, complete
                "details": details
            }
            try:
                await ws.send_json(event)
            except Exception as e:
                logger.error(f"Error sending timeline to {task_id}: {e}")
                self.disconnect(task_id)

    async def send_screenshot_event(self, task_id: str, screenshot_base64: str):
        if task_id in self.active_connections:
            ws = self.active_connections[task_id]
            event = {
                "type": "screenshot_event",
                "task_id": task_id,
                "screenshot": f"data:image/png;base64,{screenshot_base64}"
            }
            try:
                await ws.send_json(event)
            except Exception as e:
                logger.error(f"Error sending screenshot to {task_id}: {e}")
                self.disconnect(task_id)

    async def send_status_update(self, task_id: str, status: str, current_step: str):
        if task_id in self.active_connections:
            ws = self.active_connections[task_id]
            event = {
                "type": "status_update",
                "task_id": task_id,
                "status": status,
                "current_step": current_step
            }
            try:
                await ws.send_json(event)
            except Exception as e:
                logger.error(f"Error sending status to {task_id}: {e}")
                self.disconnect(task_id)

# Singleton instance
ws_manager = ConnectionManager()