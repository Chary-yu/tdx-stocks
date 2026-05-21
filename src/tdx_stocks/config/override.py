from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any


def set_by_dotted_key(config: MutableMapping[str, Any], dotted_key: str, value: Any) -> None:
    parts = [part for part in dotted_key.split(".") if part]
    if not parts:
        return
    node: MutableMapping[str, Any] = config
    for part in parts[:-1]:
        child = node.get(part)
        if not isinstance(child, MutableMapping):
            child = {}
            node[part] = child
        node = child
    node[parts[-1]] = value
