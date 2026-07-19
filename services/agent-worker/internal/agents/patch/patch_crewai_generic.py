#!/usr/bin/env python3
"""Generic CrewAI example patcher.

Walks through a CrewAI example project (flat or src layout) and applies the
common refactorings needed to run the example with the latest crewai/crewai-tools
and Ollama without OpenAI API keys.
"""

import argparse
import re
import sys
from pathlib import Path


def get_python_files(project_dir: Path) -> list[Path]:
    return [
        p
        for p in project_dir.rglob("*.py")
        if ".venv" not in p.parts and "__pycache__" not in p.parts
    ]


def detect_package_name(project_dir: Path) -> str:
    """Detect the package name for src-layout or flat-layout projects."""
    src_dir = project_dir / "src"
    if src_dir.exists():
        for child in src_dir.iterdir():
            if child.is_dir() and (child / "main.py").exists():
                return child.name
    # fallback: directory with main.py
    if (project_dir / "main.py").exists():
        return project_dir.name.replace("-", "_")
    return project_dir.name.replace("-", "_")


def create_package_init(project_dir: Path, package_name: str, src_layout: bool) -> None:
    """Ensure the package root has an __init__.py so absolute imports work."""
    if src_layout:
        init_file = project_dir / "src" / package_name / "__init__.py"
    else:
        init_file = project_dir / "__init__.py"
    if not init_file.exists():
        init_file.parent.mkdir(parents=True, exist_ok=True)
        init_file.write_text("")
        print(f"Created {init_file}")


def is_src_layout(project_dir: Path) -> bool:
    return (project_dir / "src").is_dir()


def fix_base_tool_imports(text: str) -> str:
    # from crewai_tools import BaseTool -> from crewai.tools import BaseTool
    text = re.sub(
        r"from\s+crewai_tools\s+import\s+(.*?)BaseTool",
        r"from crewai.tools import \1BaseTool",
        text,
    )
    # from langchain.tools import tool / from langchain.agents import tool
    text = re.sub(
        r"from\s+langchain(?:\.[a-zA-Z_]+)?\s+import\s+tool\n",
        "from crewai.tools import tool\n",
        text,
    )
    return text


def fix_langchain_llm(text: str, ollama_url: str, ollama_model: str) -> str:
    """Replace langchain OpenAI/Ollama imports and instantiations with crewai.LLM."""
    # Remove langchain LLM imports (LLM import is handled by inject_llm_into_agents)
    text = re.sub(
        r"from\s+langchain(?:_community)?\.llms\s+import\s+[^\n]+\n",
        "",
        text,
    )
    text = re.sub(
        r"from\s+langchain_openai\s+import\s+[^\n]+\n",
        "",
        text,
    )
    text = re.sub(
        r"from\s+langchain\.chat_models\s+import\s+[^\n]+\n",
        "",
        text,
    )

    # Replace assignments like OpenAIGPT35 = ChatOpenAI(...) or llm = OpenAI(...)
    text = re.sub(
        r"[A-Za-z_][A-Za-z0-9_]*\s*=\s*(?:ChatOpenAI|OpenAI|Ollama)\s*\([^\)]*\)",
        f'llm = LLM(model="ollama/{ollama_model}", base_url="{ollama_url}")',
        text,
    )

    # Replace DuckDuckGoSearchRun with crewai_tools DuckDuckGoSearchTool
    text = re.sub(
        r"DuckDuckGoSearchRun\s*\(\s*\)",
        "DuckDuckGoSearchTool()",
        text,
    )
    text = re.sub(
        r"from\s+langchain\.tools\s+import\s+DuckDuckGoSearchRun",
        "from crewai_tools import DuckDuckGoSearchTool",
        text,
    )

    return text


def fix_project_imports(text: str, package_name: str, src_layout: bool) -> str:
    """Make relative example imports absolute."""
    # from crew import X -> from package.crew import X
    text = re.sub(
        r"from\s+crew\s+import\s+",
        f"from {package_name}.crew import ",
        text,
    )
    # from tools.X import -> from package.tools.X import
    text = re.sub(
        r"from\s+tools\.([a-zA-Z0-9_]+)\s+import\s+",
        f"from {package_name}.tools.\\1 import ",
        text,
    )

    if not src_layout:
        # from agents import X -> from package.agents import X
        text = re.sub(
            r"from\s+agents\s+import\s+",
            f"from {package_name}.agents import ",
            text,
        )
        # from tasks import X -> from package.tasks import X
        text = re.sub(
            r"from\s+tasks\s+import\s+",
            f"from {package_name}.tasks import ",
            text,
        )

    return text


