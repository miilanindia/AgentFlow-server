import asyncio
from app.tasks.celery_app import celery_app
from app.services.agent_runner import agent_runner

@celery_app.task(name="app.tasks.celery_tasks.run_agent_task")
def run_agent_task(task_id: str, goal: str, user_id: str = None):
    """
    Celery task that runs the LangGraph runner asynchronously.
    Runs the asyncio event loop to execute the asynchronous run_agent function.
    """
    asyncio.run(agent_runner.run_agent(task_id, goal, user_id=user_id))
