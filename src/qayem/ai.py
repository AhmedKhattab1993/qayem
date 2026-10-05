"""Isolated Pi calls to the locally configured GLM provider, with strict JSON validation."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import time

from jsonschema import Draft202012Validator, ValidationError

PROVIDER = "zai-coding-cn"
MODEL = "glm-5.3-flash"
REASONING_EFFORT = "low"
TIMEOUT_ATTEMPTS = 2


def _answer(stdout: str, schema: dict, provider: str, model: str) -> dict:
    final = None
    ended = False
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Pi emitted an invalid JSON event") from exc
        if not isinstance(event, dict):
            raise RuntimeError("Pi emitted an invalid JSON event")
        if not isinstance(event.get("type", ""), str):
            raise RuntimeError("Pi emitted an invalid JSON event")
        if event.get("type", "").startswith("tool_execution"):
            raise RuntimeError("Pi attempted to use a tool during extraction")
        if event.get("type") == "message_end" and not isinstance(event.get("message"), dict):
            raise RuntimeError("Pi emitted an invalid message")
        if event.get("type") == "message_end" and event["message"].get("role") == "assistant":
            final = event["message"]
        if event.get("type") == "agent_end":
            ended = True
    if not ended or final is None:
        raise RuntimeError("Pi did not finish its response")
    if final.get("provider") != provider or final.get("model") != model:
        raise RuntimeError("Pi answered with an unexpected provider or model")
    if final.get("stopReason") != "stop":
        # Never copy provider error messages: they can include request details or credentials.
        raise RuntimeError("Pi response did not complete")
    content = final.get("content", [])
    if not isinstance(content, list) or any(not isinstance(part, dict) for part in content):
        raise RuntimeError("Pi emitted invalid content")
    if any(part.get("type") == "text" and not isinstance(part.get("text"), str) for part in content):
        raise RuntimeError("Pi emitted invalid content")
    if any(part.get("type") == "toolCall" for part in content):
        raise RuntimeError("Pi attempted to use a tool during extraction")
    answer = "".join(part.get("text", "") for part in content if part.get("type") == "text").strip()
    if answer.startswith("```json\n") and answer.endswith("\n```"):
        answer = answer[8:-4].strip()
    try:
        parsed = json.loads(answer)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Pi response was not valid JSON") from exc
    try:
        Draft202012Validator(schema).validate(parsed)
    except ValidationError as exc:
        raise RuntimeError("Pi response did not match the expected schema") from exc
    return parsed


def run_pi(prompt: str, schema: dict, instructions: Path, *, model: str = MODEL,
           provider: str = PROVIDER, effort: str = REASONING_EFFORT, timeout: int = 600) -> dict:
    """Use global provider credentials without loading project context, tools, or extensions.

    Each batch gets a new ephemeral session. Only the extraction instructions, schema,
    and listing text are sent. Timeout retries retain the existing pipeline's behavior.
    """
    system = (instructions.read_text(encoding="utf-8")
              + "\n\nReturn exactly one JSON object matching this JSON Schema. No prose or tools.\n"
              + json.dumps(schema, ensure_ascii=False, separators=(",", ":")))
    command = [
        "pi", "--offline", "--print", "--mode", "json", "--no-session", "--no-tools",
        "--no-extensions", "--no-skills", "--no-context-files", "--no-prompt-templates",
        "--provider", provider, "--model", model, "--thinking", effort,
        "--system-prompt", system,
    ]
    with tempfile.TemporaryDirectory(prefix="qayem-pi-") as root:
        for attempt in range(TIMEOUT_ATTEMPTS):
            try:
                result = subprocess.run(command, input=prompt, cwd=root, text=True, encoding="utf-8",
                                        capture_output=True, timeout=timeout, check=False)
                break
            except subprocess.TimeoutExpired as exc:
                if attempt + 1 == TIMEOUT_ATTEMPTS:
                    raise RuntimeError(f"Pi timed out after {timeout}s on {TIMEOUT_ATTEMPTS} attempts") from exc
                time.sleep(5)
            except OSError as exc:
                raise RuntimeError(f"Pi could not start: {exc.strerror or type(exc).__name__}") from exc
    if result.returncode:
        raise RuntimeError(f"Pi exited with status {result.returncode}")
    return _answer(result.stdout, schema, provider, model)
