#!/usr/bin/env bash
cd "$(dirname "$0")"
until grep -q "LUNA6 DONE" luna6.log 2>/dev/null; do sleep 20; done
BENCH_SET=test ../../.venv/bin/python bench.py run gpt-6-luna high v2 5 --evidence --sparse --fieldset core
echo FINAL_LUNA DONE
