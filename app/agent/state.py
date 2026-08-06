from typing import List, Dict, Any, TypedDict, Optional, Annotated
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

class JobListing(TypedDict):
    title: str
    company: str
    location: str
    link: str

class AgentState(TypedDict):
    task_id: str
    goal: str
    messages: Annotated[List[BaseMessage], add_messages] # LLM ki yaad (memory) ke liye
    extracted_jobs: List[JobListing]
    final_table: List[Dict[str, Any]]
    error: Optional[str]
    needs_approval: bool
    is_approved: bool
    tool_call_count: int 