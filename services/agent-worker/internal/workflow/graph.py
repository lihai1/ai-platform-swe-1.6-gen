from typing import Dict, Any
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.postgres import PostgresSaver
from internal.workflow.state import EngineeringState
from internal.workflow.nodes import (
    created_node,
    preparing_workspace_node,
    scouting_node,
    planning_node,
    designing_node,
    implementing_node,
    testing_node,
    reviewing_node,
    verifying_node,
    repairing_node,
    waiting_approval_node,
    completed_node,
    failed_node,
    cancelled_node,
    budget_exceeded_node,
)
import asyncio
from datetime import datetime
from internal.config import settings


def should_cancel(state: EngineeringState) -> str:
    """Check if run should be cancelled"""
    if state.get("cancel_requested", False):
        return "cancel"
    return "continue"


def should_repair(state: EngineeringState) -> str:
    """Check if run should enter repair loop"""
    if state.get("repair_count", 0) >= state.get("max_repair_count", 2):
        return "failed"
    return "repair"


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


def create_workflow_graph(checkpointer: PostgresSaver) -> StateGraph:
    """Create the main LangGraph workflow"""
    
    workflow = StateGraph(EngineeringState)
    
    # Add all nodes
    workflow.add_node("CREATED", created_node)
    workflow.add_node("PREPARING_WORKSPACE", preparing_workspace_node)
    workflow.add_node("SCOUTING", scouting_node)
    workflow.add_node("PLANNING", planning_node)
    workflow.add_node("DESIGNING", designing_node)
    workflow.add_node("IMPLEMENTING", implementing_node)
    workflow.add_node("TESTING", testing_node)
    workflow.add_node("REVIEWING", reviewing_node)
    workflow.add_node("VERIFYING", verifying_node)
    workflow.add_node("REPAIRING", repairing_node)
    workflow.add_node("WAITING_APPROVAL", waiting_approval_node)
    workflow.add_node("COMPLETED", completed_node)
    workflow.add_node("FAILED", failed_node)
    workflow.add_node("CANCELLED", cancelled_node)
    workflow.add_node("BUDGET_EXCEEDED", budget_exceeded_node)
    
    # Define edges
    workflow.set_entry_point("CREATED")
    
    # CREATED -> PREPARING_WORKSPACE
    workflow.add_edge("CREATED", "PREPARING_WORKSPACE")
    
    # PREPARING_WORKSPACE -> (cancel check) -> SCOUTING or CANCELLED
    workflow.add_conditional_edges(
        "PREPARING_WORKSPACE",
        should_cancel,
        {
            "continue": "SCOUTING",
            "cancel": "CANCELLED"
        }
    )
    
    # SCOUTING -> (cancel check) -> PLANNING or CANCELLED
    workflow.add_conditional_edges(
        "SCOUTING",
        should_cancel,
        {
            "continue": "PLANNING",
            "cancel": "CANCELLED"
        }
    )
    
    # PLANNING -> (cancel check) -> DESIGNING or CANCELLED
    workflow.add_conditional_edges(
        "PLANNING",
        should_cancel,
        {
            "continue": "DESIGNING",
            "cancel": "CANCELLED"
        }
    )
    
    # DESIGNING -> (cancel check) -> IMPLEMENTING or CANCELLED
    workflow.add_conditional_edges(
        "DESIGNING",
        should_cancel,
        {
            "continue": "IMPLEMENTING",
            "cancel": "CANCELLED"
        }
    )
    
    # IMPLEMENTING -> (cancel check) -> TESTING or CANCELLED
    workflow.add_conditional_edges(
        "IMPLEMENTING",
        should_cancel,
        {
            "continue": "TESTING",
            "cancel": "CANCELLED"
        }
    )
    
    # TESTING -> (cancel check) -> REVIEWING or CANCELLED
    workflow.add_conditional_edges(
        "TESTING",
        should_cancel,
        {
            "continue": "REVIEWING",
            "cancel": "CANCELLED"
        }
    )
    
    # REVIEWING -> (cancel check) -> VERIFYING or CANCELLED
    workflow.add_conditional_edges(
        "REVIEWING",
        should_cancel,
        {
            "continue": "VERIFYING",
            "cancel": "CANCELLED"
        }
    )
    
    # VERIFYING -> (budget check, repair check) -> COMPLETED, REPAIRING, FAILED, or BUDGET_EXCEEDED
    workflow.add_conditional_edges(
        "VERIFYING",
        lambda state: check_budget(state) if check_budget(state) != "continue" else should_repair(state),
        {
            "continue": "COMPLETED",
            "repair": "REPAIRING",
            "failed": "FAILED",
            "budget_exceeded": "BUDGET_EXCEEDED"
        }
    )
    
    # REPAIRING -> (cancel check) -> IMPLEMENTING or CANCELLED
    workflow.add_conditional_edges(
        "REPAIRING",
        should_cancel,
        {
            "continue": "IMPLEMENTING",
            "cancel": "CANCELLED"
        }
    )
    
    # WAITING_APPROVAL -> (based on approval decision) -> IMPLEMENTING or FAILED
    workflow.add_conditional_edges(
        "WAITING_APPROVAL",
        lambda state: "IMPLEMENTING" if state.get("approval_decisions", {}).get("last") == "approved" else "FAILED",
        {
            "IMPLEMENTING": "IMPLEMENTING",
            "FAILED": "FAILED"
        }
    )
    
    # Terminal states
    workflow.add_edge("COMPLETED", END)
    workflow.add_edge("FAILED", END)
    workflow.add_edge("CANCELLED", END)
    workflow.add_edge("BUDGET_EXCEEDED", END)
    
    return workflow.compile(checkpointer=checkpointer)


async def create_run(state: EngineeringState, checkpointer: PostgresSaver) -> Dict[str, Any]:
    """Create and start a new run"""
    graph = create_workflow_graph(checkpointer)
    
    # Initialize state with defaults
    initial_state = {
        "chat_id": state.get("chat_id"),
        "user_id": state.get("user_id"),
        "project_id": state.get("project_id"),
        "repository_id": state.get("repository_id"),
        "chatkit_thread_id": state.get("chatkit_thread_id"),
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
    }
    
    # Run the workflow
    config = {"configurable": {"thread_id": initial_state["chat_id"]}}
    result = await graph.ainvoke(initial_state, config)
    
    return result
