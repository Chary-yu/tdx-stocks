# Strategy Examples

Run the strategy registry:

```bash
tdx-stocks strategy list
```

Run the baseline preset:

```bash
tdx-stocks strategy run trend-strength --limit 20
```

Run a breakout-oriented preset:

```bash
tdx-stocks strategy run low-vol-breakout --market sh --limit 10
```

Write JSON output to a file:

```bash
tdx-stocks strategy run ma-pullback --json --to reports/ma-pullback.json
```

Explain a single symbol:

```bash
tdx-stocks strategy run relative-strength --explain-symbol 600000.SH
```

