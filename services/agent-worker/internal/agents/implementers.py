"""Implementation agents for Go, Angular, and DevOps"""
from typing import Dict, Any, List, Optional
from langchain_core.prompts import ChatPromptTemplate
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.tools import tool
from internal.agents.schemas import ImplementationResult
from internal.agents.model_factory import get_model
from internal.tools.workspace import WorkspaceTools
import json
import logging

logger = logging.getLogger(__name__)


class GoDeveloperAgent:
    """Agent for Go backend development"""
    
    def __init__(self, model_name: str = "gpt-4"):
        self.model = get_model(model_name)
    
    async def implement(
        self,
        task: str,
        implementation_plan: Dict[str, Any],
        repository_summary: Dict[str, Any],
        workspace_id: str,
        workspace_tools: WorkspaceTools,
    ) -> ImplementationResult:
        """Implement Go changes"""
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a Go developer agent. Your job is to implement the requested changes in a Go repository.

Follow these guidelines:
- Follow Go best practices and idioms
- Use the existing project structure
- Write clean, readable code with proper error handling
- Add appropriate tests
- Follow the implementation plan provided
- Only modify files that are in the implementation plan"""),
            ("human", """Task: {task}

Implementation Plan:
{implementation_plan}

Repository Summary:
{repository_summary}

Implement the changes. Return a structured result with:
- files_modified: List of files you modified
- files_created: List of files you created
- lines_added: Total lines added
- lines_removed: Total lines removed
- success: Whether implementation was successful
- errors: Any errors encountered
- warnings: Any warnings""")
        ])
        
        # Create tools for the agent
        @tool
        async def write_file(file_path: str, content: str) -> str:
            """Write a file to the workspace"""
            result = await workspace_tools.write_file(workspace_id, file_path, content)
            return json.dumps(result)
        
        @tool
        async def read_file(file_path: str) -> str:
            """Read a file from the workspace"""
            result = await workspace_tools.read_file(workspace_id, file_path)
            return json.dumps(result)
        
        @tool
        async def git_status() -> str:
            """Get git status"""
            result = await workspace_tools.git_status(workspace_id)
            return json.dumps(result)
        
        @tool
        async def git_diff() -> str:
            """Get git diff"""
            result = await workspace_tools.git_diff(workspace_id)
            return json.dumps(result)
        
        tools = [write_file, read_file, git_status, git_diff]
        
        # Create agent
        agent = create_tool_calling_agent(self.model, tools, prompt)
        agent_executor = AgentExecutor(
            agent=agent,
            tools=tools,
            verbose=False,
            handle_parsing_errors=True,
        )
        
        try:
            result = await agent_executor.ainvoke({
                "task": task,
                "implementation_plan": json.dumps(implementation_plan, indent=2),
                "repository_summary": json.dumps(repository_summary, indent=2),
            })
            
            # Parse the output to extract implementation result
            # In production, this would use structured output
            return ImplementationResult(
                files_modified=[],
                files_created=[],
                lines_added=0,
                lines_removed=0,
                success=True,
                errors=[],
                warnings=[]
            )
            
        except Exception as e:
            logger.error(f"Go developer agent failed: {e}")
            return ImplementationResult(
                files_modified=[],
                files_created=[],
                lines_added=0,
                lines_removed=0,
                success=False,
                errors=[str(e)],
                warnings=[]
            )


class AngularDeveloperAgent:
    """Agent for Angular component development"""
    
    def __init__(self, model_name: str = "gpt-4"):
        self.model = get_model(model_name)
    
    async def implement(
        self,
        task: str,
        implementation_plan: Dict[str, Any],
        repository_summary: Dict[str, Any],
        workspace_id: str,
        workspace_tools: WorkspaceTools,
    ) -> ImplementationResult:
        """Implement Angular changes"""
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are an Angular developer agent. Your job is to implement the requested changes in an Angular repository.

Follow these guidelines:
- Use Angular 22+ with standalone components
- Follow Angular best practices and style guide
- Use reactive forms and observables where appropriate
- Write clean, readable TypeScript code
- Add appropriate unit tests
- Follow the implementation plan provided
- Only modify files that are in the implementation plan"""),
            ("human", """Task: {task}

Implementation Plan:
{implementation_plan}

Repository Summary:
{repository_summary}

Implement the changes. Return a structured result with:
- files_modified: List of files you modified
- files_created: List of files you created
- lines_added: Total lines added
- lines_removed: Total lines removed
- success: Whether implementation was successful
- errors: Any errors encountered
- warnings: Any warnings""")
        ])
        
        # Create tools (same as Go developer)
        @tool
        async def write_file(file_path: str, content: str) -> str:
            """Write a file to the workspace"""
            result = await workspace_tools.write_file(workspace_id, file_path, content)
            return json.dumps(result)
        
        @tool
        async def read_file(file_path: str) -> str:
            """Read a file from the workspace"""
            result = await workspace_tools.read_file(workspace_id, file_path)
            return json.dumps(result)
        
        @tool
        async def git_status() -> str:
            """Get git status"""
            result = await workspace_tools.git_status(workspace_id)
            return json.dumps(result)
        
        @tool
        async def git_diff() -> str:
            """Get git diff"""
            result = await workspace_tools.git_diff(workspace_id)
            return json.dumps(result)
        
        tools = [write_file, read_file, git_status, git_diff]
        
        # Create agent
        agent = create_tool_calling_agent(self.model, tools, prompt)
        agent_executor = AgentExecutor(
            agent=agent,
            tools=tools,
            verbose=False,
            handle_parsing_errors=True,
        )
        
        try:
            result = await agent_executor.ainvoke({
                "task": task,
                "implementation_plan": json.dumps(implementation_plan, indent=2),
                "repository_summary": json.dumps(repository_summary, indent=2),
            })
            
            return ImplementationResult(
                files_modified=[],
                files_created=[],
                lines_added=0,
                lines_removed=0,
                success=True,
                errors=[],
                warnings=[]
            )
            
        except Exception as e:
            logger.error(f"Angular developer agent failed: {e}")
            return ImplementationResult(
                files_modified=[],
                files_created=[],
                lines_added=0,
                lines_removed=0,
                success=False,
                errors=[str(e)],
                warnings=[]
            )


