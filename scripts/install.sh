#!/usr/bin/env bash
set -euo pipefail
cd /workspace/job-tracker2
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock.txt
.venv/bin/python -m pip install --no-deps -e .
.venv/bin/python -m pip check
.venv/bin/python -m pytest -q
.venv/bin/python -m job_tracker.cli init
.venv/bin/python -m job_tracker.cli sync-excel
