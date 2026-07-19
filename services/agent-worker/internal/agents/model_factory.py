from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_ollama import ChatOllama
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, AIMessage, ToolCall
from langchain_core.outputs import ChatResult, ChatGeneration
from langchain_core.callbacks import Callbacks
from typing import Any, Dict, List, Optional
from internal.config import settings
import logging
import json
from pydantic import Field

logger = logging.getLogger(__name__)

class FakeChatModel(BaseChatModel):
    """Fake LLM that returns deterministic tool calls / structured output without external API calls"""
    
    model_name: str = Field(default="fake-model")
    _bound_tools: Optional[List] = None
    _call_count: int = 0
    _schema: Optional[type] = None
    
    def bind_tools(self, tools: List, tool_choice: Any = None, **kwargs: Any):
        """Bind tools and return self so the agent executor can invoke them"""
        # Only reset call_count if tools actually change
        if self._bound_tools != tools:
            self._bound_tools = tools
            self._call_count = 0
        return self
    
    def with_structured_output(self, schema: Any, **kwargs: Any):
        """Return a runnable that yields a deterministic structured output"""
        from langchain_core.runnables import RunnableLambda
        self._schema = schema
        return RunnableLambda(lambda x: self._default_structured_output(schema))
    
    def _default_structured_output(self, schema: type) -> Any:
        """Return a default instance of the schema with sensible fake values"""
        schema_name = getattr(schema, "__name__", "")
        defaults: Dict[str, Any] = {
            "SkillsLeadDecision": {
                "selected_specialists": ["go-developer"],
                "reasoning": "Fake skills-lead selected go-developer as the most relevant specialist.",
                "estimated_complexity": "low",
                "suggested_phases": ["implementing", "testing", "reviewing", "verifying"]
            },
            "RepositorySummary": {
                "primary_language": "Go",
                "frameworks": ["Gin"],
                "project_type": "web",
                "total_files": 5,
                "test_files": 1,
                "main_source_files": 2,
                "config_files": 2,
                "directory_structure": {},
                "key_files": ["go.mod", "main.go"],
                "build_system": "go modules",
                "test_framework": "go test",
                "dependencies": ["github.com/gin-gonic/gin"]
            },
            "ImplementationPlan": {
                "description": "Create a simple Go file and run the test suite",
                "files_expected_to_change": ["hello.go"],
                "acceptance_criteria": [
                    "A Go file is created",
                    "Tests pass"
                ],
                "estimated_steps": 3,
                "risk_factors": ["None"],
                "suggested_approach": "Create a small Go file and execute the tests",
                "dependencies_to_add": None,
                "tests_to_write": ["hello_test.go"]
            }
        }
        data = defaults.get(schema_name, {})
        return schema.model_validate(data)
    
    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Generate a deterministic sequence of tool calls, then a final answer"""
        self._call_count += 1
        
        if self._bound_tools:
            tool_call = self._next_tool_call()
            if tool_call:
                response = AIMessage(content="", tool_calls=[tool_call])
                return ChatResult(generations=[ChatGeneration(message=response)])
        
        # Final answer once all tools are exercised
        final_content = self._final_answer()
        response = AIMessage(content=final_content)
        return ChatResult(generations=[ChatGeneration(message=response)])
    
    def _next_tool_call(self) -> Optional[ToolCall]:
        """Return the next deterministic tool call based on available tools and call count"""
        import uuid as uuid_mod
        tool_names = [getattr(t, "name", str(t)) for t in self._bound_tools or []]
        has = lambda n: n in tool_names
        n = self._call_count
        call: Optional[ToolCall] = None

        # go-developer writes hello.go and checks status/diff
        if has("write_file"):
            if n == 1:
                content = (
                    "package main\n\n"
                    "import \"fmt\"\n\n"
                    "// Hello returns a greeting message.\n"
                    "func Hello() string {\n"
                    "\treturn \"Hello, real implementation!\"\n"
                    "}\n\n"
                    "func main() {\n"
                    "\tfmt.Println(Hello())\n"
                    "}\n"
                )
                call = ToolCall(name="write_file", args={"file_path": "hello.go", "content": content}, id=str(uuid_mod.uuid4()))
            elif n == 2:
                call = ToolCall(name="git_status", args={}, id=str(uuid_mod.uuid4()))
            elif n == 3:
                call = ToolCall(name="git_diff", args={}, id=str(uuid_mod.uuid4()))
            else:
                # Stop after 3 tool calls for write_file case
                return None
        # backend-test-engineer runs the real test suite
        elif has("run_tests"):
            if n == 1:
                call = ToolCall(name="run_tests", args={}, id=str(uuid_mod.uuid4()))
            elif n == 2:
                call = ToolCall(name="read_file", args={"file_path": "hello.go"}, id=str(uuid_mod.uuid4()))
            else:
                return None
        # completion verifier
        elif has("git_status") and has("git_diff"):
            if n == 1:
                call = ToolCall(name="git_status", args={}, id=str(uuid_mod.uuid4()))
            elif n == 2:
                call = ToolCall(name="git_diff", args={}, id=str(uuid_mod.uuid4()))
            elif n == 3:
                call = ToolCall(name="read_file", args={"file_path": "hello.go"}, id=str(uuid_mod.uuid4()))
            else:
                return None
        # code reviewer
        elif has("git_diff") and has("read_file"):
            if n == 1:
                call = ToolCall(name="git_diff", args={}, id=str(uuid_mod.uuid4()))
            elif n == 2:
                call = ToolCall(name="read_file", args={"file_path": "hello.go"}, id=str(uuid_mod.uuid4()))
            else:
                return None
        # fallback
        elif has("read_file"):
            if n == 1:
                call = ToolCall(name="read_file", args={"file_path": "hello.go"}, id=str(uuid_mod.uuid4()))

        return call
    
    def _final_answer(self) -> str:
        """Return a final answer based on the bound tools"""
        tool_names = [getattr(t, "name", str(t)) for t in self._bound_tools or []]
        if "write_file" in tool_names:
            return "Implementation complete. Created hello.go and verified the changes."
        if "run_tests" in tool_names:
            return "All tests passed."
        if "git_diff" in tool_names and "read_file" in tool_names:
            return "approved"
        if "git_status" in tool_names:
            return "Verification passed."
        return "Task completed."

    @property
    def _llm_type(self) -> str:
        return "fake"

    @property
    def _identifying_params(self) -> dict:
        return {"model_name": self.model_name}


def get_model(
    provider: Optional[str] = None,
    model_name: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 1000,
    mock_mode: bool = False,
    llm_provider: Optional[str] = None,
):
    """Factory function to create LLM instances based on provider or llm_provider"""
    provider = provider or settings.model_provider or "ollama"
    model_name = model_name or settings.model_name or "qwen3.5:9b"

    # Use explicit llm_provider when given; keep mock_mode as a backwards-compatible alias for fake.
    effective_llm_provider = llm_provider
    if not effective_llm_provider and mock_mode:
        effective_llm_provider = "fake"
    if not effective_llm_provider:
        effective_llm_provider = provider

    if effective_llm_provider == "fake":
        logger.info(f"[MODEL_FACTORY] Using fake LLM (llm_provider=fake, model_name={model_name})")
        return FakeChatModel(model_name=model_name)

    if effective_llm_provider == "openai":
        return ChatOpenAI(
            model=model_name,
            api_key=settings.openai_api_key,
            temperature=temperature,
            max_tokens=max_tokens,
            streaming=True
        )
    elif effective_llm_provider == "anthropic":
        return ChatAnthropic(
            model=model_name,
            api_key=settings.anthropic_api_key,
            temperature=temperature,
            max_tokens=max_tokens,
            streaming=True
        )
    elif effective_llm_provider == "ollama":
        return ChatOllama(
            model=model_name,
            base_url=settings.ollama_base_url,
            temperature=temperature,
            max_tokens=max_tokens,
            streaming=True
        )
    else:
        raise ValueError(f"Unknown provider: {effective_llm_provider}")
