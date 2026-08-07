import json
import asyncio
from typing import Dict, Any
from fastapi import WebSocket
from app.core.logger import logger
from app.core.config import settings
import redis.asyncio as aioredis

class ConnectionManager:
    def __init__(self):
        # Dictionary to map task_id to websocket connection
        self.active_connections: Dict[str, WebSocket] = {}
        self.redis_client = None
        self.redis_loop_id = None

    async def get_redis(self):
        try:
            current_loop_id = id(asyncio.get_running_loop())
        except RuntimeError:
            current_loop_id = None

        if self.redis_client is None or self.redis_loop_id != current_loop_id:
            if self.redis_client is not None:
                try:
                    await self.redis_client.close()
                except Exception:
                    pass
            kwargs = {}
            if settings.REDIS_URL.startswith("rediss://"):
                kwargs["ssl_cert_reqs"] = "none"
            self.redis_client = aioredis.from_url(settings.REDIS_URL, **kwargs)
            self.redis_loop_id = current_loop_id
        return self.redis_client

    async def connect(self, websocket: WebSocket, task_id: str):
        await websocket.accept()
        self.active_connections[task_id] = websocket
        logger.info(f"New client connected for Task: {task_id}")

    def disconnect(self, task_id: str):
        if task_id in self.active_connections:
            del self.active_connections[task_id]
            logger.info(f"Client disconnected for Task: {task_id}")

    async def publish_event(self, channel: str, event: dict):
        redis = await self.get_redis()
        try:
            await redis.publish(channel, json.dumps(event))
        except Exception as e:
            logger.error(f"Redis publish error: {e}")

    async def send_timeline_event(self, task_id: str, event_type: str, details: Dict[str, Any]):
        event = {
            "type": "timeline_event",
            "task_id": task_id,
            "event_type": event_type,
            "details": details
        }
        await self.publish_event(f"agentflow_{task_id}", event)

    async def send_screenshot_event(self, task_id: str, screenshot_base64: str):
        event = {
            "type": "screenshot_event",
            "task_id": task_id,
            "screenshot": f"data:image/png;base64,{screenshot_base64}"
        }
        await self.publish_event(f"agentflow_{task_id}", event)

    async def send_status_update(self, task_id: str, status: str, current_step: str):
        event = {
            "type": "status_update",
            "task_id": task_id,
            "status": status,
            "current_step": current_step
        }
        await self.publish_event(f"agentflow_{task_id}", event)

    async def _send_to_websocket_directly(self, task_id: str, event: dict):
        if task_id in self.active_connections:
            ws = self.active_connections[task_id]
            try:
                await ws.send_json(event)
            except Exception as e:
                logger.error(f"Error sending event to websocket for {task_id}: {e}")
                self.disconnect(task_id)

    async def listen_to_redis(self):
        redis = await self.get_redis()
        pubsub = redis.pubsub()
        await pubsub.psubscribe("agentflow_*")
        logger.info("[REDIS SUBSCRIBER] Started listening to 'agentflow_*' channels")
        try:
            async for message in pubsub.listen():
                if message["type"] == "pmessage":
                    channel = message["channel"].decode("utf-8")
                    task_id = channel.replace("agentflow_", "")
                    data = message["data"].decode("utf-8")
                    try:
                        event = json.loads(data)
                        await self._send_to_websocket_directly(task_id, event)
                    except json.JSONDecodeError:
                        logger.error("Failed to parse Redis message as JSON")
        except asyncio.CancelledError:
            logger.info("[REDIS SUBSCRIBER] Task cancelled.")
        finally:
            await pubsub.punsubscribe("agentflow_*")
            await pubsub.close()

# Singleton instance
ws_manager = ConnectionManager()