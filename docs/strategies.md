# Strategies

`tdx-stocks strategy` now exposes a standard metadata model for every preset:

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
tdx-stocks strategy list
tdx-stocks strategy groups
tdx-stocks strategy describe trend-strength --json
tdx-stocks strategy explain trend-strength 000001 --as-of latest
```

`strategy list` shows the high-level catalogue.
`strategy groups` shows how presets are distributed by group.
`strategy describe` prints the strategy schema and factor requirements.

