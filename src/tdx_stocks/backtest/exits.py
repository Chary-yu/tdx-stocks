from __future__ import annotations

from .models import PortfolioParams, Position
from .risk import check_exit_signal as _check_exit_signal, check_hard_stop as _check_hard_stop


class ExitEngine:
    @staticmethod
    def check(position: Position, bar, params: PortfolioParams, *, hold_days: int) -> tuple[str | None, str | None]:
        hard = _check_hard_stop(position, bar, params)
        if hard is not None:
            return hard, "hard_stop"
        if hold_days < max(int(params.min_hold_days or 1), 0):
            return None, None
        reason = _check_exit_signal(position, bar, params)
        return reason, "technical" if reason else (None, None)
