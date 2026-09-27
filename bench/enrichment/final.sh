#!/usr/bin/env bash
cd "$(dirname "$0")"
export BENCH_SET=test
PY=../../.venv/bin/python
$PY bench.py run gpt-5.6-luna low v2 10 --evidence --sparse --fieldset core
$PY bench.py run gpt-5.6-luna low v2 10 --evidence --sparse --fieldset core --tag gpt-5.6-luna_low_v2_b10_ev_sp_core_rep2
$PY bench.py run gpt-5.6-terra low v2 10 --evidence --sparse --fieldset core
until grep -q "SWEEP2 DONE" sweep2.log 2>/dev/null; do sleep 20; done
$PY bench.py run gpt-6-sol low v2 20 --sparse --fieldset core
$PY bench.py run gpt-6-sol medium v2 10 --sparse --fieldset core
$PY bench.py run gpt-6-sol low v2 10 --sparse --fieldset core
echo FINAL DONE
