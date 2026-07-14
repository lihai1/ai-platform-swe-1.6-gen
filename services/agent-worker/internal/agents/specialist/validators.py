"""Validation agents for testing, review, and verification"""
from abc import ABC
from typing import Dict, Any, List, Optional, ClassVar
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.agents import create_agent
from langchain_core.tools import tool
from internal.agents.schemas import TestResult, ReviewResult, ReviewFinding, VerificationResult, CriterionResult
from internal.agents.model_factory import get_model
from internal.tools.workspace import WorkspaceTools
from internal.tools.agent_tools import create_workspace_tools
import json
import logging
import re

logger = logging.getLogger(__name__)


def _parse_test_output(test_output: str) -> dict:
    """Parse test output from go test or simple summaries."""
    total = passed = failed = skipped = 0
    try:
        # Look for explicit counts first (e.g. "1 passed, 0 failed")
        passed_match = re.search(r"(\d+)\s+passed", test_output, re.IGNORECASE)
        failed_match = re.search(r"(\d+)\s+failed", test_output, re.IGNORECASE)
        skipped_match = re.search(r"(\d+)\s+skipped", test_output, re.IGNORECASE)
        if passed_match or failed_match:
            passed = int(passed_match.group(1)) if passed_match else 0
            failed = int(failed_match.group(1)) if failed_match else 0
            skipped = int(skipped_match.group(1)) if skipped_match else 0
        else:
            # Fallback for go test output: "ok" or "PASS" means all passed,
            # "FAIL" or "--- FAIL" means at least one failed.
            if re.search(r"FAIL|---\s*FAIL", test_output, re.IGNORECASE):
                failed = 1
            elif re.search(r"ok\s|PASS", test_output, re.IGNORECASE):
                passed = 1
        total = passed + failed + skipped
    except Exception as e:
        logger.warning(f"Failed to parse test output: {e}")
    return {
        "total_tests": total or 1,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
    }


def _parse_test_result(result: dict) -> TestResult:
    """Parse an AgentExecutor result into a TestResult"""
    output_text = result.get("output", "")
    test_output = ""
    success = False
    intermediate_steps = result.get("intermediate_steps", [])
    for action, observation in intermediate_steps:
        try:
            tool_name = getattr(action, "tool", None)
            if tool_name == "run_tests":
                obs = json.loads(observation) if isinstance(observation, str) else observation
                if obs.get("success"):
                    success = True
                    test_output = obs.get("output", "")
                else:
                    test_output = obs.get("error", "") or obs.get("output", "")
        except Exception as e:
            logger.warning(f"Failed to parse test step: {e}")

    if not test_output and output_text:
        test_output = output_text

    metrics = _parse_test_output(test_output)
    return TestResult(
        total_tests=metrics["total_tests"],
        passed=metrics["passed"],
        failed=metrics["failed"],
        skipped=metrics["skipped"],
        coverage=0.0,
        test_output=test_output,
        failed_tests=[]
    )


def _parse_review_result(result: dict) -> ReviewResult:
    """Parse an AgentExecutor result into a ReviewResult"""
    output = result.get("output", "")
    decision = "approved" if "approved" in output.lower() else "changes_required"
    return ReviewResult(
        decision=decision,
        findings=[],
        summary=output or "Code review completed"
    )


def _parse_verification_result(
    result: dict,
    implementation_plan: Dict[str, Any],
    test_results: Any,
    review_results: Any,
) -> VerificationResult:
    """Parse an AgentExecutor result into a VerificationResult"""
    output = result.get("output", "")
    criteria = implementation_plan.get("acceptance_criteria", []) if implementation_plan else []
    test_passed = bool(test_results and getattr(test_results, "passed", test_results.get("passed", 0)) > 0)
    review_decision = review_results.decision if hasattr(review_results, "decision") else review_results.get("decision", "approved")
    accepted = test_passed and review_decision != "rejected"

    criteria_results = [
        CriterionResult(
            criterion=c,
            passed=accepted,
            evidence=output or "Verified through testing and code review"
        )
        for c in criteria
    ] if criteria else [
        CriterionResult(
            criterion="Implementation",
            passed=accepted,
            evidence=output or "Verified through testing and code review"
        )
    ]

    return VerificationResult(
        accepted=accepted,
        criteria_results=criteria_results,
        summary=output or "Verification completed"
    )


