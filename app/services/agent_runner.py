import asyncio
import uuid
from typing import Dict, Any, List

from app.agent.graph import app_graph
from app.agent.control import resolve_approval, task_control
from app.browser.controller import browser_manager
from app.websocket.manager import ws_manager
from app.core.logger import logger
from app.database.database import AsyncSessionLocal
from app.database.models import Task, TimelineEvent, JobResult

async def db_create_task(task_id: str, goal: str):
    try:
        async with AsyncSessionLocal() as db:
            task_uuid = uuid.UUID(task_id)
            new_task = Task(id=task_uuid, description=goal, status="running")
            db.add(new_task)
            await db.commit()
            logger.info(f"[DB] Inserted Task record for {task_id}")
    except Exception as e:
        logger.error(f"[DB ERROR] Failed to create Task {task_id}: {e}")

async def db_add_timeline_event(task_id: str, event_type: str, details: dict):
    try:
        async with AsyncSessionLocal() as db:
            task_uuid = uuid.UUID(task_id)
            event = TimelineEvent(task_id=task_uuid, event_type=event_type, details=details)
            db.add(event)
            await db.commit()
    except Exception as e:
        logger.error(f"[DB ERROR] Failed to add TimelineEvent for Task {task_id}: {e}")

async def db_finalize_task(task_id: str, status: str, final_jobs: List[Dict[str, Any]] = None, error_msg: str = None):
    try:
        async with AsyncSessionLocal() as db:
            task_uuid = uuid.UUID(task_id)
            task = await db.get(Task, task_uuid)
            final_status = status or ("completed" if final_jobs is not None else "failed")
            
            if task:
                task.status = final_status
            
            if final_jobs is not None or error_msg is not None:
                job_result = JobResult(
                    id=uuid.uuid4(),
                    task_id=task_uuid,
                    status=final_status,
                    output={"jobs": final_jobs} if final_jobs is not None else None,
                    error_message=error_msg
                )
                db.add(job_result)
            await db.commit()
            logger.info(f"[DB] Finalized Task {task_id} with status='{final_status}'")
    except Exception as e:
        logger.error(f"[DB ERROR] Failed to finalize Task {task_id}: {e}")

