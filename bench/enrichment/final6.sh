#!/usr/bin/env bash
cd "$(dirname "$0")"
export BENCH_SET=test
PY=../../.venv/bin/python
$PY bench.py run gpt-6-sol low v2 40 --sparse --fieldset core
$PY bench.py run gpt-6-sol low v2 20 --sparse --fieldset core
$PY bench.py run gpt-6-sol medium v2 10 --sparse --fieldset core
$PY bench.py run gpt-6-sol low v2 40 --sparse --fieldset core --tag gpt-6-sol_low_v2_b40_sp_core_rep2
echo FINAL6 DONE