class BaseValidationAgent(ABC):
    """Shared base for validation agents (test, review, verify)."""

    agent_name: ClassVar[str] = ""

    def __init__(self, model_name: str = "gpt-4", mock_mode: bool = False, llm_provider: Optional[str] = None):
        self.model = get_model(model_name=model_name, mock_mode=mock_mode, llm_provider=llm_provider)
        self.mock_mode = mock_mode
        self.llm_provider = llm_provider
        self._last_error = ""

    def _initialize_run(self, run_id: Optional[str], workspace_tools: WorkspaceTools) -> None:
        """Initialize workspace tools with the run_id for event publishing."""
        if run_id and not workspace_tools.run_id:
            workspace_tools.run_id = run_id

    def _build_workspace_tools(
        self,
        workspace_id: str,
        workspace_tools: WorkspaceTools,
        *,
        include_run_tests: bool = False,
        include_git_status: bool = False,
        include_git_diff: bool = False,
    ) -> list:
        """Build workspace tools requested by the validation agent."""
        return create_workspace_tools(
            workspace_id,
            workspace_tools,
            include_read=True,
            include_write=False,
            include_list=False,
            include_git_status=include_git_status,
            include_git_diff=include_git_diff,
            include_run_tests=include_run_tests,
            include_run_command=False,
        )

    async def _run_agent(self, system_prompt: str, tools: list, invoke_kwargs: Dict[str, Any]) -> dict | None:
        """Create the agent, invoke it and return the result, or None on failure."""
        self._last_error = ""
        graph = create_agent(
            model=self.model,
            tools=tools,
            system_prompt=system_prompt,
        )
        try:
            return await graph.ainvoke(invoke_kwargs)
        except Exception as e:
            self._last_error = str(e)
            logger.error("%s failed: %s", self.agent_name, self._last_error)
            return None


class BackendTestEngineerAgent(BaseValidationAgent):
    """Agent for backend testing (Go, Python, etc.)"""

    agent_name = "Backend test engineer agent"

    async def run_tests(
        self,
        task: str,
        implementation_plan: Dict[str, Any],
        workspace_id: str,
        workspace_tools: WorkspaceTools,
        run_id: Optional[str] = None,
    ) -> TestResult:
        """Run backend tests"""
        self._initialize_run(run_id, workspace_tools)

        system_prompt = """You are a backend test engineer agent. Your job is to execute and analyze test results.

Analyze the test output and provide:
- Total number of tests run
- Number of tests passed
- Number of tests failed
- Number of tests skipped
- Code coverage percentage if available
- Full test output
- List of failed test names"""

        tools = self._build_workspace_tools(workspace_id, workspace_tools, include_run_tests=True)
        invoke_kwargs = {
            "messages": [
                {
                    "role": "user",
                    "content": f"""Task: {task}

Implementation Plan:
{json.dumps(implementation_plan, indent=2)}

Run the tests and analyze the results."""
                }
            ]
        }
        result = await self._run_agent(system_prompt, tools, invoke_kwargs)

        if result is None:
            return TestResult(
                total_tests=0,
                passed=0,
                failed=0,
                skipped=0,
                coverage=0.0,
                test_output=self._last_error,
                failed_tests=[],
            )
        return _parse_test_result(result)


class AngularTestEngineerAgent(BaseValidationAgent):
    """Agent for Angular testing"""

    agent_name = "Angular test engineer agent"

    async def run_tests(
        self,
        task: str,
        implementation_plan: Dict[str, Any],
        workspace_id: str,
        workspace_tools: WorkspaceTools,
        run_id: Optional[str] = None,
    ) -> TestResult:
        """Run Angular tests"""
        self._initialize_run(run_id, workspace_tools)

        system_prompt = """You are an Angular test engineer agent. Your job is to execute and analyze Angular test results.

Analyze the test output and provide:
- Total number of tests run
- Number of tests passed
- Number of tests failed
- Number of tests skipped
- Code coverage percentage if available
- Full test output
- List of failed test names"""

        tools = self._build_workspace_tools(workspace_id, workspace_tools, include_run_tests=True)
        invoke_kwargs = {
            "messages": [
                {
                    "role": "user",
                    "content": f"""Task: {task}

Implementation Plan:
{json.dumps(implementation_plan, indent=2)}

Run the Angular tests and analyze the results."""
                }
            ]
        }
        result = await self._run_agent(system_prompt, tools, invoke_kwargs)

        if result is None:
            return TestResult(
                total_tests=0,
                passed=0,
                failed=0,
                skipped=0,
                coverage=0.0,
                test_output=self._last_error,
                failed_tests=[],
            )
        return _parse_test_result(result)


