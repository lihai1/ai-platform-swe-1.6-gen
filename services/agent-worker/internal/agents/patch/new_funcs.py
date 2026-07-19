import re

def fix_env_api_keys(text: str) -> str:
    """Replace hard os.environ['KEY'] accesses with .get(..., '') so missing env vars don't crash imports."""
    # Any API key / token / cookie pattern accessed via bracket notation
    text = re.sub(
        r"os\.environ\[(['\"'])([A-Z][A-Z0-9_]*(?:_API_KEY|_KEY|_TOKEN|_COOKIE|_SECRET|_APIKEY))\1\](?!\s*=[^=])",
        r"os.environ.get('\2', '')",
        text,
    )
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