def fix_pydantic_v1(text: str) -> str:
    return re.sub(
        r"from\s+pydantic\.v1\s+import\s+([^\n]+)",
        r"from pydantic import \1",
        text,
    )


def remove_embedchain(text: str) -> str:
    text = re.sub(r"from\s+embedchain[^\n]*\n", "", text)
    text = re.sub(r"from\s+embedchain\.models[^\n]*\n", "", text)
    text = re.sub(r"kwargs\[\"data_type\"\]\s*=\s*DataType\.TEXT", "# kwargs[\"data_type\"] = DataType.TEXT", text)
    return text


def insert_after_imports(text: str, block: str) -> str:
    """Insert a block after the top-level import section (before first class/assignment)."""
    # Find the first top-level non-import, non-comment, non-blank line
    lines = text.splitlines(keepends=True)
    insert_at = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith(("from ", "import ")):
            insert_at = i + 1
            continue
        break
    return "".join(lines[:insert_at]) + block + "".join(lines[insert_at:])


def add_default_rag_config(text: str, ollama_url: str, ollama_model: str) -> str:
    """Add DEFAULT_RAG_CONFIG and default Ollama LLM to crew.py and inject config into RagTool constructors."""
    if "DEFAULT_RAG_CONFIG = {" not in text:
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

