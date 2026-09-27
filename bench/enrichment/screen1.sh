#!/usr/bin/env bash
cd "$(dirname "$0")"
PY=../../.venv/bin/python
for cfg in "gpt-5.6-luna low" "gpt-6-luna low" "gpt-6-luna medium" "gpt-5.6-terra low" "gpt-5.5 low" "gpt-6-sol low"; do
  $PY bench.py run $cfg full 10 --evidence
done
echo SCREEN1 DONE
