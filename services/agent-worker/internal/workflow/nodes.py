import asyncio
from datetime import datetime
from typing import Dict, Any
from internal.workflow.state import EngineeringState
from internal.db import get_session
from internal.models import WorkspaceLease
from internal.workflow.approvals import request_approval
from internal.messaging.nats import NATSMessaging
import uuid
import os
import logging

logger = logging.getLogger(__name__)

# Global NATS client for event publishing
_nats_client = None

async def get_nats_client() -> NATSMessaging:
    """Get or create NATS client for event publishing"""
    global _nats_client
    if _nats_client is None:
        nats_url = os.getenv("NATS_URL", "nats://localhost:4222")
        _nats_client = NATSMessaging(nats_url=nats_url)
        await _nats_client.connect()
    return _nats_client

async def publish_state_event(run_id: str, state: str, payload: dict = None):
    """Publish state change event to NATS"""
    try:
        nats = await get_nats_client()
        await nats.publish_event(
            event_type=state.lower(),
            run_id=run_id,
            chat_id=run_id,
            payload=payload or {}
        )
        logger.info(f"Published state event: {state} for run {run_id}")
    except Exception as e:
        logger.error(f"Failed to publish state event: {e}")


async def created_node(state: EngineeringState) -> EngineeringState:
    """Initial node - marks run as created"""
    await asyncio.sleep(0.1)  # Simulate work
    state["status"] = "CREATED"
    state["current_phase"] = "CREATED"
    await publish_state_event(state["run_id"], "created", {"status": "CREATED"})
    return state


async def preparing_workspace_node(state: EngineeringState) -> EngineeringState:
    """Prepare workspace - repository already cloned in container"""
    state["status"] = "PREPARING_WORKSPACE"
    state["current_phase"] = "PREPARING_WORKSPACE"
    await publish_state_event(state["run_id"], "preparing_workspace", {"status": "PREPARING_WORKSPACE"})
    
    # Workspace is now the container itself, created by Go control plane
    # Repository is already cloned to /workspace
    await asyncio.sleep(0.1)
    state["workspace_id"] = "/workspace"  # Container's workspace directory
    state["workspace_branch"] = "main"  # Default branch, can be updated from container env
    
    return state


async def scouting_node(state: EngineeringState) -> EngineeringState:
    """Scout repository - mock implementation"""
    state["status"] = "SCOUTING"
    state["current_phase"] = "SCOUTING"
    await publish_state_event(state["run_id"], "scouting", {"status": "SCOUTING"})
    await asyncio.sleep(0.3)
    
    mock_mode = state.get("mock_mode", False)
    if mock_mode:
        state["repository_summary"] = {
            "language": "Go",
            "framework": "Mock",
            "test_framework": "mock-test",
            "total_files": 3,
            "test_files": 0,
            "main_files": 1,
            "config_files": 1,
        }
    else:
        state["repository_summary"] = {
            "language": "Go",
            "framework": "Gin",
            "test_framework": "ginkgo",
            "total_files": 42,
            "test_files": 8,
            "main_files": 15,
            "config_files": 5,
        }
    return state


async def planning_node(state: EngineeringState) -> EngineeringState:
    """Plan implementation - mock implementation"""
    state["status"] = "PLANNING"
    state["current_phase"] = "PLANNING"
    await publish_state_event(state["run_id"], "planning", {"status": "PLANNING"})
    await asyncio.sleep(0.4)
    
    mock_mode = state.get("mock_mode", False)
    if mock_mode:
        state["selected_agents"] = ["mock-developer"]
        state["implementation_plan"] = {
            "description": "Mock implementation plan",
            "files_expected_to_change": ["src/main.go"],
            "acceptance_criteria": [
                "Code compiles",
                "Mock test passes"
            ],
            "estimated_steps": 2
        }
    else:
        state["selected_agents"] = ["go-developer", "test-engineer"]
        state["implementation_plan"] = {
            "description": "Add new REST endpoint",
            "files_expected_to_change": ["internal/handlers/new_endpoint.go", "internal/service/new_service.go"],
            "acceptance_criteria": [
                "Endpoint returns 200 on success",
                "Endpoint validates input",
                "Tests pass"
            ],
            "estimated_steps": 5
        }
    return state