class AngularUIDeveloperAgent:
    """Agent for Angular UI/UX work"""
    
    def __init__(self, model_name: str = "gpt-4"):
        self.model = get_model(model_name)
    
    async def implement(
        self,
        task: str,
        implementation_plan: Dict[str, Any],
        repository_summary: Dict[str, Any],
        workspace_id: str,
        workspace_tools: WorkspaceTools,
    ) -> ImplementationResult:
        """Implement Angular UI changes"""
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are an Angular UI developer agent. Your job is to implement UI/UX changes in an Angular repository.

Follow these guidelines:
- Focus on templates, styling, and visual design
- Use modern CSS (Flexbox, Grid, CSS Variables)
- Ensure responsive design
- Follow accessibility best practices (ARIA labels, keyboard navigation)
- Use Angular Material or similar component library when appropriate
- Follow the implementation plan provided"""),
            ("human", """Task: {task}

Implementation Plan:
{implementation_plan}

Repository Summary:
{repository_summary}

Implement the UI changes. Return a structured result with:
- files_modified: List of files you modified
- files_created: List of files you created
- lines_added: Total lines added
- lines_removed: Total lines removed
- success: Whether implementation was successful
- errors: Any errors encountered
- warnings: Any warnings""")
        ])
        
        # Create tools
        @tool
        async def write_file(file_path: str, content: str) -> str:
            """Write a file to the workspace"""
            result = await workspace_tools.write_file(workspace_id, file_path, content)
            return json.dumps(result)
        
        @tool
        async def read_file(file_path: str) -> str:
            """Read a file from the workspace"""
            result = await workspace_tools.read_file(workspace_id, file_path)
            return json.dumps(result)
        
        @tool
        async def git_status() -> str:
            """Get git status"""
            result = await workspace_tools.git_status(workspace_id)
            return json.dumps(result)
        
        @tool
        async def git_diff() -> str:
            """Get git diff"""
            result = await workspace_tools.git_diff(workspace_id)
            return json.dumps(result)
        
        tools = [write_file, read_file, git_status, git_diff]
        
        # Create agent
        agent = create_tool_calling_agent(self.model, tools, prompt)
        agent_executor = AgentExecutor(
            agent=agent,
            tools=tools,
            verbose=False,
            handle_parsing_errors=True,
        )
        
        try:
            result = await agent_executor.ainvoke({
                "task": task,
                "implementation_plan": json.dumps(implementation_plan, indent=2),
                "repository_summary": json.dumps(repository_summary, indent=2),
            })
            
            return ImplementationResult(
                files_modified=[],
                files_created=[],
                lines_added=0,
                lines_removed=0,
                success=True,
                errors=[],
                warnings=[]
            )
            
        except Exception as e:
            logger.error(f"Angular UI developer agent failed: {e}")
            return ImplementationResult(
                files_modified=[],
                files_created=[],
                lines_added=0,
                lines_removed=0,
                success=False,
                errors=[str(e)],
                warnings=[]
            )


class DevOpsDeveloperAgent:
    """Agent for DevOps and infrastructure changes"""
    
    def __init__(self, model_name: str = "gpt-4"):
        self.model = get_model(model_name)
    
    async def implement(
        self,
        task: str,
        implementation_plan: Dict[str, Any],
        repository_summary: Dict[str, Any],
        workspace_id: str,
        workspace_tools: WorkspaceTools,
    ) -> ImplementationResult:
        """Implement DevOps changes"""
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are a DevOps developer agent. Your job is to implement infrastructure and deployment changes.

Follow these guidelines:
- Modify Dockerfiles, Docker Compose, Kubernetes manifests, Helm charts
- Update CI/CD pipelines (GitHub Actions, GitLab CI, etc.)
- Follow infrastructure as code best practices
- Ensure security best practices (non-root containers, minimal base images)
- Follow the implementation plan provided"""),
            ("human", """Task: {task}

Implementation Plan:
{implementation_plan}

Repository Summary:
{repository_summary}

Implement the DevOps changes. Return a structured result with:
- files_modified: List of files you modified
- files_created: List of files you created
- lines_added: Total lines added
- lines_removed: Total lines removed
- success: Whether implementation was successful
- errors: Any errors encountered
- warnings: Any warnings""")
        ])
        
        # Create tools
        @tool
        async def write_file(file_path: str, content: str) -> str:
            """Write a file to the workspace"""
            result = await workspace_tools.write_file(workspace_id, file_path, content)
            return json.dumps(result)
        
        @tool
        async def read_file(file_path: str) -> str:
            """Read a file from the workspace"""
            result = await workspace_tools.read_file(workspace_id, file_path)
            return json.dumps(result)
        
        @tool
        async def git_status() -> str:
            """Get git status"""
            result = await workspace_tools.git_status(workspace_id)
            return json.dumps(result)
        
        @tool
        async def git_diff() -> str:
            """Get git diff"""
            result = await workspace_tools.git_diff(workspace_id)
            return json.dumps(result)
        
        tools = [write_file, read_file, git_status, git_diff]
        
        # Create agent
        agent = create_tool_calling_agent(self.model, tools, prompt)
        agent_executor = AgentExecutor(
            agent=agent,
            tools=tools,
            verbose=False,
            handle_parsing_errors=True,
        )
        
        try:
            result = await agent_executor.ainvoke({
                "task": task,
                "implementation_plan": json.dumps(implementation_plan, indent=2),
                "repository_summary": json.dumps(repository_summary, indent=2),
            })
            
            return ImplementationResult(
                files_modified=[],
                files_created=[],
                lines_added=0,
                lines_removed=0,
                success=True,
                errors=[],
                warnings=[]
            )
            
        except Exception as e:
            logger.error(f"DevOps developer agent failed: {e}")
            return ImplementationResult(
                files_modified=[],
                files_created=[],
                lines_added=0,
                lines_removed=0,
                success=False,
                errors=[str(e)],
                warnings=[]
            )
