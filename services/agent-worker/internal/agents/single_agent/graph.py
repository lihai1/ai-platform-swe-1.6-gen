"""Single-agent workflow graph"""
from typing import Dict, Any
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from internal.workflow.state import EngineeringState
from internal.workflow.nodes import (
    failed_node,
    cancelled_node,
    budget_exceeded_node,
)
from .nodes import reasoning_node
import asyncio
from datetime import datetime


def should_cancel(state: EngineeringState) -> str:
    """Check if run should be cancelled"""
    if state.get("cancel_requested", False):
        return "cancel"
    return "continue"


def check_budget(state: EngineeringState) -> str:
    """Check if budget exceeded"""
    max_tokens = state.get("max_tokens")
    tokens_used = state.get("tokens_used", 0)
    max_cost = state.get("max_cost")
    cost_incurred = state.get("cost_incurred", 0.0)
    
    if max_tokens and tokens_used >= max_tokens:
        return "budget_exceeded"
    if max_cost and cost_incurred >= max_cost:
        return "budget_exceeded"
    return "continue"


def create_single_agent_graph(checkpointer: MemorySaver) -> StateGraph:
    """Create the single-agent workflow graph with simplified flow: REASONING -> COMPLETED"""
    
    workflow = StateGraph(EngineeringState)
    
    # Add nodes for single-agent workflow
    workflow.add_node("REASONING", reasoning_node)
    workflow.add_node("FAILED", failed_node)
    workflow.add_node("CANCELLED", cancelled_node)
    workflow.add_node("BUDGET_EXCEEDED", budget_exceeded_node)

    # Define edges
    workflow.set_entry_point("REASONING")

    # REASONING -> (cancel check, budget check) -> END, BUDGET_EXCEEDED, or CANCELLED
    workflow.add_conditional_edges(
        "REASONING",
        lambda state: "cancel" if should_cancel(state) == "cancel" else check_budget(state),
        {
            "cancel": "CANCELLED",
            "budget_exceeded": "BUDGET_EXCEEDED",
            "continue": END
        }
    )

    # Terminal states
    workflow.add_edge("FAILED", END)
    workflow.add_edge("CANCELLED", END)
    workflow.add_edge("BUDGET_EXCEEDED", END)
    
    return workflow.compile(checkpointer=checkpointer)


async def create_single_agent_run(state: EngineeringState, checkpointer: MemorySaver) -> Dict[str, Any]:
    """Create and start a single-agent run"""
    graph = create_single_agent_graph(checkpointer)
    
    # Initialize state with defaults
    initial_state = {
        "run_id": state.get("run_id"),
        "user_id": state.get("user_id"),
        "project_id": state.get("project_id"),
        "repository_id": state.get("repository_id"),
        "task": state.get("task"),
        "status": "CREATED",
        "current_phase": "CREATED",
        "error_message": None,
        "cancel_requested": False,
        "max_tokens": state.get("max_tokens"),
        "tokens_used": 0,
        "max_cost": state.get("max_cost"),
        "cost_incurred": 0.0,
        "repair_count": 0,
        "max_repair_count": state.get("max_repair_count", 2),
        "repository_summary": None,
        "selected_agents": None,
        "implementation_plan": None,
        "design_spec": None,
        "implementation_results": None,
        "code_diff": None,
        "test_results": None,
        "review_results": None,
        "verification_results": None,
        "messages": [],
        "workspace_id": None,
        "workspace_branch": None,
        "pending_approvals": [],
        "approval_decisions": {},
        "mock_mode": state.get("mock_mode", False),
        "llm_provider": state.get("llm_provider"),
        "agent_type": "single-agent",
    }
    
    # Run the workflow
    config = {"configurable": {"thread_id": initial_state["run_id"]}}
    result = await graph.ainvoke(initial_state, config)
    
    return result