class CodeReviewerAgent(BaseValidationAgent):
    """Agent for code review"""

    agent_name = "Code reviewer agent"

    async def review(
        self,
        task: str,
        implementation_plan: Dict[str, Any],
        code_diff: str,
        workspace_id: str,
        workspace_tools: WorkspaceTools,
        run_id: Optional[str] = None,
    ) -> ReviewResult:
        """Review code changes"""
        self._initialize_run(run_id, workspace_tools)

        system_prompt = """You are a code reviewer agent. Your job is to review code changes for correctness, maintainability, security, and best practices.

Provide review findings with severity levels:
- blocking: Must be fixed before merge
- high: Should be fixed
- medium: Nice to have
- low: Minor suggestions

Your review should cover:
- Correctness and logic
- Security vulnerabilities
- Performance issues
- Code style and readability
- Error handling
- Test coverage
- Documentation"""

        tools = self._build_workspace_tools(workspace_id, workspace_tools, include_git_diff=True)
        invoke_kwargs = {
            "messages": [
                {
                    "role": "user",
                    "content": f"""Task: {task}

Implementation Plan:
{json.dumps(implementation_plan, indent=2)}

Code Diff:
{code_diff}

Review the changes and provide findings."""
                }
            ]
        }
        result = await self._run_agent(system_prompt, tools, invoke_kwargs)

        if result is None:
            return ReviewResult(
                decision="rejected",
                findings=[
                    ReviewFinding(
                        severity="blocking",
                        message=f"Review failed: {self._last_error}",
                        file=None,
                        line=None,
                    )
                ],
                summary="Review failed due to error",
            )
        return _parse_review_result(result)


class CompletionVerifierAgent(BaseValidationAgent):
    """Agent for verifying completion against acceptance criteria"""

    agent_name = "Completion verifier agent"

    async def verify(
        self,
        task: str,
        implementation_plan: Dict[str, Any],
        test_results: TestResult,
        review_results: ReviewResult,
        workspace_id: str,
        workspace_tools: WorkspaceTools,
        run_id: Optional[str] = None,
    ) -> VerificationResult:
        """Verify completion against acceptance criteria"""
        self._initialize_run(run_id, workspace_tools)

        system_prompt = """You are a completion verifier agent. Your job is to verify that the implementation meets all acceptance criteria.

For each acceptance criterion:
- Determine if it was met (passed/failed)
- Provide evidence for your decision

Your final decision should be:
- accepted: All criteria are met
- rejected: One or more criteria are not met"""

        tools = self._build_workspace_tools(workspace_id, workspace_tools, include_git_status=True, include_git_diff=True)
        invoke_kwargs = {
            "messages": [
                {
                    "role": "user",
                    "content": f"""Task: {task}

Implementation Plan:
{json.dumps(implementation_plan, indent=2)}

Acceptance Criteria:
{json.dumps(implementation_plan.get("acceptance_criteria", []), indent=2)}

Test Results:
{test_results.model_dump_json(indent=2)}

Review Results:
{review_results.model_dump_json(indent=2)}

Verify completion against the acceptance criteria."""
                }
            ]
        }
        result = await self._run_agent(system_prompt, tools, invoke_kwargs)

        if result is None:
            return VerificationResult(
                accepted=False,
                criteria_results=[
                    CriterionResult(
                        criterion="Verification",
                        passed=False,
                        evidence=f"Verification failed: {self._last_error}",
                    )
                ],
                summary="Verification failed due to error",
            )
        return _parse_verification_result(result, implementation_plan, test_results, review_results)
