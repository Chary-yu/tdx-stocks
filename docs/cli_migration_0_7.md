# CLI Migration 0.7

This release flattens the CLI surface and retires the old top-level strategy and factor entrypoints.

## New commands

- `tdx-stocks sync`
- `tdx-stocks run daily`
- `tdx-stocks report`
- `tdx-stocks query stock`
- `tdx-stocks query tables`
- `tdx-stocks query factors`
- `tdx-stocks query factor <name>`
- `tdx-stocks query rank <name>`
- `tdx-stocks query strategies`
- `tdx-stocks query strategy <name>`
- `tdx-stocks help <topic>`

## Old to new

| Old | New |
| --- | --- |
| `tdx-stocks data sync` | `tdx-stocks sync` |
| `tdx-stocks query price` | `tdx-stocks query stock` |
| `tdx-stocks query factor list` | `tdx-stocks query factors` |
| `tdx-stocks query factor describe <factor>` | `tdx-stocks query factor <factor>` |
| `tdx-stocks query factor rank <factor>` | `tdx-stocks query rank <factor>` |
| `tdx-stocks strategy list` | `tdx-stocks query strategies` |
| `tdx-stocks strategy groups` | `tdx-stocks query strategies --grouped` |
| `tdx-stocks strategy describe <name>` | `tdx-stocks query strategy <name>` |
| `tdx-stocks strategy explain <name> <symbol>` | `tdx-stocks query strategy <name> --symbol <symbol> --explain` |
| `tdx-stocks strategy run <preset>` | `tdx-stocks run <preset>` |
| `tdx-stocks strategy reports list` | `tdx-stocks report strategy --list` |
| `tdx-stocks strategy reports show <name>` | `tdx-stocks report strategy <name>` |
| `tdx-stocks help-summary` | `tdx-stocks help` |

## Notes

- The retired CLI wiring stays in the codebase only where existing internals still import those functions.
- The backlog item is to move any remaining retired CLI logic into business modules and stop exposing it through parser registration.
