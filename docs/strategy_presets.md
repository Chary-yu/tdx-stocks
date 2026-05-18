# Strategy Presets

## trend-strength

Compatibility baseline. Designed to keep the original trend observation pool
available while the framework evolves.

## low-vol-breakout

Breakout-oriented preset for stocks that are close to a 20-day high with
controlled volatility.

## ma-pullback

Pullback-oriented preset for names that remain above medium-term moving averages
but have cooled off from short-term strength.

## relative-strength

Momentum-oriented preset for names that are holding up better than the broader
universe.

## volume-breakout

Volume-oriented preset for names with active participation and price strength.

## Notes

The current first pass keeps the same underlying engine for all presets. The
differences come from the preset name, candidate filter, and strategy-level
entry points.

