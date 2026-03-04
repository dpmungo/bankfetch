from abc import ABC, abstractmethod
from dataclasses import dataclass
import importlib
import pkgutil

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


# Auto-discover and import all modules in this package so their
# @register decorators fire — no manual imports needed when adding a new parser.
for _mod_info in pkgutil.iter_modules(__path__):
    importlib.import_module(f"{__name__}.{_mod_info.name}")