class AgentRunner:
    def __init__(self):
        self.active_tasks = {}

    async def run_agent(self, task_id: str, goal: str):
        logger.info(f"[RUNNER] Starting agent execution for Task {task_id} with goal: '{goal}'")
        
        # 1. DB Row insertion at task start
        await db_create_task(task_id, goal)
        
        # 2. Live WebSocket timeline event
        await ws_manager.send_timeline_event(task_id, "info", {"message": f"Starting agent for goal: {goal}"})
        await db_add_timeline_event(task_id, "info", {"message": f"Starting agent for goal: {goal}"})
        await ws_manager.send_status_update(task_id, "running", "Initializing Browser")
        
        try:
            logger.info(f"[RUNNER] Initializing per-task browser controller for Task {task_id}...")
            browser_controller = await browser_manager.get_or_create(task_id)
            logger.info(f"[RUNNER] Browser controller ready for Task {task_id}.")
        except Exception as e:
            logger.exception(f"[RUNNER] Critical Error: Browser failed to start for Task {task_id}: {e}")
            await ws_manager.send_timeline_event(task_id, "error", {"message": f"Browser failed to start: {str(e)}"})
            await db_add_timeline_event(task_id, "error", {"message": f"Browser failed to start: {str(e)}"})
            await db_finalize_task(task_id, "failed", error_msg=str(e))
            return

        initial_state = {
            "task_id": task_id,
            "goal": goal,
            "messages": [],
            "extracted_jobs": [],
            "needs_approval": False,
            "is_approved": False,
            "tool_call_count": 0
        }
        
        task_status = "completed"
        final_jobs_delivered = []
        error_message = None
        
        logger.info(f"[RUNNER] Initial state configured. Invoking LangGraph stream for Task {task_id}...")
        try:
            async for event in app_graph.astream(initial_state, {"recursion_limit": 50}, stream_mode="updates"):
                for node_name, state_update in event.items():
                    logger.info(f"[RUNNER] Graph node execution update -> Node: '{node_name}' finished.")
                    
                    if node_name == "agent":
                        messages = state_update.get("messages", [])
                        if messages:
                            last_msg = messages[-1]
                            reasoning = getattr(last_msg, "content", "")
                            tool_calls = getattr(last_msg, "tool_calls", [])
                            
                            if reasoning:
                                logger.info(f"[RUNNER] Agent reasoning: {reasoning}")
                            if tool_calls:
                                logger.info(f"[RUNNER] Agent planned tool calls: {tool_calls}")
                                
                            if reasoning or tool_calls:
                                tool_desc = ""
                                if tool_calls:
                                    t_calls = []
                                    for tc in tool_calls:
                                        t_name = tc.get("name")
                                        t_args = tc.get("args", {})
                                        if t_name == "search_internet":
                                            t_calls.append(f"Search: '{t_args.get('query')}'")
                                        elif t_name == "visit_webpage":
                                            t_calls.append(f"Visit: {t_args.get('url')}")
                                        else:
                                            t_calls.append(f"{t_name}")
                                    tool_desc = " | 📍 Next Action: " + ", ".join(t_calls)
                                
                                friendly_message = f"🧠 Thought: {reasoning}{tool_desc}"
                                details = {
                                    "message": friendly_message,
                                    "reasoning": reasoning,
                                    "tool_calls": tool_calls
                                }
                                await ws_manager.send_timeline_event(task_id, "reasoning", details)
                                await db_add_timeline_event(task_id, "reasoning", details)

                    if node_name == "tools":
                        logger.info(f"[RUNNER] Node '{node_name}' executed. Capturing screenshot for UI monitoring...")
                        try:
                            screenshot = await browser_controller.get_screenshot()
                            await ws_manager.send_screenshot_event(task_id, screenshot)
                            logger.info(f"[RUNNER] Screenshot sent to client via WebSocket for Task {task_id}.")
                        except Exception as e:
                            logger.warning(f"[RUNNER] Screenshot capture failed (non-critical, skipping): {e}")
                        
                        from langchain_core.messages import ToolMessage
                        messages = state_update.get("messages", [])
                        for msg in messages:
                            if isinstance(msg, ToolMessage):
                                tool_output = str(msg.content)
                                
                                status_msg = "Action executed."
                                if "Search results for" in tool_output or "Search results" in tool_output:
                                    first_line = tool_output.splitlines()[0] if tool_output.splitlines() else ""
                                    status_msg = f"⚡ Search results: {first_line}"
                                elif "ERROR" in tool_output:
                                    status_msg = f"❌ Action failed: {tool_output}"
                                elif "SKIPPED" in tool_output:
                                    status_msg = f"⚠️ Action skipped: {tool_output}"
                                elif "protected by CAPTCHA" in tool_output:
                                    status_msg = "⚠️ CAPTCHA/Security block detected. Skipping domain..."
                                else:
                                    status_msg = f"✅ Webpage visited: Read {len(tool_output)} characters successfully."
                                    
                                details = {
                                    "message": status_msg,
                                    "output_preview": tool_output[:300] + ("..." if len(tool_output) > 300 else "")
                                }
                                await ws_manager.send_timeline_event(task_id, "action", details)
                                await db_add_timeline_event(task_id, "action", details)
                        
                    if node_name == "extract":
                        jobs = state_update.get("extracted_jobs", [])
                        logger.info(f"[RUNNER] Node '{node_name}' executed. Extracted {len(jobs)} jobs.")
                        await ws_manager.send_timeline_event(task_id, "action", {"message": f"LLM extracted {len(jobs)} jobs."})
                        await db_add_timeline_event(task_id, "action", {"message": f"LLM extracted {len(jobs)} jobs."})

                    if node_name == "approve" and not state_update.get("is_approved"):
                        logger.info(f"[RUNNER] Task {task_id} was rejected by user in node 'approve'.")
                        task_status = "rejected"
                        await ws_manager.send_timeline_event(task_id, "rejected", {"message": "Task rejected by user."})
                        await db_add_timeline_event(task_id, "rejected", {"message": "Task rejected by user."})

                    if node_name == "finalize":
                        final_jobs_delivered = state_update.get("final_table", [])
                        logger.info(f"[RUNNER] Node 'finalize' executed. Task {task_id} complete. Delivering {len(final_jobs_delivered)} jobs.")
                        await ws_manager.send_timeline_event(task_id, "results", {"message": "Task completed.", "data": final_jobs_delivered})
                        await db_add_timeline_event(task_id, "results", {"message": "Task completed.", "data": final_jobs_delivered})
                        
        except Exception as e:
            logger.exception(f"[RUNNER] Exception encountered in graph execution for Task {task_id}: {e}")
            task_status = "failed"
            error_message = str(e)
            await ws_manager.send_timeline_event(task_id, "error", {"message": f"Agent failed: {str(e)}"})
            await db_add_timeline_event(task_id, "error", {"message": f"Agent failed: {str(e)}"})
        finally:
            logger.info(f"[RUNNER] Finalizing execution. Closing per-task browser for Task {task_id}...")
            await browser_manager.close_and_remove(task_id)
            task_control.remove(task_id)
            logger.info(f"[RUNNER] Browser closed. Task {task_id} execution finished.")
            
            await db_finalize_task(
                task_id,
                task_status,
                final_jobs=final_jobs_delivered if task_status == "completed" else None,
                error_msg=error_message
            )
            await ws_manager.send_status_update(task_id, task_status, "Agent finished execution")
            await ws_manager.send_timeline_event(task_id, "complete", {"message": "Agent finished execution."})

    def approve_task(self, task_id: str):
        resolve_approval(task_id, approved=True)

    def reject_task(self, task_id: str):
        resolve_approval(task_id, approved=False)

agent_runner = AgentRunner()