async def designing_node(state: EngineeringState) -> EngineeringState:
    """Design solution - fake implementation"""
    state["status"] = "DESIGNING"
    state["current_phase"] = "DESIGNING"
    await publish_state_event(state["run_id"], "designing", {"status": "DESIGNING"})
    await asyncio.sleep(0.3)
    state["design_spec"] = {
        "architecture": "REST API with Gin",
        "data_flow": "Request -> Handler -> Service -> Repository",
        "components": ["Handler", "Service", "Repository"]
    }
    return state


async def implementing_node(state: EngineeringState) -> EngineeringState:
    """Implement changes - run implementation agents"""
    state["status"] = "IMPLEMENTING"
    state["current_phase"] = "IMPLEMENTING"
    await publish_state_event(state["run_id"], "implementing", {"status": "IMPLEMENTING"})
    
    mock_mode = state.get("mock_mode", False)
    
    # In production, this would:
    # 1. Determine which implementation agents to run based on selected_agents
    # 2. Run agents in parallel for non-overlapping file scopes
    # 3. Serialize execution for overlapping file scopes
    # 4. Aggregate results from all agents
    # 5. Generate diff artifact
    
    # For now, use fake implementation to maintain compatibility
    await asyncio.sleep(0.5)
    
    if mock_mode:
        state["implementation_results"] = {
            "files_modified": 1,
            "lines_added": 5,
            "lines_removed": 1,
            "success": True
        }
        state["code_diff"] = "diff --git a/src/main.go b/src/main.go\nindex 1234567..abcdefg 100644\n--- a/src/main.go\n+++ b/src/main.go\n@@ -4,5 +4,5 @@ func main() {\n-    fmt.Println(\"Hello, World!\")\n+    fmt.Println(\"Mock implementation complete!\")\n }"
    else:
        state["implementation_results"] = {
            "files_modified": 2,
            "lines_added": 45,
            "lines_removed": 3,
            "success": True
        }
        state["code_diff"] = "diff --git a/internal/handlers/new_endpoint.go b/internal/handlers/new_endpoint.go\nnew file mode 100644\nindex 0000000..1234567\n--- /dev/null\n+++ b/internal/handlers/new_endpoint.go\n@@ -0,0 +1,30 @@\n+package handlers\n+\n+func NewEndpoint() string {\n+    return \"Hello World\"\n+}"
    
    return state


async def testing_node(state: EngineeringState) -> EngineeringState:
    """Run tests - execute test engineer agents"""
    state["status"] = "TESTING"
    state["current_phase"] = "TESTING"
    await publish_state_event(state["run_id"], "testing", {"status": "TESTING"})
    
    mock_mode = state.get("mock_mode", False)
    
    # In production, this would:
    # 1. Determine which test engineer to use based on repository type
    # 2. Run tests in the workspace
    # 3. Analyze test results
    # 4. Generate test report artifact
    
    # For now, use fake implementation to maintain compatibility
    await asyncio.sleep(0.4)
    
    if mock_mode:
        state["test_results"] = {
            "total_tests": 1,
            "passed": 1,
            "failed": 0,
            "skipped": 0,
            "coverage": 100.0
        }
    else:
        state["test_results"] = {
            "total_tests": 8,
            "passed": 7,
            "failed": 1,
            "skipped": 0,
            "coverage": 85.5
        }
    
    return state


async def reviewing_node(state: EngineeringState) -> EngineeringState:
    """Review code - execute code reviewer agent"""
    state["status"] = "REVIEWING"
    await publish_state_event(state["run_id"], "reviewing", {"status": "REVIEWING"})
    state["current_phase"] = "REVIEWING"
    
    mock_mode = state.get("mock_mode", False)
    
    # In production, this would:
    # 1. Run code reviewer agent on the diff
    # 2. Analyze findings with severity levels
    # 3. Generate review report artifact
    
    # For now, use fake implementation to maintain compatibility
    await asyncio.sleep(0.3)
    
    if mock_mode:
        state["review_results"] = {
            "decision": "approved",
            "findings": []
        }
    else:
        state["review_results"] = {
            "decision": "changes_required",
            "findings": [
                {"severity": "medium", "message": "Add error handling"},
                {"severity": "low", "message": "Improve variable naming"}
            ]
        }
    
    return state


