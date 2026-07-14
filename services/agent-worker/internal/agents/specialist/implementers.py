"""Implementation agents for Go, Angular, and DevOps"""
from abc import ABC
from typing import Dict, Any, Optional, List, ClassVar
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.agents import create_agent
from langchain_core.tools import tool
from internal.agents.schemas import ImplementationResult
from internal.agents.model_factory import get_model
from internal.agents.code_guidelines import load_code_guidelines
from internal.tools.workspace import WorkspaceTools
from internal.tools.agent_tools import create_workspace_tools, create_web_search_tools
from internal.agents.result_parsers import parse_implementation_result
import json
import logging

logger = logging.getLogger(__name__)




_HUMAN_IMPLEMENTATION_TEMPLATE = """Task: {task}

Implementation Plan:
{implementation_plan}

Repository Summary:
{repository_summary}

{task_call} Return a structured result with:
- files_modified: List of files you modified
- files_created: List of files you created
- lines_added: Total lines added
- lines_removed: Total lines removed
- success: Whether implementation was successful
- errors: Any errors encountered
- warnings: Any warnings"""


class BaseImplementationAgent(ABC):
    """Shared base for the implementation specialist agents."""

    agent_name: ClassVar[str] = ""
    task_call: ClassVar[str] = ""
    system_prompt: ClassVar[str] = ""
    include_web_search: ClassVar[bool] = True

    def __init__(self, model_name: str = "gpt-4", mock_mode: bool = False, llm_provider: Optional[str] = None):
        self.model = get_model(model_name=model_name, mock_mode=mock_mode, llm_provider=llm_provider)
        self.mock_mode = mock_mode
        self.llm_provider = llm_provider
        self._code_guidelines = load_code_guidelines()

    def _initialize_run(self, run_id: Optional[str], workspace_tools: WorkspaceTools) -> None:
        """Initialize workspace tools with the run_id for event publishing."""
        if run_id and not workspace_tools.run_id:
            workspace_tools.run_id = run_id

    def _build_prompt(self) -> ChatPromptTemplate:
        """Build the ChatPromptTemplate from the agent's system prompt and task call."""
        human_prompt = _HUMAN_IMPLEMENTATION_TEMPLATE.replace("{task_call}", self.task_call)
        system_prompt = self.system_prompt
        if self._code_guidelines:
            system_prompt += self._code_guidelines
        return ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", human_prompt),
            ("placeholder", "{agent_scratchpad}"),
        ])

    def _build_implementation_tools(self, workspace_id: str, workspace_tools: WorkspaceTools) -> list:
        """Build the workspace and optional web-search tools for the agent."""
        tools = create_workspace_tools(
            workspace_id,
            workspace_tools,
            include_read=True,
            include_write=True,
            include_list=False,
            include_git_status=True,
            include_git_diff=True,
            include_run_tests=False,
            include_run_command=self.include_web_search,
        )

        if self.include_web_search:
            tools.extend(create_web_search_tools())

        return tools

    async def _execute_agent(self, graph, task: str, implementation_plan: Dict[str, Any], repository_summary: Dict[str, Any]) -> ImplementationResult:
        """Run the agent and parse the result."""
        result = await graph.ainvoke({
            "messages": [
                {
                    "role": "user",
                    "content": f"""Task: {task}

Implementation Plan:
{json.dumps(implementation_plan, indent=2)}

Repository Summary:
{json.dumps(repository_summary, indent=2)}"""
                }
            ]
        })
        return parse_implementation_result(result)

    async def implement(
        self,
        task: str,
        implementation_plan: Dict[str, Any],
        repository_summary: Dict[str, Any],
        workspace_id: str,
        workspace_tools: WorkspaceTools,
        run_id: Optional[str] = None,
    ) -> ImplementationResult:
        """Run the implementation agent for the configured technology."""
        self._initialize_run(run_id, workspace_tools)

        tools = self._build_implementation_tools(workspace_id, workspace_tools)
        system_prompt = self._build_prompt()
        graph = create_agent(
            model=self.model,
            tools=tools,
            system_prompt=system_prompt,
        )

        try:
            return await self._execute_agent(graph, task, implementation_plan, repository_summary)
        except Exception as e:
            logger.error("%s failed: %s", self.agent_name, e)
            return ImplementationResult(
                files_modified=[],
                files_created=[],
                lines_added=0,
                lines_removed=0,
                success=False,
                errors=[str(e)],
                warnings=[],
            )


class GoDeveloperAgent(BaseImplementationAgent):
    """Agent for Go backend development"""

    agent_name = "Go developer agent"
    task_call = "Implement the changes."
    system_prompt = """You are a Go developer agent. Your job is to implement the requested changes in a Go repository.

Follow these guidelines:
- Follow Go best practices and idioms
- Use the existing project structure
- Write clean, readable code with proper error handling
- Add appropriate tests
- Follow the implementation plan provided
- Only modify files that are in the implementation plan
- You can search the web for Go documentation, best practices, and examples"""


class AngularDeveloperAgent(BaseImplementationAgent):
    """Agent for Angular component development"""

    agent_name = "Angular developer agent"
    task_call = "Implement the changes."
    system_prompt = """You are an Angular developer agent. Your job is to implement the requested changes in an Angular repository.

Follow these guidelines:
- Use Angular 22+ with standalone components
- Follow Angular best practices and style guide
- Use reactive forms and observables where appropriate
- Write clean, readable TypeScript code
- Add appropriate unit tests
- Follow the implementation plan provided
- Only modify files that are in the implementation plan
- You can search the web for Angular documentation, best practices, and examples"""


class AngularUIDeveloperAgent(BaseImplementationAgent):
    """Agent for Angular UI/UX work"""

    agent_name = "Angular UI developer agent"
    task_call = "Implement the UI changes."
    system_prompt = """You are an Angular UI developer agent. Your job is to implement UI/UX changes in an Angular repository.

Follow these guidelines:
- Focus on templates, styling, and visual design
- Use modern CSS (Flexbox, Grid, CSS Variables)
- Ensure responsive design
- Follow accessibility best practices (ARIA labels, keyboard navigation)
- Use Angular Material or similar component library when appropriate
- Follow the implementation plan provided
- You can search the web for CSS/HTML best practices, design patterns, and examples"""


class DevOpsDeveloperAgent(BaseImplementationAgent):
    """Agent for DevOps and infrastructure changes"""

    agent_name = "DevOps developer agent"
    task_call = "Implement the DevOps changes."
    system_prompt = """You are a DevOps developer agent. Your job is to implement infrastructure and deployment changes.

Follow these guidelines:
- Modify Dockerfiles, Docker Compose, Kubernetes manifests, Helm charts
- Update CI/CD pipelines (GitHub Actions, GitLab CI, etc.)
- Follow infrastructure as code best practices
- Ensure security best practices (non-root containers, minimal base images)
- Follow the implementation plan provided
- You can search the web for DevOps best practices, documentation, and examples"""
