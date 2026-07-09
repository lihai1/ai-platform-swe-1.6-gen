from typing import List, Dict, Any, Optional
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from internal.agents.model_factory import get_model
from internal.skills.registry import Skill, SkillRegistry
from internal.tools.repository import ReadOnlyRepositoryTools, RepositoryMetadataTools
from pydantic import BaseModel
import httpx


class AgentFactory:
    """Factory for creating LangChain agents with context isolation"""
    
    def __init__(self, skill_registry: SkillRegistry, control_plane_base_url: str = "http://localhost:8080"):
        self.skill_registry = skill_registry
        self.control_plane_base_url = control_plane_base_url
        self.http_client = httpx.AsyncClient()
    
    async def create_agent(
        self,
        skill_name: str,
        repository_path: Optional[str] = None,
        repository_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> AgentExecutor:
        """Create an agent with minimal context isolation"""
        
        skill = self.skill_registry.get_skill(skill_name)
        if not skill:
            raise ValueError(f"Skill {skill_name} not found in registry")
        
        # Get the model for this skill with Ollama as default provider
        provider = skill.definition.model_preferences.get("provider", "ollama")
        model_name = skill.definition.model_preferences.get("model", "qwen3.5:9b")
        model = get_model(
            provider,
            model_name,
            temperature=skill.definition.temperature,
            max_tokens=skill.definition.max_tokens
        )
        
        # Create tools based on skill capabilities
        tools = self._create_tools_for_skill(
            skill,
            repository_path,
            repository_id,
            context
        )
        
        # Create the agent with minimal context
        prompt = ChatPromptTemplate.from_messages([
            ("system", self._build_system_prompt(skill, context)),
            MessagesPlaceholder(variable_name="chat_history", optional=True),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])
        
        agent = create_tool_calling_agent(model, tools, prompt)
        
        executor = AgentExecutor(
            agent=agent,
            tools=tools,
            verbose=True,
            handle_parsing_errors=True,
            max_iterations=10,
        )
        
        return executor
    
    def _create_tools_for_skill(
        self,
        skill: Skill,
        repository_path: Optional[str],
        repository_id: Optional[str],
        context: Optional[Dict[str, Any]]
    ) -> List:
        """Create tools based on skill capabilities"""
        tools = []
        
        # Add read-only repository tools if repository is available
        if repository_path:
            repo_tools = ReadOnlyRepositoryTools(repository_path)
            
            @tool
            def list_files(pattern: str = "*", recursive: bool = True) -> List[str]:
                """List files in the repository matching a pattern"""
                return repo_tools.list_files(pattern, recursive)
            
            @tool
            def read_file(file_path: str) -> str:
                """Read a file's contents"""
                return repo_tools.read_file(file_path)
            
            @tool
            def search_files(pattern: str, file_pattern: str = "*") -> List[Dict[str, Any]]:
                """Search for a pattern in files"""
                return repo_tools.search_files(pattern, file_pattern)
            
            @tool
            def get_directory_structure(max_depth: int = 3) -> Dict[str, Any]:
                """Get simplified directory structure"""
                return repo_tools.get_directory_structure(max_depth)
            
            tools.extend([list_files, read_file, search_files, get_directory_structure])
        
        # Add repository metadata tools if repository_id is available
        if repository_id:
            metadata_tools = RepositoryMetadataTools(self.control_plane_base_url, self.http_client)
            
            @tool
            async def get_repository_metadata() -> Dict[str, Any]:
                """Get repository metadata from control plane"""
                return await metadata_tools.get_repository_metadata(repository_id)
            
            @tool
            async def get_project_metadata(project_id: str) -> Dict[str, Any]:
                """Get project metadata from control plane"""
                return await metadata_tools.get_project_metadata(project_id)
            
            tools.extend([get_repository_metadata, get_project_metadata])
        
        return tools
    
    def _build_system_prompt(self, skill: Skill, context: Optional[Dict[str, Any]]) -> str:
        """Build system prompt with minimal context"""
        
        prompt_parts = [
            f"You are a {skill.definition.agent_type} agent named {skill.definition.name}.",
            f"\n{skill.markdown}",
            f"\nYour capabilities: {', '.join(skill.definition.capabilities)}",
        ]
        
        # Add minimal context if provided
        if context:
            context_parts = []
            if "task" in context:
                context_parts.append(f"Task: {context['task']}")
            if "repository_summary" in context:
                context_parts.append(f"Repository: {context['repository_summary'].get('primary_language', 'unknown')} project")
            
            if context_parts:
                prompt_parts.append("\n\nContext:")
                prompt_parts.extend(context_parts)
        
        prompt_parts.append("\n\nUse the available tools to complete your task. Always provide structured output according to your schema.")
        
        return "\n".join(prompt_parts)
    
    async def close(self):
        """Close HTTP client"""
        await self.http_client.aclose()


def get_agent_factory(profile_name: str = "minimal") -> AgentFactory:
    """Get an agent factory instance"""
    from internal.skills.registry import get_registry
    
    registry = get_registry(profile_name)
    return AgentFactory(registry)