llm = LLM(model="ollama/__OLLAMA_MODEL__", base_url="__OLLAMA_URL__")
"""
        config_block = config_block.replace("__OLLAMA_MODEL__", ollama_model).replace("__OLLAMA_URL__", ollama_url)
        text = insert_after_imports(text, config_block)

    # Inject config=DEFAULT_RAG_CONFIG into common tool constructors
    for tool in (
        "ScrapeWebsiteTool",
        "WebsiteSearchTool",
        "TXTSearchTool",
        "DirectorySearchTool",
        "PDFSearchTool",
        "DOCXSearchTool",
        "CSVSearchTool",
    ):
        text = re.sub(
            rf"({tool})\s*\(\)",
            r"\1(config=DEFAULT_RAG_CONFIG)",
            text,
        )

    # Replace SerperDevTool with an Ollama-backed WebsiteSearchTool
    text = re.sub(
        r"SerperDevTool\s*\(\s*\)",
        "WebsiteSearchTool(config=DEFAULT_RAG_CONFIG)",
        text,
    )
    text = re.sub(
        r"from\s+crewai_tools\s+import\s+SerperDevTool",
        "from crewai_tools import WebsiteSearchTool",
        text,
    )

    return text


def inject_llm_into_agents(text: str, ollama_url: str, ollama_model: str) -> str:
    """For CrewBase projects, ensure LLM import and inject llm=llm into Agent(...) calls."""
    # Strip any pre-existing llm=llm keyword argument to avoid duplicates
    # when re-patching already-patched files. Top-level llm = LLM(...) is safe
    # because the right side is LLM(...), not llm.
    text = re.sub(r"\bllm\s*=\s*llm\s*,?\s*", "", text)

    # Ensure LLM is imported from crewai
    if "from crewai import" in text and "LLM" not in re.search(r"from crewai import ([^\n]+)", text).group(1):
        text = re.sub(
            r"(from crewai import\s+)([^\n]+)",
            lambda m: f"{m.group(1)}{m.group(2).rstrip()}, LLM",
            text,
            count=1,
        )
    elif "from crewai import LLM" not in text:
        text = "from crewai import LLM\n" + text

    # Add a global llm assignment before the first class/decorator if missing
    has_llm = re.search(r"llm\s*=\s*LLM\(", text) is not None
    if not has_llm and ("class " in text or "@CrewBase" in text):
        llm_block = f'\nllm = LLM(model="ollama/{ollama_model}", base_url="{ollama_url}")\n'
        text = re.sub(
            r"(\n)(class\s+|@[A-Za-z_]+\nclass\s+)",
            llm_block + r"\1\2",
            text,
            count=1,
        )

    # Inject llm=llm into return Agent(...) calls.
    # Captures leading whitespace so the inserted line stays inside the same block.
    text = re.sub(
        r"^(\s*)(return\s+Agent\()\s*",
        r"\1\2\n\1    llm=llm, ",
        text,
        flags=re.MULTILINE,
    )
    return text


def replace_api_backed_tools(text: str) -> str:
    """Replace custom API-key tools with Ollama-backed crewai_tools equivalents.

    Covers the common pattern where older/community examples use
    SearchTools.search_internet (Serper), BrowserTools.scrape_and_summarize_website
    (Browserless), or langchain FileManagementToolkit.
    """
    # FileManagementToolkit -> inline FileReadTool + DirectorySearchTool in tools list
    if "FileManagementToolkit" in text:
        text = re.sub(
            r"from\s+langchain_community\.agent_toolkits\.file_management\.toolkit\s+import\s+FileManagementToolkit\s*\n",
            "from crewai_tools import FileReadTool, DirectorySearchTool, WebsiteSearchTool, ScrapeWebsiteTool\n",
            text,
        )
        text = re.sub(
            r"\s*toolkit\s*=\s*FileManagementToolkit\([^)]*\)",
            "",
            text,
            flags=re.DOTALL,
        )
        text = re.sub(
            r"]\s*\+\s*self\.toolkit\.get_tools\(\)",
            ", FileReadTool(), DirectorySearchTool(config=DEFAULT_RAG_CONFIG)]",
            text,
        )

    # Custom search/browser method references -> crewai_tools instances
    if "SearchTools.search_internet" in text or "BrowserTools.scrape_and_summarize_website" in text:
        if "from crewai_tools import" in text:
            text = re.sub(
                r"(from crewai_tools import\s+)([^\n]+)",
                lambda m: f"{m.group(1)}{m.group(2).rstrip()}, WebsiteSearchTool, ScrapeWebsiteTool",
                text,
                count=1,
            )
        else:
            text = "from crewai_tools import WebsiteSearchTool, ScrapeWebsiteTool\n" + text
        text = text.replace("SearchTools.search_internet", "WebsiteSearchTool(config=DEFAULT_RAG_CONFIG)")
        text = text.replace("BrowserTools.scrape_and_summarize_website", "ScrapeWebsiteTool(config=DEFAULT_RAG_CONFIG)")

    # Deduplicate from crewai_tools import lines created by multiple replacements
    def dedup_crewai_tools(m: re.Match) -> str:
        prefix = m.group(1)
        names = [n.strip() for n in m.group(2).split(",")]
        seen: set[str] = set()
        unique = [n for n in names if n and n not in seen and not seen.add(n)]
        return f"{prefix}{', '.join(unique)}"

    text = re.sub(r"(from\s+crewai_tools\s+import\s+)([^\n]+)", dedup_crewai_tools, text)

    return text


def fix_sec_tools(text: str) -> str:
    """Add DEFAULT_RAG_CONFIG and default config kwarg to custom SEC tools."""
    if "DEFAULT_RAG_CONFIG = {" not in text:
        config_block = """DEFAULT_RAG_CONFIG = {
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
        # Prepend before a class definition at the top of the file
        text = config_block + text

    text = re.sub(
        r"def\s+__init__\(self,\s*stock_name:\s*Optional\[str\]\s*=\s*None,\s*\*\*kwargs\):",
        'def __init__(self, stock_name: Optional[str] = None, **kwargs):\n        kwargs.setdefault("config", DEFAULT_RAG_CONFIG)',
        text,
    )
    return text


def patch_file(path: Path, package_name: str, src_layout: bool, ollama_url: str, ollama_model: str) -> None:
    text = path.read_text()
    original = text

    text = fix_base_tool_imports(text)
    text = fix_langchain_llm(text, ollama_url, ollama_model)
    text = fix_project_imports(text, package_name, src_layout)
    text = fix_pydantic_v1(text)
    text = remove_embedchain(text)
    text = replace_api_backed_tools(text)

    if path.name == "crew.py" or "_agents.py" in path.name:
        text = add_default_rag_config(text, ollama_url, ollama_model)
        text = inject_llm_into_agents(text, ollama_url, ollama_model)

    if "sec" in path.name.lower() and "tools" in str(path):
        text = fix_sec_tools(text)

    # Ensure any hardcoded Ollama URLs point to the correct host
    text = text.replace("http://ollama:11434", ollama_url)

    # Older examples pass verbose=2 (int) to Crew/Agent, but Pydantic expects bool
    text = re.sub(r"\bverbose\s*=\s*2\b", "verbose=True", text)

    if text != original:
        path.write_text(text)
        print(f"Patched {path}")


def patch_pyproject(project_dir: Path) -> None:
    """Bump crewai/crewai-tools constraints and widen python version so uv resolves compatible deps."""
    pyproject = project_dir / "pyproject.toml"
    if not pyproject.exists():
        return

    text = pyproject.read_text()
    original = text

    # Widen upper python bound from <3.12 to <3.13 so newer crewai can be selected
    text = re.sub(
        r'requires-python\s*=\s*"([^"]*)<3\.12([^"]*)"',
        r'requires-python = "\1<3.13\2"',
        text,
    )

    # Bump old crewai 0.x pins to >=1.6.1 (including extras like crewai[tools])
    text = re.sub(
        r'"crewai(?:\[[^\]]+\])?>=0\.[^"]+"',
        '"crewai[tools]>=1.6.0"',
        text,
    )

    # crewai>=1.6.0 requires python-dotenv>=1.1.1; bump exact 1.0.x pins
    text = re.sub(
        r'"python-dotenv==1\.0\.\d+"',
        '"python-dotenv>=1.1.1"',
        text,
    )

    # Bump or add crewai-tools
    if re.search(r'"crewai-tools>=', text):
        text = re.sub(
            r'"crewai-tools>=0\.[^"]+"',
            '"crewai-tools>=1.6.0"',
            text,
        )
    elif '"crewai' in text and '[tools]' not in text:
        text = re.sub(
            r'("crewai(?:\[[^\]]+\])?>=1\.6\.0",?\n)',
            r'\1    "crewai-tools>=1.6.0",\n',
            text,
        )

    # Ollama-backed tools need the ollama python client and litellm
    if '"ollama"' not in text:
        text = re.sub(
            r'("crewai(?:\[[^\]]+\])?>=1\.6\.0",?\n|"crewai-tools>=1\.6\.0",?\n)',
            r'\1    "ollama>=0.6.0",\n',
            text,
        )
    if '"litellm"' not in text:
        text = re.sub(
            r'("ollama>=0\.6\.0",?\n)',
            r'\1    "litellm>=1.74.3",\n',
            text,
        )

    # Remove PyPI dependencies whose names shadow local directories (e.g. tools>=0.1.9 when a local tools/ exists)
    for dep_match in re.finditer(r'^(\s*)"([a-zA-Z0-9_-]+)(?:\[[^\]]*\])?(?:[>=~!]=|==|~=|!=|<|>).*$', text, flags=re.MULTILINE):
        dep_name = dep_match.group(2)
        if (project_dir / dep_name).is_dir() and dep_name not in ("src", "tests", "docs"):
            text = text[:dep_match.start()] + text[dep_match.end():]

    if text != original:
        pyproject.write_text(text)
        print(f"Patched {pyproject}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Patch a CrewAI example project to run with Ollama")
    parser.add_argument("project_dir", type=Path, help="Path to the example project")
    parser.add_argument("--ollama-url", default="http://ollama:11434", help="Ollama base URL")
    parser.add_argument("--ollama-model", default="qwen3.5:9b", help="Ollama chat model")
    args = parser.parse_args()

    project_dir = args.project_dir.resolve()
    package_name = detect_package_name(project_dir)
    src_layout = is_src_layout(project_dir)

    print(f"Project: {project_dir}")
    print(f"Package: {package_name}, src_layout={src_layout}")

    patch_pyproject(project_dir)
    create_package_init(project_dir, package_name, src_layout)

    for py_file in get_python_files(project_dir):
        patch_file(py_file, package_name, src_layout, args.ollama_url, args.ollama_model)

    return 0


if __name__ == "__main__":
    sys.exit(main())
