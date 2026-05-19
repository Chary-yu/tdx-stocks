# Run Config

`tdx-stocks run <config.toml>` reads a task-oriented TOML file and dispatches
to the matching runner.

Supported task types:

- `daily`
- `signal`
- `backtest`
- `grid_search`
- `portfolio`
- `rebalance`

Minimum requirements:

- `[task].type` must be present.
- The type must be one of the supported values above.
- Task-specific required sections must exist.
- Paths inside the config are resolved relative to the TOML file location.

Example:

```toml
[task]
type = "backtest"
name = "trend-strength-backtest"

[strategy]
name = "trend-strength"

[backtest]
from_date = "2022-01-01"
to_date = "2024-12-31"
top = 20
hold_days = 5
```

If validation fails, `tdx-stocks run` prints an error with a suggested fix.
