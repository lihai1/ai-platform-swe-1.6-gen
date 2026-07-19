import re

# Patch crew.py
crew_path = "src/stock_analysis/crew.py"
with open(crew_path) as f:
    text = f.read()

config_block = """\nDEFAULT_RAG_CONFIG = {
    \"embedding_model\": {
        \"provider\": \"ollama\",
        \"config\": {
            \"url\": \"http://ollama:11434/api/embeddings\",
            \"model_name\": \"nomic-embed-text\",
        },
    },
    \"vectordb\": {
        \"provider\": \"chromadb\",
        \"config\": {},
    },
}
"""

text = text.replace(
    'llm = LLM(model="ollama/llama3.1", base_url="http://ollama:11434")\n',
    'llm = LLM(model="ollama/llama3.1", base_url="http://ollama:11434")\n' + config_block
)

text = re.sub(r"ScrapeWebsiteTool\(\)", "ScrapeWebsiteTool(config=DEFAULT_RAG_CONFIG)", text)
text = re.sub(r"WebsiteSearchTool\(\)", "WebsiteSearchTool(config=DEFAULT_RAG_CONFIG)", text)
text = re.sub(r'SEC10QTool\("AMZN"\)', 'SEC10QTool("AMZN", config=DEFAULT_RAG_CONFIG)', text)
text = re.sub(r'SEC10KTool\("AMZN"\)', 'SEC10KTool("AMZN", config=DEFAULT_RAG_CONFIG)', text)
text = re.sub(r"SEC10QTool\(\)", "SEC10QTool(config=DEFAULT_RAG_CONFIG)", text)
text = re.sub(r"SEC10KTool\(\)", "SEC10KTool(config=DEFAULT_RAG_CONFIG)", text)

with open(crew_path, "w") as f:
    f.write(text)

# Patch sec_tools.py
sec_path = "src/stock_analysis/tools/sec_tools.py"
with open(sec_path) as f:
    text = f.read()

text = text.replace(
    "def __init__(self, stock_name: Optional[str] = None, **kwargs):",
    "def __init__(self, stock_name: Optional[str] = None, **kwargs):\n        kwargs.setdefault(\"config\", DEFAULT_RAG_CONFIG)"
)

text = text.replace(
    "class FixedSEC10KToolSchema",
    """DEFAULT_RAG_CONFIG = {
    \"embedding_model\": {
        \"provider\": \"ollama\",
        \"config\": {
            \"url\": \"http://ollama:11434/api/embeddings\",
            \"model_name\": \"nomic-embed-text\",
        },
    },
    \"vectordb\": {
        \"provider\": \"chromadb\",
        \"config\": {},
    },
}

class FixedSEC10KToolSchema"""
)

with open(sec_path, "w") as f:
    f.write(text)

print("Patched crew.py and sec_tools.py")
