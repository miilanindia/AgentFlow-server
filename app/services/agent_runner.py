import asyncio
from typing import Dict
from app.websocket.manager import ws_manager
from app.core.logger import logger

class AgentRunner:
    def __init__(self):
        self.approval_events: Dict[str, asyncio.Event] = {}

    def approve_task(self, task_id: str):
        if task_id in self.approval_events:
            self.approval_events[task_id].set()
            logger.info(f"Task {task_id} approved by user.")

    async def run_agent(self, task_id: str, goal: str):
        logger.info(f"Starting agent runner simulation for task: {task_id}, goal: {goal}")
        self.approval_events[task_id] = asyncio.Event()

        def make_svg(text: str, status_text: str = "ACTIVE"):
            svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="800" height="600">
                <rect width="100%" height="100%" fill="%2309090b"/>
                <rect x="20" y="20" width="760" height="560" rx="10" fill="%2318181b" stroke="%2327272a" stroke-width="2"/>
                <!-- Browser Header -->
                <circle cx="50" cy="50" r="6" fill="%23ef4444"/>
                <circle cx="70" cy="50" r="6" fill="%23eab308"/>
                <circle cx="90" cy="50" r="6" fill="%2322c55e"/>
                <rect x="120" y="38" width="500" height="24" rx="5" fill="%2309090b" stroke="%2327272a"/>
                <text x="130" y="54" fill="%23a1a1aa" font-size="11" font-family="monospace">https://browser-agent.flow/run/{task_id}</text>
                <rect x="630" y="38" width="80" height="24" rx="5" fill="%2322c55e" opacity="0.2"/>
                <text x="670" y="54" dominant-baseline="middle" text-anchor="middle" fill="%2322c55e" font-size="10" font-family="sans-serif" font-weight="bold">{status_text}</text>
                
                <!-- Browser Content -->
                <text x="400" y="220" dominant-baseline="middle" text-anchor="middle" fill="%233b82f6" font-size="64">🤖</text>
                <text x="400" y="300" dominant-baseline="middle" text-anchor="middle" fill="%23f4f4f5" font-size="22" font-family="sans-serif" font-weight="bold">{text}</text>
                <text x="400" y="340" dominant-baseline="middle" text-anchor="middle" fill="%2371717a" font-size="14" font-family="sans-serif">Goal: {goal[:50]}...</text>
                
                <!-- Stats Box -->
                <rect x="200" y="400" width="400" height="80" rx="8" fill="%2309090b" stroke="%2327272a"/>
                <text x="250" y="435" fill="%2371717a" font-size="11" font-family="sans-serif">STEPS COMPLETED</text>
                <text x="250" y="465" fill="%233b82f6" font-size="20" font-family="monospace" font-weight="bold">2 / 4</text>
                <text x="480" y="435" fill="%2371717a" font-size="11" font-family="sans-serif">TOKENS USED</text>
                <text x="480" y="465" fill="%2322c55e" font-size="20" font-family="monospace" font-weight="bold">1,420</text>
            </svg>"""
            svg_clean = "".join([line.strip() for line in svg.split("\n")])
            return f"data:image/svg+xml;utf8,{svg_clean}"

        try:
            # Step 1: Navigating
            await asyncio.sleep(2)
            await ws_manager.send_status_update(task_id, "running", "Navigating to target site")
            await ws_manager.send_timeline_event(task_id, "navigating", {"message": "Navigating to LinkedIn Job search for Python developers"})
            await ws_manager.send_screenshot_event(task_id, make_svg("Navigating to LinkedIn..."))

            # Step 2: Extracting
            await asyncio.sleep(3)
            await ws_manager.send_status_update(task_id, "running", "Extracting job listings")
            await ws_manager.send_timeline_event(task_id, "extracting", {"message": "Scraped: Stripe | Staff Python Engineer | $185,000 | Hybrid"})
            await ws_manager.send_screenshot_event(task_id, make_svg("Extracting job listings from page..."))

            # Step 3: Awaiting Approval (Human Checkpoint)
            await asyncio.sleep(2)
            await ws_manager.send_status_update(task_id, "pending_approval", "Awaiting human operator approval")
            await ws_manager.send_timeline_event(task_id, "approval_required", {"message": "Checkpoint reached: Please verify if the listing extraction is correct"})
            await ws_manager.send_screenshot_event(task_id, make_svg("Awaiting Human Approval", "PAUSED"))

            # Wait for the approval event to be set
            logger.info(f"Task {task_id} is waiting for user approval...")
            await self.approval_events[task_id].wait()

            # Step 4: Resume and Complete
            await ws_manager.send_status_update(task_id, "running", "Analyzing and compiling results")
            await ws_manager.send_timeline_event(task_id, "analyzing", {"message": "Human checkpoint approved. Resuming task execution..."})
            await ws_manager.send_screenshot_event(task_id, make_svg("Compiling results into final format..."))
            await asyncio.sleep(3)

            # Completed
            await ws_manager.send_status_update(task_id, "completed", "Task completed successfully")
            await ws_manager.send_timeline_event(task_id, "completed", {"message": "Finished all tasks successfully. Results compiled."})
            await ws_manager.send_screenshot_event(task_id, make_svg("Task Completed Successfully!", "DONE"))

        except Exception as e:
            logger.error(f"Error in agent runner simulation: {e}")
            await ws_manager.send_status_update(task_id, "failed", f"Failed: {str(e)}")
            await ws_manager.send_timeline_event(task_id, "error", {"message": f"Execution failed: {str(e)}"})
        finally:
            if task_id in self.approval_events:
                del self.approval_events[task_id]

agent_runner = AgentRunner()
