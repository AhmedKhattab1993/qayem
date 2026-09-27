#!/usr/bin/env bash
cd "$(dirname "$0")"
PY=../../.venv/bin/python
until grep -q "SCREEN3 DONE" screen3.log 2>/dev/null; do sleep 20; done
$PY bench.py run gpt-5.6-terra low v2 10 --evidence --sparse --fieldset core
$PY bench.py run gpt-6-sol low v2 10 --evidence --sparse --fieldset core
echo SCREEN4 DONE
