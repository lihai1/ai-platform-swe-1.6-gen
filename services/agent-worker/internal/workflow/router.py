from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
from typing import Optional
import uuid
import os

from internal.db import get_session
from internal.models import AgentRun, AgentApproval
from internal.workflow.graph import create_run
from internal.workflow.checkpointer import get_checkpointer
from internal.workflow.events import stream_events
from pydantic import BaseModel


class CreateRunRequest(BaseModel):
    user_id: str
    project_id: str
    repository_id: str
    task: str
    chatkit_thread_id: Optional[str] = None
    max_tokens: Optional[int] = None
    max_cost: Optional[float] = None
    max_repair_count: int = 2


class RunResponse(BaseModel):
    id: str
    user_id: str
    project_id: str
    repository_id: str
    task: str
    status: str
    current_phase: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]


router = APIRouter(prefix="/agent/v1", tags=["agent"])


@router.post("/runs", response_model=RunResponse)
async def create_agent_run(
    request: CreateRunRequest,
    session: AsyncSession = Depends(get_session)
):
    """Create and start a new agent run"""
    
    run_id = str(uuid.uuid4())
    
    # Create run record in database
    run = AgentRun(
        id=run_id,
        user_id=request.user_id,
        project_id=request.project_id,
        repository_id=request.repository_id,
        chatkit_thread_id=request.chatkit_thread_id,
        task=request.task,
        status="CREATED",
        current_phase="CREATED",
        max_tokens=request.max_tokens,
        max_cost=request.max_cost,
        max_repair_count=request.max_repair_count,
    )
    
    session.add(run)
    await session.commit()
    await session.refresh(run)
    
    # Start the workflow asynchronously
    checkpointer = await get_checkpointer()
    
    # Don't await - let it run in background
    import asyncio
    asyncio.create_task(create_run({
        "run_id": run_id,
        "user_id": request.user_id,
        "project_id": request.project_id,
        "repository_id": request.repository_id,
        "chatkit_thread_id": request.chatkit_thread_id,
        "task": request.task,
        "max_tokens": request.max_tokens,
        "max_cost": request.max_cost,
        "max_repair_count": request.max_repair_count,
    }, checkpointer))
    
    return RunResponse(
        id=run.id,
        user_id=run.user_id,
        project_id=run.project_id,
        repository_id=run.repository_id,
        task=run.task,
        status=run.status,
        current_phase=run.current_phase,
        created_at=run.created_at,
        updated_at=run.updated_at,
    )


@router.get("/runs/{run_id}", response_model=RunResponse)
async def get_run(
    run_id: str,
    session: AsyncSession = Depends(get_session)
):
    """Get a run by ID"""
    
    from sqlalchemy import select
    
    query = select(AgentRun).where(AgentRun.id == run_id)
    result = await session.execute(query)
    run = result.scalar_one_or_none()
    
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    
    return RunResponse(
        id=run.id,
        user_id=run.user_id,
        project_id=run.project_id,
        repository_id=run.repository_id,
        task=run.task,
        status=run.status,
        current_phase=run.current_phase,
        created_at=run.created_at,
        updated_at=run.updated_at,
    )


@router.post("/runs/{run_id}/cancel")
async def cancel_run(
    run_id: str,
    session: AsyncSession = Depends(get_session)
):
    """Cancel a running run"""
    
    from sqlalchemy import select, update
    
    query = select(AgentRun).where(AgentRun.id == run_id)
    result = await session.execute(query)
    run = result.scalar_one_or_none()
    
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    
    if run.status in ["COMPLETED", "FAILED", "CANCELLED", "BUDGET_EXCEEDED"]:
        raise HTTPException(status_code=400, detail="Run is already in terminal state")
    
    # Update run to mark cancellation requested
    update_query = update(AgentRun).where(AgentRun.id == run_id).values(
        cancel_requested_at=datetime.utcnow()
    )
    await session.execute(update_query)
    await session.commit()
    
    return {"status": "cancellation_requested"}


@router.get("/runs/{run_id}/events")
async def get_run_events(
    run_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session)
):
    """Stream events for a run via SSE"""
    
    return await stream_events(run_id, request, session)


class ApprovalRequest(BaseModel):
    decision: str  # approved or rejected
    decided_by: str
    comments: Optional[str] = None


@router.post("/runs/{run_id}/approvals/{approval_id}/approve")
async def approve_approval(
    run_id: str,
    approval_id: str,
    request: ApprovalRequest,
    session: AsyncSession = Depends(get_session)
):
    """Approve a pending approval"""
    
    from sqlalchemy import select, update
    
    # Get the approval
    query = select(AgentApproval).where(
        AgentApproval.id == approval_id,
        AgentApproval.run_id == run_id
    )
    result = await session.execute(query)
    approval = result.scalar_one_or_none()
    
    if not approval:
        raise HTTPException(status_code=404, detail="Approval not found")
    
    if approval.decision != "pending":
        raise HTTPException(status_code=400, detail="Approval already decided")
    
    # Update approval
    approval.decision = "approved"
    approval.decided_by = request.decided_by
    approval.decided_at = datetime.utcnow()
    
    await session.commit()
    
    # Resume the workflow with the approval decision
    # In production, this would use langgraph.Command to resume
    checkpointer = await get_checkpointer()
    
    # Update state with approval decision
    from langgraph.checkpoint.postgres import PostgresSaver
    config = {"configurable": {"thread_id": run_id}}
    
    # Get current state
    checkpoint = checkpointer.get(config)
    if checkpoint:
        current_state = checkpoint.get("channel_values", {})
        approval_decisions = current_state.get("approval_decisions", {})
        approval_decisions["last"] = "approved"
        approval_decisions[approval_id] = "approved"
        
        # Update checkpoint with approval decision
        checkpointer.put(config, current_state)
    
    return {"status": "approved"}


@router.post("/runs/{run_id}/approvals/{approval_id}/reject")
async def reject_approval(
    run_id: str,
    approval_id: str,
    request: ApprovalRequest,
    session: AsyncSession = Depends(get_session)
):
    """Reject a pending approval"""
    
    from sqlalchemy import select, update
    
    # Get the approval
    query = select(AgentApproval).where(
        AgentApproval.id == approval_id,
        AgentApproval.run_id == run_id
    )
    result = await session.execute(query)
    approval = result.scalar_one_or_none()
    
    if not approval:
        raise HTTPException(status_code=404, detail="Approval not found")
    
    if approval.decision != "pending":
        raise HTTPException(status_code=400, detail="Approval already decided")
    
    # Update approval
    approval.decision = "rejected"
    approval.decided_by = request.decided_by
    approval.decided_at = datetime.utcnow()
    
    await session.commit()
    
    # Resume the workflow with the rejection decision
    checkpointer = await get_checkpointer()
    
    # Update state with approval decision
    config = {"configurable": {"thread_id": run_id}}
    
    # Get current state
    checkpoint = checkpointer.get(config)
    if checkpoint:
        current_state = checkpoint.get("channel_values", {})
        approval_decisions = current_state.get("approval_decisions", {})
        approval_decisions["last"] = "rejected"
        approval_decisions[approval_id] = "rejected"
        
        # Update checkpoint with approval decision
        checkpointer.put(config, current_state)
    
    return {"status": "rejected"}
