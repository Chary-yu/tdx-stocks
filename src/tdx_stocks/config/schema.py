from __future__ import annotations

CORE_EXECUTION_SECTIONS = {
    "exit_rules",
    "consensus",
    "signal",
    "portfolio",
    "rebalance",
}

# Recognized but currently partial features.
UNSUPPORTED_FEATURE_RULES = {
    ("portfolio", "weighting"): {"risk-parity"},
}
