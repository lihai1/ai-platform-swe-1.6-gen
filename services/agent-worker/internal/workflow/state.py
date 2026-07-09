from typing import TypedDict, Annotated, Optional, List, Dict, Any
from langgraph.graph import add_messages
import uuid

class EngineeringState(TypedDict):
    """State for the engineering workflow"""
    
    # Chat identification
    chat_id: str
    user_id: str
    project_id: str
    repository_id: str
    chatkit_thread_id: Optional[str]
    
    # Task definition
    task: str
    
    # Workflow status
    status: str  # CREATED, PREPARING_WORKSPACE, SCOUTING, PLANNING, DESIGNING, IMPLEMENTING, TESTING, REVIEWING, VERIFYING, REPAIRING, WAITING_APPROVAL, COMPLETED, FAILED, CANCELLED, BUDGET_EXCEEDED
    current_phase: str
    error_message: Optional[str]
    
    # Cancellation
    cancel_requested: bool
    
    # Budget tracking
    max_tokens: Optional[int]
    tokens_used: int
    max_cost: Optional[float]
    cost_incurred: float
    
    # Repair tracking
    repair_count: int
    max_repair_count: int
    
    # Repository analysis (from SCOUTING phase)
    repository_summary: Optional[Dict[str, Any]]
    
    # Planning (from PLANNING phase)
    selected_agents: Optional[List[str]]
    implementation_plan: Optional[Dict[str, Any]]
    
    # Design (from DESIGNING phase)
    design_spec: Optional[Dict[str, Any]]
    
    # Implementation (from IMPLEMENTING phase)
    implementation_results: Optional[Dict[str, Any]]
    code_diff: Optional[str]
    
    # Testing (from TESTING phase)
    test_results: Optional[Dict[str, Any]]
    
    # Review (from REVIEWING phase)
    review_results: Optional[Dict[str, Any]]
    
    # Verification (from VERIFYING phase)
    verification_results: Optional[Dict[str, Any]]
    
    # Messages for LangChain agents
    messages: Annotated[List, add_messages]
    
    # Workspace info
    workspace_id: Optional[str]
    workspace_branch: Optional[str]
    
    # Approval tracking
    pending_approvals: List[Dict[str, Any]]
    approval_decisions: Dict[str, str]
