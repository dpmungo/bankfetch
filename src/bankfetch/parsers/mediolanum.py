from . import BaseParser, ParsedTransaction, register
from .generic import _signed_amount


@register("mediolanum")
class MediolanumParser(BaseParser):
    """
    Parser for Banca Mediolanum transactions.

    Banca Mediolanum encodes rich information inside ``remittance_information``
    segments.  This parser extracts category, merchant/counterparty description,
    and user notes from those segments.
    """

    def parse(self, txn: dict) -> ParsedTransaction:
        date = txn.get("booking_date") or txn.get("value_date", "")
        amount_obj = txn.get("transaction_amount") or {}
        currency = amount_obj.get("currency", "")
        direction = "debit" if txn.get("credit_debit_indicator") == "DBIT" else "credit"
        counterparty = (txn.get("creditor") or txn.get("debtor") or {}).get("name", "")
        remittance = txn.get("remittance_information") or []
        if remittance:
            category, description, notes = _parse_remittance(remittance)
        else:
            category, description, notes = _fallback(txn)
        return ParsedTransaction(
            date=date,
            amount=_signed_amount(txn),
            currency=currency,
            direction=direction,
            counterparty=counterparty,
            category=category,
            description=description,
            notes=notes,
        )


def _parse_remittance(parts: list[str]) -> tuple[str, str, str]:
    """
    Parse Banca Mediolanum remittance_information segments into
    (category, description, notes).

    The bank's segments follow a consistent pattern:
      - Last segment: movement category (e.g. "Pagamenti paesi UE",
        "ADDEBITO DIRETTO", "BONIFICO A VOSTRO FAVORE")
      - Second-to-last: "Causale Movimento: {code}"
      - Card payments contain a "C/O {merchant/location}" segment
      - Transfers have the counterparty name as the first segment,
        with an optional "Note: {text}" segment
    """
    if not parts:
        return "", "", ""

    stripped = [p.strip() for p in parts]

    # Movement category is the last segment
    category = stripped[-1]

    # Extract optional user note ("Note: ...")
    notes = ""
    for seg in stripped:
        if seg.startswith("Note:"):
            notes = seg[len("Note:") :].strip()
            break

    # Build a concise description:
    #   - Card transactions: use the "C/O <location>" segment
    #   - Everything else: use the first segment (counterparty / reference)
    description = ""
    for seg in stripped:
        if seg.startswith("C/O"):
            description = seg[3:].strip()
            break

    if not description and stripped:
        # Skip segments that are clearly not human-readable descriptions
        first = stripped[0]
        if not first.startswith("CORE RCUR") and not first.startswith(
            "Causale Movimento"
        ):
            description = first

    return category, description, notes


def _fallback(txn: dict) -> tuple[str, str, str]:
    """
    Return (category, description, notes) when no remittance_information is
    present, using counterparty name and bank transaction code.
    """
    counterparty = (txn.get("creditor") or txn.get("debtor") or {}).get("name", "")
    code_obj = txn.get("bank_transaction_code") or {}
    category = code_obj.get("description") or ""
    return category, counterparty, ""
