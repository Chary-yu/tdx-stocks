# Strategy Examples

Run the strategy registry:

```bash
tdx-stocks strategy list
```

Describe a preset:

```bash
tdx-stocks strategy describe trend-strength
```

Explain a single symbol:

```bash
tdx-stocks strategy explain trend-strength 600000.SH --as-of latest
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
tdx-stocks strategy run ma-pullback --json --output reports/ma-pullback.json
```

The legacy `--to` flag still works, but new examples should use `--output`.
