import json
import subprocess

import pytest

from qayem import ai

SCHEMA = {"type": "object", "properties": {"ready": {"type": "boolean"}},
          "required": ["ready"], "additionalProperties": False}


def events(answer='{"ready":true}', **changes):
    message = {"role": "assistant", "provider": ai.PROVIDER, "model": ai.MODEL,
               "stopReason": "stop", "content": [{"type": "text", "text": answer}]} | changes
    return "\n".join(json.dumps(e) for e in [
        {"type": "message_end", "message": message}, {"type": "agent_end"}])


def test_final_answer_and_json_fence():
    assert ai._answer(events(), SCHEMA, ai.PROVIDER, ai.MODEL) == {"ready": True}
    assert ai._answer(events('```json\n{"ready":true}\n```'), SCHEMA, ai.PROVIDER, ai.MODEL) == {"ready": True}


@pytest.mark.parametrize("output,error", [
    (events(model="another-model"), "unexpected provider or model"),
    (events(provider="another-provider"), "unexpected provider or model"),
    (events(stopReason="length"), "did not complete"),
    (events(stopReason="error", errorMessage="secret-key"), "did not complete"),
    (events('{"ready":"true"}'), "expected schema"),
    (events('{"ready":true,"extra":1}'), "expected schema"),
    (events('{"ready":'), "valid JSON"),
    (events(content=[{"type": "toolCall", "name": "bash"}]), "use a tool"),
    ('{"type":"agent_end"}', "did not finish"),
    (events().splitlines()[0], "did not finish"),
    ('not an event', "invalid JSON event"),
    ('{"type":"tool_execution_start"}\n' + events(), "use a tool"),
])
def test_invalid_or_incomplete_model_output_is_never_accepted(output, error):
    with pytest.raises(RuntimeError, match=error) as failure:
        ai._answer(output, SCHEMA, ai.PROVIDER, ai.MODEL)
    assert "secret-key" not in str(failure.value)


def test_timeout_retry_keeps_the_same_provider_and_prompt(monkeypatch, tmp_path):
    instructions = tmp_path / "spec.md"
    instructions.write_text("Extract only stated facts.")
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        if len(calls) == 1:
            raise subprocess.TimeoutExpired(command, kwargs["timeout"])
        return subprocess.CompletedProcess(command, 0, events(), "")

    monkeypatch.setattr(ai.subprocess, "run", run)
    monkeypatch.setattr(ai.time, "sleep", lambda _: None)
    assert ai.run_pi("listing", SCHEMA, instructions, timeout=30) == {"ready": True}
    assert len(calls) == 2 and calls[0] == calls[1]
    assert calls[0][1]["timeout"] == 30


def test_nonzero_exit_does_not_expose_provider_stderr(monkeypatch, tmp_path):
    instructions = tmp_path / "spec.md"
    instructions.write_text("Extract facts.")
    monkeypatch.setattr(ai.subprocess, "run", lambda command, **kwargs:
                        subprocess.CompletedProcess(command, 1, "", "secret-key"))
    with pytest.raises(RuntimeError, match="Pi exited with status 1") as failure:
        ai.run_pi("listing", SCHEMA, instructions)
    assert "secret-key" not in str(failure.value)
