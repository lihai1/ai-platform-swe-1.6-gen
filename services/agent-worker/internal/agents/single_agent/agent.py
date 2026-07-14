"""Single agent implementation for simple task execution"""
from typing import Dict, Any, Optional
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


class SingleAgent:
    """Simple single agent that handles all tasks using available tools"""

    def __init__(self, model_name: str = "qwen3.5:9b", mock_mode: bool = False, llm_provider: str = "ollama"):
        # Default to ollama with mock mode for testing
        if mock_mode:
            llm_provider = "fake"
        self.model = get_model(model_name=model_name, mock_mode=mock_mode, llm_provider=llm_provider)
        self.mock_mode = mock_mode
        self.llm_provider = llm_provider
        self._code_guidelines = load_code_guidelines()
    
    async def reason(
        self,
        task: str,
        repository_summary: Dict[str, Any],
        workspace_id: str,
        workspace_tools: WorkspaceTools,
        run_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Reason about the task and provide an answer using available tools"""
        
        # Initialize WorkspaceTools with run_id for event publishing
        if run_id and not workspace_tools.run_id:
            workspace_tools.run_id = run_id
        
        system_prompt = """You are a helpful AI assistant. Your job is to understand the task and provide a clear, accurate answer.

Follow these guidelines:
- Analyze the repository structure if available
- Understand the context of the task
- Provide clear, concise answers
- Use available tools to read files, write files, check git status, run tests, search the web, etc.
- Return a structured result with your answer"""
        
        # Add code quality guidelines if available
        if self._code_guidelines:
            system_prompt += self._code_guidelines
        
        # Create tools for the agent - all available workspace tools + web search
        tools = create_workspace_tools(
            workspace_id,
            workspace_tools,
            include_read=True,
            include_write=True,
            include_list=True,
            include_git_status=True,
            include_git_diff=True,
            include_run_tests=True,
            include_run_command=True,
            include_apply_patch=True,
        )
        tools.extend(create_web_search_tools())

        # Create agent using LangChain 1.3.x API
        graph = create_agent(
            model=self.model,
            tools=tools,
            system_prompt=system_prompt,
        )

        try:
            result = await graph.ainvoke({
                "messages": [
                    {"role": "user", "content": f"Repository summary:\n{json.dumps(repository_summary, indent=2)}\n\nTask: {task}"}
                ]
            })

            return _parse_reasoning_result(result)

        except Exception as e:
            logger.error(f"Single agent reasoning failed: {e}")
            return {
                "answer": f"Failed to complete task: {str(e)}",
                "success": False,
                "errors": [str(e)],
            }

    async def implement(
        self,
        task: str,
        implementation_plan: Dict[str, Any],
        repository_summary: Dict[str, Any],
        workspace_id: str,
        workspace_tools: WorkspaceTools,
        run_id: Optional[str] = None,
    ) -> ImplementationResult:
        """Implement the task using a single agent with all available tools"""
        
        # Initialize WorkspaceTools with run_id for event publishing
        if run_id and not workspace_tools.run_id:
            workspace_tools.run_id = run_id
        
        system_prompt = """You are a versatile software development agent. Your job is to implement the requested changes in a repository.

Follow these guidelines:
- Analyze the repository structure and understand the codebase
- Follow best practices for the detected language/framework
- Write clean, readable code with proper error handling
- Add appropriate tests when needed
- Use the available tools to read files, write files, and check git status
- Work through the task systematically
- Return a structured result with your implementation details"""
        
        # Add code quality guidelines if available
        if self._code_guidelines:
            system_prompt += self._code_guidelines
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", """Task: {task}

Implementation Plan:
{implementation_plan}

Repository Summary:
{repository_summary}

Implement the changes. Use the available tools to:
1. Read existing files to understand the codebase
2. Write or modify files as needed
3. Check git status and diff to track changes

Return a structured result with:
- files_modified: List of files you modified
- files_created: List of files you created
- lines_added: Total lines added
- lines_removed: Total lines removed
- success: Whether implementation was successful
- errors: Any errors encountered
- warnings: Any warnings""")
        ])

        # Create tools for the agent
        tools = create_workspace_tools(
            workspace_id,
            workspace_tools,
            include_read=True,
            include_write=True,
            include_list=False,
            include_git_status=True,
            include_git_diff=True,
            include_run_tests=False,
            include_run_command=False,
        )

        # Create agent using LangChain 1.3.x API
        graph = create_agent(
            model=self.model,
            tools=tools,
            system_prompt=system_prompt,
        )

        try:
            result = await graph.ainvoke({
                "messages": [
                    {
                        "role": "user",
                        "content": f"""Task: {task}

Implementation Plan:
{json.dumps(implementation_plan, indent=2)}

Repository Summary:
{json.dumps(repository_summary, indent=2)}

Implement the changes. Use the available tools to:
1. Read existing files to understand the codebase
2. Write or modify files as needed
3. Check git status and diff to track changes

Return a structured result with:
- files_modified: List of files you modified
- files_created: List of files you created
- lines_added: Total lines added
- lines_removed: Total lines removed
- success: Whether implementation was successful
- errors: Any errors encountered
- warnings: Any warnings"""
                    }
                ]
            })

            return parse_implementation_result(result)

        except Exception as e:
            logger.error(f"Single agent failed: {e}")
            return ImplementationResult(
                files_modified=[],
                files_created=[],
                lines_added=0,
                lines_removed=0,
                success=False,
                errors=[str(e)],
                warnings=[]
            )


def _parse_reasoning_result(result: dict) -> Dict[str, Any]:
    """Parse an agent result into a reasoning result"""
    output = result.get("output", "")
    errors = []
    
    # Handle LangGraph result structure with messages list
    if "messages" in result:
        messages = result.get("messages", [])
        
        # Extract final answer from the last AIMessage
        answer = "No answer provided"
        for msg in reversed(messages):
            from langchain_core.messages import AIMessage
            if isinstance(msg, AIMessage) and msg.content:
                answer = msg.content
                break
        
        # Check for errors in ToolMessages
        from langchain_core.messages import ToolMessage
        for msg in messages:
            if isinstance(msg, ToolMessage):
                try:
                    if isinstance(msg.content, str):
                        obs = json.loads(msg.content)
                    else:
                        obs = msg.content
                    
                    if obs.get("success") is False:
                        errors.append(obs.get("error", "Unknown error"))
                except Exception as e:
                    logger.warning(f"Failed to parse ToolMessage: {e}")
        
        success = not errors and bool(answer)
    else:
        # Handle legacy structure with output and intermediate_steps
        answer = output if output else "No answer provided"
        
        intermediate_steps = result.get("intermediate_steps", [])
        if intermediate_steps:
            for action, observation in intermediate_steps:
                try:
                    if isinstance(observation, str):
                        try:
                            obs = json.loads(observation)
                        except json.JSONDecodeError:
                            obs = {"output": observation, "success": True}
                    else:
                        obs = observation
                    
                    if obs.get("success") is False:
                        errors.append(obs.get("error", "Unknown error"))
                except Exception as e:
                    logger.warning(f"Failed to parse intermediate step: {e}")
        
        success = not errors and bool(output)
        
        # If there were tool calls but no final output, consider it a success
        if not output and intermediate_steps and not errors:
            answer = "Task completed successfully with tool execution."
            success = True
    
    return {
        "answer": answer,
        "success": success,
        "errors": errors,
    }
