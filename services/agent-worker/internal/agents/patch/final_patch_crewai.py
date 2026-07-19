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
    """Ensure the package root has an __init__.py so absolute imports work.

    For flat-layout projects whose directory name contains hyphens, also create a
    sanitized symlink so Python can import the package by the sanitized name.
    """
    if src_layout:
        init_file = project_dir / "src" / package_name / "__init__.py"
    else:
        init_file = project_dir / "__init__.py"
    if not init_file.exists():
        init_file.parent.mkdir(parents=True, exist_ok=True)
        init_file.write_text("")
        print(f"Created {init_file}")

    if not src_layout and project_dir.name != package_name:
        link = project_dir.parent / package_name
        if not link.exists():
            link.symlink_to(project_dir.name, target_is_directory=True)
            print(f"Created symlink {link} -> {project_dir.name}")


def is_src_layout(project_dir: Path) -> bool:
    return (project_dir / "src").is_dir()


def ensure_import_os(text: str) -> str:
    if re.search(r"^import\s+os\b", text, flags=re.MULTILINE) is None:
        text = "import os\n" + text
    return text


def make_llm_instantiation(ollama_url: str, ollama_model: str, var_name: str = "llm") -> str:
    """Return an env-aware LLM(...) assignment string.

    Defaults to Ollama, but MODEL/API_KEY/OPENAI_API_KEY/OPENAI_API_BASE_URL env vars
    let the user switch to another provider without code changes.
    """
    return f'''{var_name} = LLM(
    model=os.environ.get("MODEL", "ollama/{ollama_model}"),
    base_url=os.environ.get("OPENAI_API_BASE_URL", os.environ.get("OLLAMA_HOST", "{ollama_url}")),
    api_key=(os.environ.get("API_KEY") or os.environ.get("OPENAI_API_KEY")) or None,
)'''


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
    # while preserving the original variable name. We scan for balanced parens
    # and respect string literals so nested calls (e.g. os.environ.get(...)) work.
    def replace_llm_call(text: str, cls: str) -> str:
        pattern = re.compile(rf"([A-Za-z_][A-Za-z0-9_]*)\s*=\s*{cls}\s*\(")
        parts: list[str] = []
        i = 0
        for m in pattern.finditer(text):
            parts.append(text[i:m.start()])
            var = m.group(1)
            j = m.end()  # position right after the opening '('
            depth = 1
            in_quote: str | None = None
            escaped = False
            while j < len(text) and depth > 0:
                ch = text[j]
                if in_quote:
                    if escaped:
                        escaped = False
                    elif ch == "\\":
                        escaped = True
                    elif ch == in_quote:
                        in_quote = None
                else:
                    if ch in ('"', "'"):
                        in_quote = ch
                    elif ch == "(":
                        depth += 1
                    elif ch == ")":
                        depth -= 1
                j += 1
            parts.append(make_llm_instantiation(ollama_url, ollama_model, var_name=var))
            i = j
        parts.append(text[i:])
        return "".join(parts)

    for cls in ("ChatOpenAI", "OpenAI", "Ollama"):
        text = replace_llm_call(text, cls)

    # If we introduced any LLM(...) calls, make sure LLM is imported.
    if re.search(r"\bLLM\s*\(", text) and not re.search(
        r"from\s+crewai\s+import\s+[^#\n]*\bLLM\b", text
    ):
        new_text, n = re.subn(
            r"(from\s+crewai\s+import\s+)([^#\n]+)(?=\n)",
            r"\1\2, LLM",
            text,
            count=1,
        )
        if n:
            text = new_text
        else:
            text = insert_after_imports(text, "from crewai import LLM\n")

    # Drop unused langchain.agents imports (e.g. load_tools).
    text = re.sub(
        r"from\s+langchain\.agents\s+import\s+[^\n]+\n",
        "",
        text,
    )

    # DuckDuckGoSearchRun is often just a placeholder in templates and the
    # crewai-tools package no longer ships DuckDuckGoSearchTool, so remove it.
    text = re.sub(
        r"from\s+langchain\.tools\s+import\s+DuckDuckGoSearchRun\s*\n",
        "",
        text,
    )
    text = re.sub(
        r"\bsearch_tool\s*=\s*DuckDuckGoSearchRun\s*\(\s*\)\s*\n?",
        "",
        text,
    )

    return text


