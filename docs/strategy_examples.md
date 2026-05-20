# Strategy Examples

Run the strategy registry:

```bash
tdx-stocks query strategies
```

Describe a preset:

```bash
tdx-stocks query strategy trend-strength
```

Explain a single symbol:

```bash
tdx-stocks query strategy trend-strength --symbol 600000.SH --explain
```

Run the baseline preset:

```bash
tdx-stocks run signal --limit 20
```

Run a breakout-oriented preset:

```bash
tdx-stocks run signal --market sh --limit 10
```

Write JSON output to a file:

```bash
tdx-stocks run signal --json --output reports/signal.json
```

The legacy `--to` flag still works, but new examples should use `--output`.
