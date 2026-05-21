from __future__ import annotations

from .models import PortfolioParams, Position
from .risk import check_exit_signal as _check_exit_signal


class ExitEngine:
    @staticmethod
    def check(position: Position, current_price: float, params: PortfolioParams) -> str | None:
        return _check_exit_signal(position, current_price, params)