def fix_project_imports(text: str, package_name: str, src_layout: bool, project_dir: Path) -> str:
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

    # Rewrite any bare 'from <local_module> import' that is actually a .py file in this project.
    if src_layout:
        module_dir = project_dir / "src" / package_name
    else:
        module_dir = project_dir
    local_modules = {
        p.stem
        for p in module_dir.glob("*.py")
        if p.stem not in ("__init__", "main", "setup")
    }
    for mod in sorted(local_modules):
        text = re.sub(
            rf"from\s+{re.escape(mod)}\s+import\s+",
            f"from {package_name}.{mod} import ",
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
"""
        text = insert_after_imports(text, config_block)

    if re.search(r"\bllm\s*=\s*LLM\(", text) is None:
        text = insert_after_imports(text, "\n" + make_llm_instantiation(ollama_url, ollama_model) + "\n")

    text = ensure_import_os(text)

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
    elif not re.search(r"from\s+crewai\s+import\s+[^#\n]*\bLLM\b", text):
        text = "from crewai import LLM\n" + text

    # Add a global llm assignment before the first class/decorator/Agent if missing
    has_llm = re.search(r"llm\s*=\s*LLM\(", text) is not None
    if not has_llm and ("class " in text or "@CrewBase" in text or "Agent(" in text):
        llm_block = "\n" + make_llm_instantiation(ollama_url, ollama_model) + "\n"
        text = re.sub(
            r"(\n)(class\s+|@[A-Za-z_]+\nclass\s+|[^\n]*?Agent\s*\()",
            llm_block + r"\1\2",
            text,
            count=1,
        )

    text = ensure_import_os(text)

    # Inject llm=llm into every Agent(...) call that does not already specify llm.
    def _inject_llm(m: re.Match) -> str:
        prefix = m.group(1)  # includes "Agent" and any whitespace before "("
        paren = m.end()  # position right after '('
        depth = 1
        in_quote: str | None = None
        escaped = False
        j = paren
        while j < len(text) and depth > 0:
            ch = text[j]
            if in_quote:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == in_quote:
                    in_quote = None
            else:
                if ch in ('"', "'"):
                    in_quote = ch
                elif ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
            j += 1
        call = text[m.start() : j]
        if re.search(r"\bllm\s*=", call):
            return prefix
        return f"{prefix}llm=llm, "

    text = re.sub(r"(Agent\s*\()", _inject_llm, text)

    return text


def replace_api_backed_tools(text: str) -> str:
    """Replace langchain FileManagementToolkit with crewai_tools equivalents.

    We do NOT replace SearchTools.search_internet (Serper) or
    BrowserTools.scrape_and_summarize_website (Browserless); those are patched
    separately to read keys from environment variables.
    """
    # FileManagementToolkit -> inline FileReadTool + DirectorySearchTool in tools list
    if "FileManagementToolkit" in text:
        text = re.sub(
            r"from\s+langchain_community\.agent_toolkits\.file_management\.toolkit\s+import\s+FileManagementToolkit\s*\n",
            "from crewai_tools import FileReadTool, DirectorySearchTool\n",
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

    # Deduplicate from crewai_tools import lines created by multiple replacements
    def dedup_crewai_tools(m: re.Match) -> str:
        prefix = m.group(1)
        names = [n.strip() for n in m.group(2).split(",")]
        seen: set[str] = set()
        unique = [n for n in names if n and n not in seen and not seen.add(n)]
        return f"{prefix}{', '.join(unique)}"

    text = re.sub(r"(from\s+crewai_tools\s+import\s+)([^\n]+)", dedup_crewai_tools, text)

    return text




def fix_search_tools(text: str) -> str:
    """Make Serper search tools read the API key safely and skip gracefully on errors."""
    if "SERPER_API_KEY" not in text:
        return text

    # Ensure bracket access is normalized to .get() first.
    text = fix_env_api_keys(text)

    # 1. Promote the inline API-key lookup into a variable and guard missing keys.
    def headers_repl(m: re.Match) -> str:
        indent = m.group(1)
        before = m.group(2)
        after = m.group(3)
        return (
            f"{indent}serper_api_key = os.environ.get('SERPER_API_KEY', '')\n"
            f'{indent}if not serper_api_key:\n'
            f'{indent}    return "SERPER_API_KEY not set; skipping search."\n'
            f"{indent}headers = {{{before}'X-API-KEY': serper_api_key{after}}}"
        )

    text = re.sub(
        r"^(\s+)headers\s*=\s*\{([^}]*?)'X-API-KEY':\s*os\.environ\.get\('SERPER_API_KEY',\s*''\)([^}]*?)\}",
        headers_repl,
        text,
        flags=re.MULTILINE | re.DOTALL,
    )

    # 2. Replace response.json() calls with a placeholder so the new try block is not touched.
    text = text.replace("response.json()", "__CREWAI_JSON__")

    # 3. Wrap the HTTP request in a try/except and assign JSON to data.
    def request_repl(m: re.Match) -> str:
        indent = m.group(1)
        call = m.group(2)
        return (
            f"{indent}try:\n"
            f"{indent}    response = {call}\n"
            f"{indent}    response.raise_for_status()\n"
            f"{indent}    data = response.json()\n"
            f"{indent}except Exception as e:\n"
            f'{indent}    return f"Search request failed: {{e}}"'
        )

    text = re.sub(
        r"^(\s+)response\s*=\s*(requests\.request\s*\([^)]*\))",
        request_repl,
        text,
        flags=re.MULTILINE | re.DOTALL,
    )

    # 4. Restore the remaining response.json() references to use the data variable.
    text = text.replace("__CREWAI_JSON__", "data")

    # 5. Harden the 'organic' key checks.
    text = re.sub(
        r"if\s+(['\"])organic\1\s+not\s+in\s+data\s*:",
        "if not isinstance(data, dict) or 'organic' not in data:",
        text,
        flags=re.MULTILINE,
    )

    def results_repl(m: re.Match) -> str:
        indent = m.group(1)
        return (
            f"{indent}if not isinstance(data, dict) or 'organic' not in data:\n"
            f'{indent}    return "Sorry, I couldn\'t find anything about that, there could be an error with your Serper API key."\n'
            f"{indent}results = data['organic']"
        )

    text = re.sub(
        r"^(\s+)results\s*=\s*data\['organic'\]",
        results_repl,
        text,
        flags=re.MULTILINE,
    )

    # 6. Some examples mistakenly use `next` instead of `continue` in except KeyError blocks.
    text = re.sub(
        r"(except\s+KeyError\s*:\s*\n\s+)next\b",
        r"\1continue",
        text,
        flags=re.MULTILINE,
    )

    return text


def fix_browser_tools(text: str, ollama_url: str, ollama_model: str) -> str:
    """Make Browserless-backed scrapers env-safe and skip gracefully on missing keys."""
    if "BROWSERLESS_API_KEY" not in text:
        return text

    text = fix_env_api_keys(text)

    # 1. Promote inline API-key lookup into a variable and guard missing keys.
    def url_repl(m: re.Match) -> str:
        indent = m.group(1)
        return (
            f"{indent}browserless_api_key = os.environ.get('BROWSERLESS_API_KEY', '')\n"
            f'{indent}if not browserless_api_key:\n'
            f'{indent}    return "BROWSERLESS_API_KEY not set; skipping website scrape."\n'
            f'{indent}url = f"https://chrome.browserless.io/content?token={{browserless_api_key}}"'
        )

    text = re.sub(
        r"^(\s+)url\s*=\s*f\"https://chrome\.browserless\.io/content\?token=\{os\.environ\.get\('BROWSERLESS_API_KEY',\s*''\)\}\"",
        url_repl,
        text,
        flags=re.MULTILINE,
    )

    # 2. Wrap the HTTP request in a try/except with raise_for_status().
    def request_repl(m: re.Match) -> str:
        indent = m.group(1)
        call = m.group(2)
        return (
            f"{indent}try:\n"
            f"{indent}    response = {call}\n"
            f"{indent}    response.raise_for_status()\n"
            f"{indent}except Exception as e:\n"
            f'{indent}    return f"Scrape request failed: {{e}}"'
        )

    text = re.sub(
        r"^(\s+)response\s*=\s*(requests\.request\s*\([^)]*\))",
        request_repl,
        text,
        flags=re.MULTILINE | re.DOTALL,
    )

    # 3. Wrap partition_html / content extraction in a try/except.
    def partition_repl(m: re.Match) -> str:
        indent = m.group(1)
        return (
            f"{indent}try:\n"
            f"{indent}    elements = partition_html(text=response.text)\n"
            f'{indent}    content = "\\n\\n".join([str(el) for el in elements])\n'
            f"{indent}except Exception as e:\n"
            f'{indent}    return f"Could not parse page content: {{e}}"'
        )

    text = re.sub(
        r'^(\s+)elements\s*=\s*partition_html\(text=response\.text\)\s*\n\1content\s*=\s*"\\n\\n"\.join\(\[str\(el\)\s+for\s+el\s+in\s+elements\]\)',
        partition_repl,
        text,
        flags=re.MULTILINE,
    )

    # 4. Guard empty content before chunking.
    def chunk_guard_repl(m: re.Match) -> str:
        indent = m.group(1)
        line = m.group(2)
        return (
            f"{indent}if not content or not content.strip():\n"
            f'{indent}    return "No usable content found on the page."\n'
            f"{indent}{line}"
        )

    text = re.sub(
        r"^(\s+)(content\s*=\s*\[content\[i:i\s*\+\s*8000\]\s+for\s+i\s+in\s+range\(0,\s*len\(content\),\s*8000\)\])",
        chunk_guard_repl,
        text,
        flags=re.MULTILINE,
    )

    return text


def fix_sec_tools(text: str) -> str:
    """Make SEC tools use env API key and skip gracefully when it is missing."""
    if "sec_api" not in text:
        return text

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

    # RagTool._run does not accept stock_name, so drop it before delegating
    text = re.sub(
        r"^(\s+)return\s+super\(\)\._run\(query=search_query,\s*\*\*kwargs\)$",
        r"\1kwargs.pop('stock_name', None)\n\1return super()._run(query=search_query, **kwargs)",
        text,
        flags=re.MULTILINE,
    )

    # Avoid KeyError when SEC_API_API_KEY is not set; guard before the network call
    def repl_sec_api(m: re.Match) -> str:
        indent = m.group(1)
        return (
            f"{indent}sec_api_key = os.environ.get('SEC_API_API_KEY', '')\n"
            f"{indent}if not sec_api_key:\n"
            f"{indent}    print('SEC_API_API_KEY not set; skipping SEC lookup.')\n"
            f"{indent}    return None\n"
            f"{indent}queryApi = QueryApi(api_key=sec_api_key)"
        )

    text = re.sub(
        r"^(\s*)queryApi\s*=\s*QueryApi\(api_key=os\.environ(?:\.get\('SEC_API_API_KEY',\s*''\)|\['SEC_API_API_KEY'\])\)",
        repl_sec_api,
        text,
        flags=re.MULTILINE,
    )

    # Fallback: if the replacement above did not fire because the line uses direct bracket access
    text = text.replace("os.environ['SEC_API_API_KEY']", "os.environ.get('SEC_API_API_KEY', '')")

    return text


def fix_exa_tools(text: str) -> str:
    """Make ExaSearchTool skip gracefully when the EXA_API_KEY is missing."""
    if "Exa(" not in text:
        return text

    def _exa_repl(m: re.Match) -> str:
        indent = m.group(1)
        t = "\t"
        return (
            f"{indent}def _exa():\n"
            f"{indent}{t}class _DummyExa:\n"
            f"{indent}{t}{t}def search(self, *args, **kwargs):\n"
            f"{indent}{t}{t}{t}return \"EXA_API_KEY not set; skipping Exa search.\"\n"
            f"{indent}{t}{t}def find_similar(self, *args, **kwargs):\n"
            f"{indent}{t}{t}{t}return \"EXA_API_KEY not set; skipping Exa search.\"\n"
            f"{indent}{t}{t}def get_contents(self, *args, **kwargs):\n"
            f"{indent}{t}{t}{t}return \"EXA_API_KEY not set; skipping Exa search.\"\n"
            f"{indent}{t}api_key = os.environ.get('EXA_API_KEY', '')\n"
            f"{indent}{t}if not api_key:\n"
            f"{indent}{t}{t}return _DummyExa()\n"
            f"{indent}{t}return Exa(api_key=api_key)"
        )

    text = re.sub(
        r"^(\s+)def\s+_exa\(\):\s*\n\s*return\s+Exa\(api_key=os\.environ\.get\('EXA_API_KEY',\s*''\)\)",
        _exa_repl,
        text,
        flags=re.MULTILINE,
    )

    return text


def fix_env_api_keys(text: str) -> str:
    """Replace hard os.environ['KEY'] accesses with .get(..., '') so missing env vars don't crash imports."""
    # Any API key / token / cookie pattern accessed via bracket notation
    text = re.sub(
        r"os\.environ\[(['\"'])([A-Z][A-Z0-9_]*(?:_API_KEY|_KEY|_TOKEN|_COOKIE|_SECRET|_APIKEY))\1\](?!\s*=[^=])",
        r"os.environ.get('\2', '')",
        text,
    )
    return text


def patch_file(path: Path, package_name: str, src_layout: bool, project_dir: Path, ollama_url: str, ollama_model: str) -> None:
    text = path.read_text()
    original = text

    text = fix_base_tool_imports(text)
    text = fix_langchain_llm(text, ollama_url, ollama_model)
    text = fix_project_imports(text, package_name, src_layout, project_dir)
    text = fix_pydantic_v1(text)
    text = remove_embedchain(text)
    text = replace_api_backed_tools(text)

    if path.name == "crew.py" or "_agents.py" in path.name:
        text = add_default_rag_config(text, ollama_url, ollama_model)

    if "Agent(" in text:
        text = inject_llm_into_agents(text, ollama_url, ollama_model)

    if "sec" in path.name.lower() and "tools" in str(path):
        text = fix_sec_tools(text)

    text = fix_env_api_keys(text)

    if "exa_py" in text:
        text = fix_exa_tools(text)

    if "search_tools" in path.name:
        text = fix_search_tools(text)
    if "browser_tools" in path.name:
        text = fix_browser_tools(text, ollama_url, ollama_model)

    # os.environ may now be referenced, ensure os is imported
    if "os.environ" in text:
        text = ensure_import_os(text)

    # Ensure any hardcoded Ollama URLs point to the correct host
    text = text.replace("http://ollama:11434", ollama_url)

    # Older examples call task.execute(), which was renamed to execute_sync() in newer CrewAI
    text = re.sub(r"\.execute\s*\(\s*\)", ".execute_sync()", text)

    # decouple.config calls for uppercase env vars need a default so missing keys don't crash imports
    text = re.sub(
        r"config\((['\"'])([A-Z][A-Z0-9_]*)\1\)",
        r"config('\2', default='')",
        text,
    )

    # Older examples pass verbose=2 (int) to Crew/Agent, but Pydantic expects bool
    text = re.sub(r"\bverbose\s*=\s*2\b", "verbose=True", text)

    if text != original:
        path.write_text(text)
        print(f"Patched {path}")


def patch_pyproject(project_dir: Path) -> None:
    """Bump crewai/crewai-tools constraints, add tool dependencies, and create pyproject.toml if missing."""
    pyproject = project_dir / "pyproject.toml"

    # Collect extra tool dependencies from source imports.
    source = "\n".join(
        p.read_text(encoding="utf-8", errors="ignore")
        for p in get_python_files(project_dir)
    )
    extra_deps: set[str] = set()
    if re.search(r"\bfrom\s+unstructured\b|\bimport\s+unstructured\b", source):
        extra_deps.add("unstructured>=0.16.0")
    if re.search(r"\bfrom\s+sec_api\b|\bimport\s+sec_api\b", source):
        extra_deps.add("sec-api>=1.0.20")
    if re.search(r"\bfrom\s+pymarkdown\b|\bimport\s+pymarkdown\b", source):
        extra_deps.add("pymarkdownlnt>=0.9.15")
    if re.search(r"\bfrom\s+selenium\b|\bimport\s+selenium\b", source):
        extra_deps.add("selenium>=4.21.0")
    if re.search(r"\bfrom\s+exa_py\b|\bimport\s+exa_py\b", source):
        extra_deps.add("exa_py>=1.0.7")
    if re.search(r"\bfrom\s+pyowm\b|\bimport\s+pyowm\b", source):
        extra_deps.add("pyowm==3.3.0")
    if re.search(r"\bimport\s+cv2\b", source):
        extra_deps.add("opencv-python>=4.8.0")
    if re.search(r"\bimport\s+markdown\b", source):
        extra_deps.add("markdown>=3.4.3")
    if re.search(r"\bimport\s+html2text\b", source):
        extra_deps.add("html2text>=2024.2.26")
    if re.search(r"\bfrom\s+decouple\b|\bimport\s+decouple\b", source):
        extra_deps.add("python-decouple>=3.8")
    if re.search(r"\bRagTool\b|\bVectorSearchTool\b", source):
        extra_deps.add("chromadb>=0.5.0")
    if re.search(r"\bfrom\s+linkedin_api\b|\bimport\s+linkedin_api\b", source):
        extra_deps.add("linkedin-api>=2.1.0")

    dep_map: dict[str, str] = {
        "crewai[tools]": "crewai[tools]>=1.6.0",
        "python-dotenv": "python-dotenv>=1.1.1",
        "ollama": "ollama>=0.6.0",
        "litellm": "litellm>=1.74.3",
    }

    def _norm(dep: str) -> str:
        return dep.split("=")[0].split(">")[0].split("<")[0].split("[")[0].strip().lower()

    for d in sorted(extra_deps):
        dep_map.setdefault(_norm(d), d)

    req_file = project_dir / "requirements.txt"
    if req_file.exists():
        for line in req_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            lower = line.lower()
            if lower.startswith("crewai") or lower.startswith("python-dotenv"):
                continue
            if lower.startswith("langchain"):
                continue
            dep_map.setdefault(_norm(line), line)

    deps = list(dep_map.values())

    if not pyproject.exists():
        dep_lines = ",\n    ".join(f'"{d}"' for d in deps)
        pyproject.write_text(
            f'''[project]
name = "{project_dir.name.replace("-", "_")}"
version = "0.1.0"
description = ""
requires-python = ">=3.10,<3.13"
dependencies = [
    {dep_lines}
]
'''
        )
        print(f"Created {pyproject}")
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
        patch_file(py_file, package_name, src_layout, project_dir, args.ollama_url, args.ollama_model)

    return 0


if __name__ == "__main__":
    sys.exit(main())
