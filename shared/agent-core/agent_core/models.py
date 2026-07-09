from sqlalchemy import Column, String, DateTime, Text, ForeignKey, Integer, JSON, Float, Boolean
from sqlalchemy.sql import func
from agent_core.db import Base
import uuid

class ChatkitThread(Base):
    __tablename__ = "chatkit_threads"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, nullable=False, index=True)
    title = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class ChatkitItem(Base):
    __tablename__ = "chatkit_items"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    thread_id = Column(String, ForeignKey("chatkit_threads.id", ondelete="CASCADE"), nullable=False)
    role = Column(String, nullable=False)  # "user" or "assistant"
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class AgentRun(Base):
    __tablename__ = "agent_runs"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, nullable=False, index=True)
    project_id = Column(String, nullable=False, index=True)
    repository_id = Column(String, nullable=False, index=True)
    chatkit_thread_id = Column(String, ForeignKey("chatkit_threads.id", ondelete="SET NULL"), nullable=True)
    task = Column(Text, nullable=False)
    status = Column(String, nullable=False, index=True)  # CREATED, PREPARING_WORKSPACE, SCOUTING, PLANNING, DESIGNING, IMPLEMENTING, TESTING, REVIEWING, VERIFYING, REPAIRING, WAITING_APPROVAL, COMPLETED, FAILED, CANCELLED, BUDGET_EXCEEDED
    current_phase = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)
    cancel_requested_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Budget tracking
    max_tokens = Column(Integer, nullable=True)
    tokens_used = Column(Integer, default=0)
    max_cost = Column(Float, nullable=True)
    cost_incurred = Column(Float, default=0.0)
    
    # Repair tracking
    repair_count = Column(Integer, default=0)
    max_repair_count = Column(Integer, default=2)

class AgentStep(Base):
    __tablename__ = "agent_steps"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    chat_id = Column(String, ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    phase = Column(String, nullable=False, index=True)
    agent_name = Column(String, nullable=False)
    status = Column(String, nullable=False)  # started, completed, failed
    input_data = Column(JSON, nullable=True)
    output_data = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)

class AgentEvent(Base):
    __tablename__ = "agent_events"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    chat_id = Column(String, ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    step_id = Column(String, ForeignKey("agent_steps.id", ondelete="CASCADE"), nullable=True, index=True)
    event_type = Column(String, nullable=False, index=True)  # phase_start, phase_end, agent_start, agent_end, tool_call, tool_result, error, etc.
    event_data = Column(JSON, nullable=True)
    sequence_number = Column(Integer, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class SkillSnapshot(Base):
    __tablename__ = "skill_snapshots"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    chat_id = Column(String, ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    skill_name = Column(String, nullable=False)
    skill_version = Column(String, nullable=False)
    content_hash = Column(String, nullable=False)
    skill_yaml = Column(Text, nullable=False)
    skill_markdown = Column(Text, nullable=False)
    output_schema = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class AgentArtifact(Base):
    __tablename__ = "agent_artifacts"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    chat_id = Column(String, ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    step_id = Column(String, ForeignKey("agent_steps.id", ondelete="CASCADE"), nullable=True, index=True)
    kind = Column(String, nullable=False, index=True)  # code_diff, test_report, review_report, verification_report, diagram, etc.
    title = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    extra_metadata = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class AgentApproval(Base):
    __tablename__ = "agent_approvals"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    chat_id = Column(String, ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    step_id = Column(String, ForeignKey("agent_steps.id", ondelete="CASCADE"), nullable=True, index=True)
    approval_type = Column(String, nullable=False)  # push, pr, network, credentials, protected_files
    description = Column(Text, nullable=False)
    decision = Column(String, nullable=True)  # approved, rejected, pending
    decided_by = Column(String, nullable=True)
    decided_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class WorkspaceLease(Base):
    __tablename__ = "workspace_leases"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    chat_id = Column(String, nullable=False, index=True)
    workspace_id = Column(String, nullable=False, unique=True)
    volume_name = Column(String, nullable=False)
    container_id = Column(String, nullable=True)
    branch_name = Column(String, nullable=False)
    repository_url = Column(String, nullable=False)
    status = Column(String, nullable=False, index=True)  # active, released, failed
    leased_at = Column(DateTime(timezone=True), server_default=func.now())
    released_at = Column(DateTime(timezone=True), nullable=True)
    extra_metadata = Column(JSON, nullable=True)
