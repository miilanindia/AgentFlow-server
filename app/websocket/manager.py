from typing import List, Dict, Any
from fastapi import WebSocket
from app.core.logger import logger
import json

class ConnectionManager:
    def __init__(self):
        # Keeps track of all active websocket connections
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"New client connected. Active connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"Client disconnected. Active connections: {len(self.active_connections)}")

    async def send_personal_message(self, message: Dict[str, Any], websocket: WebSocket):
        await websocket.send_json(message)

    async def broadcast(self, message: Dict[str, Any]):
        logger.debug(f"Broadcasting message: {message}")
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error broadcasting to client: {e}")
                # Clean up stale connections during broadcast
                self.disconnect(connection)

    async def send_timeline_event(self, task_id: str, event_type: str, details: Dict[str, Any], websocket: WebSocket = None):
        event = {
            "type": "timeline_event",
            "task_id": task_id,
            "event_type": event_type,
            "details": details
        }
        if websocket:
            await self.send_personal_message(event, websocket)
        else:
            await self.broadcast(event)

    async def send_screenshot_event(self, task_id: str, screenshot_base64: str, websocket: WebSocket = None):
        event = {
            "type": "screenshot_event",
            "task_id": task_id,
            "screenshot": screenshot_base64
        }
        if websocket:
            await self.send_personal_message(event, websocket)
        else:
            await self.broadcast(event)

    async def send_status_update(self, task_id: str, status: str, current_step: str, websocket: WebSocket = None):
        event = {
            "type": "status_update",
            "task_id": task_id,
            "status": status,
            "current_step": current_step
        }
        if websocket:
            await self.send_personal_message(event, websocket)
        else:
            await self.broadcast(event)

ws_manager = ConnectionManager()
