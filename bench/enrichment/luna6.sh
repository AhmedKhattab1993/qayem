#!/usr/bin/env bash
cd "$(dirname "$0")"
PY=../../.venv/bin/python
$PY bench.py run gpt-6-luna medium v2 10 --evidence --sparse --fieldset core
$PY bench.py run gpt-6-luna high v2 10 --evidence --sparse --fieldset core
$PY bench.py run gpt-6-luna high v2 5 --evidence --sparse --fieldset core
$PY bench.py run gpt-6-luna xhigh v2 10 --evidence --sparse --fieldset core
echo LUNA6 DONE
