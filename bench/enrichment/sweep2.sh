#!/usr/bin/env bash
cd "$(dirname "$0")"
PY=../../.venv/bin/python
until grep -q "SWEEP DONE" sweep.log 2>/dev/null && grep -q "SCREEN4 DONE" screen4.log 2>/dev/null; do sleep 20; done
for b in 20 40; do
  $PY bench.py run gpt-6-sol low v2 $b --sparse --fieldset core
  $PY bench.py run gpt-6-sol medium v2 $b --sparse --fieldset core
done
echo SWEEP2 DONE
