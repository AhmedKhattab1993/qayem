#!/usr/bin/env bash
cd "$(dirname "$0")"
PY=../../.venv/bin/python
until grep -q "SCREEN2 DONE" screen2.log 2>/dev/null; do sleep 20; done
$PY bench.py run gpt-6-sol low v2 10 --evidence --fieldset core
$PY bench.py run gpt-6-sol low v2 10 --sparse --fieldset core
$PY bench.py run gpt-6-sol medium v2 10 --sparse --fieldset core
echo SCREEN3 DONE
