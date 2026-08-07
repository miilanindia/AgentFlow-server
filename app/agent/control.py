import asyncio
import json
from typing import Dict
from app.core.config import settings
from app.core.logger import logger
import redis.asyncio as aioredis

_redis_client = None
_redis_loop_id = None

async def get_redis():
    global _redis_client, _redis_loop_id
    try:
        current_loop_id = id(asyncio.get_running_loop())
    except RuntimeError:
        current_loop_id = None

    if _redis_client is None or _redis_loop_id != current_loop_id:
        if _redis_client is not None:
            try:
                await _redis_client.close()
            except Exception:
                pass
        kwargs = {}
        if settings.REDIS_URL.startswith("rediss://"):
            kwargs["ssl_cert_reqs"] = "none"
        _redis_client = aioredis.from_url(settings.REDIS_URL, **kwargs)
        _redis_loop_id = current_loop_id
    return _redis_client


async def wait_for_approval(task_id: str) -> bool:
    """
    Subscribes to a Redis channel and blocks until 'approve' or 'reject' is received.
    """
    redis = await get_redis()
    pubsub = redis.pubsub()
    channel = f"control_{task_id}"
    await pubsub.subscribe(channel)
    logger.info(f"Task {task_id} waiting for approval on Redis channel {channel}...")
    
    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                data = json.loads(message["data"])
                if data.get("action") == "approve":
                    return True
                elif data.get("action") == "reject":
                    return False
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.close()


async def resolve_approval(task_id: str, approved: bool) -> bool:
    """Called by the API endpoint to publish the approval decision."""
    redis = await get_redis()
    channel = f"control_{task_id}"
    action = "approve" if approved else "reject"
    await redis.publish(channel, json.dumps({"action": action}))
    return True


class TaskControl:
    """Manages live task pause and resume states using Redis."""

    async def pause(self, task_id: str):
        redis = await get_redis()
        await redis.set(f"paused_{task_id}", "1")
        logger.info(f"Task {task_id} paused via Redis.")

    async def resume(self, task_id: str):
        redis = await get_redis()
        await redis.delete(f"paused_{task_id}")
        logger.info(f"Task {task_id} resumed via Redis.")

    async def is_paused(self, task_id: str) -> bool:
        redis = await get_redis()
        val = await redis.get(f"paused_{task_id}")
        return val == b"1"

    async def check_paused(self, task_id: str):
        """Called inside graph execution loops to block if paused."""
        redis = await get_redis()
        while await redis.get(f"paused_{task_id}") == b"1":
            await asyncio.sleep(1)

    def remove(self, task_id: str):
        # We can clean up the redis key in the background
        asyncio.create_task(self.resume(task_id))

task_control = TaskControl()
