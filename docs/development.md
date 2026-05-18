# Development Notes

## Strategy work

The strategy layer is split into:

- `registry.py` for discovery
- `data.py` for factor/date access
- `signals.py` for candidate classification
- `scoring.py` for score breakdowns
- `universe.py` for hard filters and symbol formatting
- `presets/` for user-facing strategy entrypoints

## Adding a preset

1. Add a new module under `src/tdx_stocks/strategies/presets/`.
2. Reuse the shared helpers instead of copying the full trend engine.
3. Register the preset in `registry.py`.
4. Add CLI and unit test coverage.
5. Update `docs/strategy_presets.md` and `docs/cli_help_summary.md`.

## Compatibility rule

Keep `tdx_stocks.strategy` as a compatibility entrypoint until a major version
boundary.

