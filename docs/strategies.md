# Strategies

The strategy metadata model is exposed through the `query` surface for every preset:

- `name`
- `display_name`
- `description`
- `group`
- `style`
- `runner`
- `required_fields`
- `optional_fields`
- `default_params`
- `param_schema`
- `candidate_types`
- `risk_tags`
- `introduced_in`
- `aliases`

Useful commands:

```bash
tdx-stocks query strategies
tdx-stocks query strategies --grouped
tdx-stocks query strategy trend-strength --json
tdx-stocks query strategy trend-strength --symbol 000001 --explain
```

`query strategies` shows the high-level catalogue.
`query strategies --grouped` shows how presets are distributed by group.
`query strategy` prints the strategy schema and factor requirements.
