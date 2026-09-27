#!/usr/bin/env bash
cd "$(dirname "$0")"
PY=../../.venv/bin/python
$PY bench.py run gpt-5.6-luna low v2 10 --evidence --fieldset core
$PY bench.py run gpt-6-luna low v2 10 --evidence --fieldset core
$PY bench.py run gpt-5.6-luna low v2 10 --evidence --sparse --fieldset core
$PY bench.py run gpt-5.6-luna low v2 10 --sparse --fieldset core
$PY bench.py run gpt-6-luna low v2 10 --sparse --fieldset core
echo SCREEN2 DONE
