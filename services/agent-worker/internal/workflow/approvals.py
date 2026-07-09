"""Human approval workflow integration"""
from typing import Dict, Any, Optional
from langgraph.types import interrupt
import uuid
import logging

logger = logging.getLogger(__name__)


def request_approval(
    approval_type: str,
    description: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Request human approval using LangGraph interrupt"""
    
    approval_request = {
        "approval_id": str(uuid.uuid4()),
        "approval_type": approval_type,
        "description": description,
        "metadata": metadata or {},
        "status": "pending",
    }
    
    # This interrupts the workflow and waits for human input
    decision = interrupt(approval_request)
    
    return {
        "approval_id": approval_request["approval_id"],
        "decision": decision.get("decision", "rejected"),
        "decided_by": decision.get("decided_by"),
        "decided_at": decision.get("decided_at"),
        "comments": decision.get("comments", ""),
    }


class ApprovalRequiredError(Exception):
    """Raised when an action requires approval"""
    pass


class ApprovalRejectedError(Exception):
    """Raised when approval is rejected"""
    pass
