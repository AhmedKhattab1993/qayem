"""Structured extraction with the Claude CLI: one headless, tool-less `claude -p` call per document batch.

Owner rule (2026-11-25): figures are never pulled out of pages, sheets or articles with regular
expressions; they are read by Claude Opus 5.5 at medium effort as a step of the run itself. Each call
runs in an empty folder with no tools, no MCP servers, no settings, skills or saved session, and its
answer must match the given JSON Schema. Callers then check every figure against the source text
(`quoted`, `number_in`) before it is kept.

Authentication: the operator's signed-in CLI on the Mac, or `CLAUDE_CODE_OAUTH_TOKEN` (from
`claude setup-token`) in the cloud container. Override the binary with `QAYEM_CLAUDE`.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile

from bs4 import BeautifulSoup
from jsonschema import Draft202012Validator, ValidationError

MODEL = "claude-opus-5-5"
EFFORT = "medium"
TIMEOUT = 600
BUDGET_USD = "3"  # a ceiling per call, far above a normal extraction (about 0.05 USD)
MAX_CHARS = 120_000


class ClaudeUnavailable(RuntimeError):
    """The CLI is missing or not signed in: extraction steps are skipped, structured ones still run."""


def binary() -> str:
    found = shutil.which(os.environ.get("QAYEM_CLAUDE", "claude"))
    if not found:
        raise ClaudeUnavailable("the Claude CLI is not installed")
    return found


def command(schema: dict, instructions: str) -> list[str]:
    return [binary(), "-p", "--model", MODEL, "--effort", EFFORT, "--tools", "", "--strict-mcp-config",
            "--no-session-persistence", "--disable-slash-commands", "--setting-sources", "",
            "--max-budget-usd", BUDGET_USD, "--output-format", "json",
            "--system-prompt", instructions.strip() + "\n\nAnswer only through the structured output. "
            "Use only what the text states; never estimate, compute or add knowledge of your own.",
            "--json-schema", json.dumps(schema, ensure_ascii=False, separators=(",", ":"))]


def answer(stdout: str, schema: dict) -> dict:
    """The structured output of one `--output-format json` result, validated against `schema`."""
    try:
        result = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Claude returned no JSON result") from exc
    if not isinstance(result, dict) or result.get("type") != "result":
        raise RuntimeError("Claude returned an unexpected result")
    if result.get("is_error") and "login" in str(result.get("result") or "").casefold():
        raise ClaudeUnavailable("the Claude CLI is not signed in (set CLAUDE_CODE_OAUTH_TOKEN)")
    if result.get("is_error") or result.get("subtype") != "success":
        # Never copy the CLI's error text: it can include account or request details.
        raise RuntimeError(f"Claude did not finish ({result.get('subtype') or 'error'})")
    if MODEL not in (result.get("modelUsage") or {}):
        raise RuntimeError("Claude answered with an unexpected model")
    output = result.get("structured_output")
    if output is None:
        raise RuntimeError("Claude returned no structured output")
    try:
        Draft202012Validator(schema).validate(output)
    except ValidationError as exc:
        raise RuntimeError("Claude's answer did not match the expected schema") from exc
    return output


def extract(text: str, schema: dict, instructions: str, *, timeout: int = TIMEOUT) -> dict:
    """Send `text` (truncated to MAX_CHARS) for structured extraction; raise on any failure."""
    with tempfile.TemporaryDirectory(prefix="qayem-claude-") as folder:
        try:
            result = subprocess.run(command(schema, instructions), input=text[:MAX_CHARS], cwd=folder, text=True,
                                    encoding="utf-8", capture_output=True, timeout=timeout, check=False)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"Claude timed out after {timeout}s") from exc
        except OSError as exc:
            raise ClaudeUnavailable(f"the Claude CLI could not start ({type(exc).__name__})") from exc
    if result.returncode and not result.stdout.strip():
        raise ClaudeUnavailable(f"the Claude CLI exited with status {result.returncode} (not signed in?)")
    return answer(result.stdout, schema)


# --- checking an extraction against its source -------------------------------------------------

_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹٫٬", "01234567890123456789.,")


def page_text(html: str) -> str:
    """The visible words of an HTML page or fragment, whitespace collapsed."""
    soup = BeautifulSoup(html or "", "lxml")
    for tag in soup(["script", "style", "noscript", "svg", "template"]):
        tag.decompose()
    return " ".join(soup.get_text(" ", strip=True).split())


def _plain(text: str) -> str:
    return " ".join((text or "").translate(_DIGITS).casefold().split())


def quoted(quote: str, text: str) -> bool:
    """The quote appears in the source text (case, spacing and Arabic-Indic digits ignored)."""
    quote = _plain(quote)
    return len(quote) >= 3 and quote in _plain(text)


def numbers(text: str) -> list[float]:
    """Every number written in `text`: «12,361.5», «٥٥٢٠», «8.5%» (thousands separators dropped)."""
    found, token = [], ""
    for char in (text or "").translate(_DIGITS) + " ":
        if char.isdigit() or (char in ".," and token and token[-1].isdigit()):
            token += char
            continue
        if token:
            cleaned = token.rstrip(".,").replace(",", "")
            if cleaned.count(".") <= 1:
                try:
                    found.append(float(cleaned))
                except ValueError:
                    pass
            token = ""
    return found


def number_in(value: float, text: str) -> bool:
    """`value` is written in `text` as given (12361.5), rounded to two decimals, or as a whole number."""
    for written in numbers(text):
        if abs(written - value) <= max(0.005, abs(value) * 1e-6):
            return True
    return False


def checked(figure: dict, text: str) -> bool:
    """A figure counts only when its quote is in the source and its number is in the quote."""
    quote = figure.get("quote") or ""
    return quoted(quote, text) and number_in(float(figure["value"]), quote)

