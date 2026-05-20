#!/usr/bin/env bash
set -euo pipefail

python -m coverage erase
python -m coverage run -m pytest -q
python -m coverage report -m
python -m coverage report -m --include="src/tdx_stocks/cli.py,src/tdx_stocks/commands/common.py,src/tdx_stocks/commands/doctor.py,src/tdx_stocks/commands/help.py,src/tdx_stocks/commands/init.py,src/tdx_stocks/commands/output.py,src/tdx_stocks/commands/query.py,src/tdx_stocks/commands/report.py,src/tdx_stocks/commands/run.py,src/tdx_stocks/commands/status.py,src/tdx_stocks/commands/sync.py,src/tdx_stocks/commands/ui.py"
