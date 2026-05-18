from __future__ import annotations

from .catalog import FACTOR_CATALOG, FactorDefinition, list_factor_definitions

_REGISTRY = {definition.name: definition for definition in FACTOR_CATALOG}


def get_factor_definition(name: str) -> FactorDefinition:
    try:
        return _REGISTRY[name]
    except KeyError as exc:
        raise KeyError(f"unknown factor: {name}") from exc


def list_factor_definitions_by_name() -> list[FactorDefinition]:
    return sorted(list_factor_definitions(), key=lambda item: (item.group, item.name))
