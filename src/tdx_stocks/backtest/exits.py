from __future__ import annotations

from .models import PortfolioParams, Position
from .risk import check_exit_signal as _check_exit_signal


class ExitEngine:
    @staticmethod
    def check(position: Position, bar, params: PortfolioParams) -> str | None:
        return _check_exit_signal(position, bar, params)
