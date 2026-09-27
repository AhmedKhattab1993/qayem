#!/usr/bin/env bash
cd "$(dirname "$0")"
PY=../../.venv/bin/python
for b in 1 5 20 40; do
  $PY bench.py run gpt-5.6-luna low v2 $b --evidence --sparse --fieldset core --workers 6
done
echo SWEEP DONE
