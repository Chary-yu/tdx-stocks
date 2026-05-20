#!/usr/bin/env bash
set -euo pipefail

python -m coverage erase
python -m coverage run -m pytest -q
python -m coverage report -m
python -m coverage report -m --include="src/tdx_stocks/cli.py,src/tdx_stocks/commands/*"
