# Strategy Explain

`tdx-stocks query strategy <strategy> --symbol <symbol> --explain` returns a read-only explanation for one symbol.

Main fields:

- `selected`: whether the symbol was selected by the preset
- `total_score`: final score after rule and penalty aggregation
- `not_selected_reason`: why the symbol was rejected, if applicable
- `rule_checks`: rule-by-rule pass/fail checks
- `score_breakdown`: scoring components
- `key_factors`: key factor snapshot used during evaluation
- `risk_tags`: risk flags attached to the symbol
- `missing_fields`: required fields that are not available

Example:

```bash
tdx-stocks query strategy trend-strength --symbol 000001 --explain --json
```

This command is independent from `run --explain-symbol`.
