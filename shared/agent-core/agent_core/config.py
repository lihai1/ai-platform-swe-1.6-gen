from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://agentic:agentic@localhost:5432/agentic"
    jwt_secret: str = "dev-secret-change-in-production"
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"
    langsmith_api_key: str = ""
    langsmith_project: str = "agentic-engineering-platform"
    
    class Config:
        env_file = ".env"

settings = Settings()
