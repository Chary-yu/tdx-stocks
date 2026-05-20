# Portfolio

Portfolio commands build a target basket from strategy or consensus candidates.
The current CLI exposes this capability through `run portfolio` presets and the
report/query workflows.

Supported sources:

- `consensus`
- `strategy`
- `report`

`--from report` uses a saved strategy report. In this version it must be used
with `--strategy`, and `--as-of latest` is the supported default form.

Weighting modes:

- `equal`: `1 / N`
- `score`: `score_i / sum(score)`
- `risk-adjusted`: `score_i * (1 - risk_score)` with fallback to score weighting when `risk_score` is missing

Important constraints:

- `max_weight` caps a single position
- `min_weight` removes tiny positions before normalization
- final weights are normalized to approximately `1.0`
- `--output` is the primary file flag, `--to` remains a compatibility alias
- `--output` and `--to` cannot be used together

Example:

```bash
tdx-stocks run portfolio
tdx-stocks run portfolio --json --output reports/portfolio.json
tdx-stocks report strategy trend-strength
```

The portfolio layer does not connect to a broker and does not place orders.
