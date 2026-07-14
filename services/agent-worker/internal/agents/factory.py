from typing import List, Dict, Any, Optional
from langchain.agents import create_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from internal.agents.model_factory import get_model
from internal.agents.code_guidelines import load_code_guidelines
from internal.skills.registry import Skill, SkillRegistry
from internal.tools.agent_tools import create_repository_tools, create_repository_metadata_tools
from pydantic import BaseModel
import httpx


class AgentFactory:
    """Factory for creating LangChain agents with context isolation"""
    
    def __init__(self, skill_registry: SkillRegistry, control_plane_base_url: str = "http://localhost:8080"):
        self.skill_registry = skill_registry
        self.control_plane_base_url = control_plane_base_url
        self.http_client = httpx.AsyncClient()
        self._code_guidelines = load_code_guidelines()
    
    async def create_agent(
        self,
        skill_name: str,
        repository_path: Optional[str] = None,
        repository_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ):
        """Create an agent with minimal context isolation"""
        
        skill = self.skill_registry.get_skill(skill_name)
        if not skill:
            raise ValueError(f"Skill {skill_name} not found in registry")
        
        # Get the model for this skill with Ollama as default provider
        provider = skill.definition.model_preferences.get("provider", "ollama")
        model_name = skill.definition.model_preferences.get("model", "qwen3.5:9b")
        mock_mode = context.get("mock_mode", False) if context else False
        model = get_model(
            provider,
            model_name,
            temperature=skill.definition.temperature,
            max_tokens=skill.definition.max_tokens,
            mock_mode=mock_mode
        )
        
        # Create tools based on skill capabilities
        tools = self._create_tools_for_skill(
            skill,
            repository_path,
            repository_id,
            context
        )

        # Create the agent using LangChain 1.3.x API
        system_prompt = self._build_system_prompt(skill, context)
        graph = create_agent(
            model=model,
            tools=tools,
            system_prompt=system_prompt,
        )

        # Return agent and tools for invocation (LangChain 1.3+ pattern)
        return {
            "agent": graph,
            "tools": tools,
            "system_prompt": system_prompt,
            "model": model
        }
    
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
            tools.extend(create_repository_tools(repository_path))
        
        # Add repository metadata tools if repository_id is available
        if repository_id:
            project_id = context.get("project_id") if context else None
            tools.extend(create_repository_metadata_tools(
                self.control_plane_base_url,
                self.http_client,
                repository_id=repository_id,
                project_id=project_id,
            ))
        
        return tools
    
    def _build_system_prompt(self, skill: Skill, context: Optional[Dict[str, Any]]) -> str:
        """Build system prompt with minimal context"""
        
        prompt_parts = [
            f"You are a {skill.definition.agent_type} agent named {skill.definition.name}.",
            f"\n{skill.markdown}",
            f"\nYour capabilities: {', '.join(skill.definition.capabilities)}",
        ]
        
        # Add code quality guidelines if available
        if self._code_guidelines:
            prompt_parts.append(self._code_guidelines)
        
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