async def verifying_node(state: EngineeringState) -> EngineeringState:
    """Verify completion - execute completion verifier agent"""
    state["status"] = "VERIFYING"
    state["current_phase"] = "VERIFYING"
    await publish_state_event(state["run_id"], "verifying", {"status": "VERIFYING"})
    
    mock_mode = state.get("mock_mode", False)
    
    # In production, this would:
    # 1. Run completion verifier agent against acceptance criteria
    # 2. Map test results and review results to criteria
    # 3. Generate verification report artifact
    
    # For now, use fake implementation to maintain compatibility
    await asyncio.sleep(0.3)
    
    if mock_mode:
        # In mock mode, always pass verification
        state["verification_results"] = {
            "accepted": True,
            "criteria_results": [
                {"criterion": "Code compiles", "passed": True},
                {"criterion": "Mock test passes", "passed": True}
            ]
        }
    else:
        # For demo, alternate between success and failure
        if state.get("repair_count", 0) == 0:
            state["verification_results"] = {
                "accepted": False,
                "criteria_results": [
                    {"criterion": "Endpoint returns 200 on success", "passed": True},
                    {"criterion": "Endpoint validates input", "passed": False},
                    {"criterion": "Tests pass", "passed": True}
                ]
            }
        else:
            state["verification_results"] = {
                "accepted": True,
                "criteria_results": [
                    {"criterion": "Endpoint returns 200 on success", "passed": True},
                    {"criterion": "Endpoint validates input", "passed": True},
                    {"criterion": "Tests pass", "passed": True}
                ]
            }
    
    return state


async def repairing_node(state: EngineeringState) -> EngineeringState:
    """Repair issues - fake implementation"""
    state["status"] = "REPAIRING"
    state["current_phase"] = "REPAIRING"
    state["repair_count"] = state.get("repair_count", 0) + 1
    await publish_state_event(state["run_id"], "repairing", {"status": "REPAIRING", "repair_count": state["repair_count"]})
    await asyncio.sleep(0.4)
    return state


async def waiting_approval_node(state: EngineeringState) -> EngineeringState:
    """Wait for human approval - use LangGraph interrupt"""
    state["status"] = "WAITING_APPROVAL"
    state["current_phase"] = "WAITING_APPROVAL"
    
    # In production, this would:
    # 1. Use request_approval() to interrupt the workflow
    # 2. Wait for human decision via API
    # 3. Resume with langgraph.Command based on decision
    
    # For now, use fake implementation to maintain compatibility
    await asyncio.sleep(0.1)
    
    return state


async def completed_node(state: EngineeringState) -> EngineeringState:
    """Mark run as completed"""
    await asyncio.sleep(0.1)
    state["status"] = "COMPLETED"
    state["current_phase"] = "COMPLETED"
    await publish_state_event(state["run_id"], "completed", {"status": "COMPLETED"})
    return state


async def failed_node(state: EngineeringState) -> EngineeringState:
    """Mark run as failed"""
    await asyncio.sleep(0.1)
    state["status"] = "FAILED"
    state["current_phase"] = "FAILED"
    state["error_message"] = "Verification failed after repair limit"
    await publish_state_event(state["run_id"], "failed", {"status": "FAILED", "error_message": state["error_message"]})
    return state


async def cancelled_node(state: EngineeringState) -> EngineeringState:
    """Mark run as cancelled"""
    await asyncio.sleep(0.1)
    state["status"] = "CANCELLED"
    state["current_phase"] = "CANCELLED"
    state["error_message"] = "Run cancelled by user"
    await publish_state_event(state["run_id"], "cancelled", {"status": "CANCELLED"})
    return state


async def budget_exceeded_node(state: EngineeringState) -> EngineeringState:
    """Mark run as budget exceeded"""
    await asyncio.sleep(0.1)
    state["status"] = "BUDGET_EXCEEDED"
    state["current_phase"] = "BUDGET_EXCEEDED"
    state["error_message"] = "Budget limit exceeded"
    await publish_state_event(state["run_id"], "budget_exceeded", {"status": "BUDGET_EXCEEDED"})
    return state
