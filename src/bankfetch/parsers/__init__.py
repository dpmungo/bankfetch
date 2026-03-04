import importlib
import importlib.util
import os
import pkgutil
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

_REGISTRY: dict[str, type["BaseParser"]] = {}


def register(name: str):
    """Decorator to register a parser under a short name."""

    def decorator(cls: type["BaseParser"]):
        _REGISTRY[name] = cls
        return cls

    return decorator


def get_parser(name: str) -> "BaseParser":
    try:
        return _REGISTRY[name]()
    except KeyError:
        available = ", ".join(_REGISTRY)
        raise ValueError(f"Unknown parser '{name}'. Available: {available}")


def list_parsers() -> list[str]:
    return list(_REGISTRY.keys())


@dataclass
class ParsedTransaction:
    date: str  # booking_date, fallback value_date
    amount: str  # signed decimal string (negative = debit)
    currency: str  # ISO 4217, e.g. "EUR"
    direction: str  # "credit" | "debit"
    counterparty: str  # creditor or debtor name
    category: str  # transaction type label
    description: str  # payment narrative
    notes: str  # user-facing free-text note


class BaseParser(ABC):
    @abstractmethod
    def parse(self, txn: dict) -> ParsedTransaction:
        """Map a raw Enable Banking transaction dict to a ParsedTransaction."""
        ...


# Built-in parsers in this package.
for _mod_info in pkgutil.iter_modules(__path__):
    importlib.import_module(f"{__name__}.{_mod_info.name}")

# User parsers: drop a .py file in ~/.config/bankfetch/parsers/ (or $BANKFETCH_PARSERS_DIR).
_plugin_dir = Path(
    os.environ.get(
        "BANKFETCH_PARSERS_DIR", Path.home() / ".config" / "bankfetch" / "parsers"
    )
)
if _plugin_dir.is_dir():
    for _plugin_file in sorted(_plugin_dir.glob("*.py")):
        _spec = importlib.util.spec_from_file_location(_plugin_file.stem, _plugin_file)
        if _spec and _spec.loader:
            _mod = importlib.util.module_from_spec(_spec)
            sys.modules[_plugin_file.stem] = _mod
            _spec.loader.exec_module(_mod)