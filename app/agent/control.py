import asyncio
from typing import Dict

# Ek task_id ke against ek hi pending approval hoti hai us waqt
_approval_events: Dict[str, asyncio.Event] = {}
_approval_results: Dict[str, bool] = {}


async def wait_for_approval(task_id: str) -> bool:
    """
    Yeh function approval_node ke ANDAR se call hota hai (node khud yahi pe block
    karta hai). Jab tak /approve ya /reject endpoint hit nahi hota, yeh wapas
    nahi aata. Isse graph ka apna internal state (is_approved) sahi update hota
    hai, aur infinite 'approve -> approve -> approve' loop nahi banta.
    """
    event = asyncio.Event()
    _approval_events[task_id] = event
    try:
        await event.wait()
        return _approval_results.pop(task_id, False)
    finally:
        _approval_events.pop(task_id, None)


def resolve_approval(task_id: str, approved: bool) -> bool:
    """Called by the /approve or /reject endpoint. Returns False if no approval was pending."""
    event = _approval_events.get(task_id)
    if not event:
        return False
    _approval_results[task_id] = approved
    event.set()
    return True

class TaskControl:
    """Manages live task pause and resume states using asyncio.Event objects."""
    def __init__(self):
        self._running_events: Dict[str, asyncio.Event] = {}

    def get_event(self, task_id: str) -> asyncio.Event:
        if task_id not in self._running_events:
            event = asyncio.Event()
            event.set()
            self._running_events[task_id] = event
        return self._running_events[task_id]

    def pause(self, task_id: str):
        event = self.get_event(task_id)
        event.clear()

    def resume(self, task_id: str):
        event = self.get_event(task_id)
        event.set()

    def is_paused(self, task_id: str) -> bool:
        event = self.get_event(task_id)
        return not event.is_set()

    async def check_paused(self, task_id: str):
        event = self.get_event(task_id)
        if not event.is_set():
            await event.wait()

    def remove(self, task_id: str):
        self._running_events.pop(task_id, None)

task_control = TaskControl()
