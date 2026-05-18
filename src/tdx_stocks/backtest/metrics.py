from __future__ import annotations


def max_drawdown(equity_curve: list[float]) -> float:
    if not equity_curve:
        return 0.0
    peak = equity_curve[0]
    worst = 0.0
    for value in equity_curve:
        if value > peak:
            peak = value
        if peak > 0:
            drawdown = value / peak - 1.0
            if drawdown < worst:
                worst = drawdown
    return round(worst, 6)


def annualize_return(total_return: float, days: int) -> float:
    if days <= 0:
        return total_return
    return round((1.0 + total_return) ** (365.0 / days) - 1.0, 6)
