from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_ollama import ChatOllama
from internal.config import settings

def get_model(provider: str, model_name: str, temperature: float = 0.7, max_tokens: int = 1000):
    """Factory function to create LLM instances based on provider"""
    if provider == "openai":
        return ChatOpenAI(
            model=model_name,
            api_key=settings.openai_api_key,
            temperature=temperature,
            max_tokens=max_tokens,
            streaming=True
        )
    elif provider == "anthropic":
        return ChatAnthropic(
            model=model_name,
            api_key=settings.anthropic_api_key,
            temperature=temperature,
            max_tokens=max_tokens,
            streaming=True
        )
    elif provider == "ollama":
        return ChatOllama(
            model=model_name,
            base_url=settings.ollama_base_url,
            temperature=temperature,
            max_tokens=max_tokens,
            streaming=True
        )
    else:
        raise ValueError(f"Unknown provider: {provider}")
