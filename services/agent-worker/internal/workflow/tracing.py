import os
from langsmith import Client
from internal.config import settings


def get_langsmith_client() -> Client:
    """Get LangSmith client for tracing"""
    
    if not settings.langsmith_api_key:
        # Return None if no API key is configured
        return None
    
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = settings.langsmith_api_key
    os.environ["LANGCHAIN_PROJECT"] = settings.langsmith_project
    
    return Client()


def get_run_metadata(run_id: str, chatkit_thread_id: str = None, project_id: str = None, repository_id: str = None) -> dict:
    """Get metadata for LangSmith tracing"""
    
    metadata = {
        "run_id": run_id,
    }
    
    if chatkit_thread_id:
        metadata["chatkit_thread_id"] = chatkit_thread_id
    if project_id:
        metadata["project_id"] = project_id
    if repository_id:
        metadata["repository_id"] = repository_id
    
    return metadata
