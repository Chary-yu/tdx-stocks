# Portfolio

Portfolio commands build a target basket from strategy or consensus candidates.

Supported sources:

- `consensus`
- `strategy`
- `report`

Weighting modes:

- `equal`: `1 / N`
- `score`: `score_i / sum(score)`
- `risk-adjusted`: `score_i * (1 - risk_score)` with fallback to score weighting when `risk_score` is missing

Important constraints:

- `max_weight` caps a single position
- `min_weight` removes tiny positions before normalization
- final weights are normalized to approximately `1.0`

Example:

```bash
tdx-stocks portfolio build --from consensus --top 20
tdx-stocks portfolio build --from strategy --strategy trend-strength --top 20 --weighting score
```

The portfolio layer does not connect to a broker and does not place orders.

