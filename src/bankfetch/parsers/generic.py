from . import BaseParser, ParsedTransaction, register


def _signed_amount(txn: dict) -> str:
    """
    Return the signed amount as a string.

    Enable Banking returns amounts always positive; credit_debit_indicator
    distinguishes direction: CRDT = inflow (+), DBIT = outflow (-).
    """
    amount_obj = txn.get("transaction_amount") or {}
    amount = amount_obj.get("amount", "")
    if not amount:
        return ""
    if txn.get("credit_debit_indicator") == "DBIT" and not str(amount).startswith("-"):
        return f"-{amount}"
    return str(amount)


@register("generic")
class GenericParser(BaseParser):
    """
    Straight mapping from Enable Banking transaction fields — no bank-specific
    interpretation.  Use this to explore raw API data or as the baseline for
    writing a custom parser.

    CSV columns produced:
      Date         → booking_date (fallback: value_date)
      Amount       → signed decimal (negative = debit)
      Currency     → ISO 4217 currency code
      Direction    → "credit" | "debit"
      Counterparty → creditor name (debit) or debtor name (credit)
      Category     → bank_transaction_code.description
      Description  → remittance_information joined with " | " (fallback: counterparty)
      Notes        → note field set by the PSU in their banking app
    """

    def parse(self, txn: dict) -> ParsedTransaction:
        date = txn.get("booking_date") or txn.get("value_date", "")
        amount_obj = txn.get("transaction_amount") or {}
        currency = amount_obj.get("currency", "")
        direction = "debit" if txn.get("credit_debit_indicator") == "DBIT" else "credit"
        counterparty = (txn.get("creditor") or txn.get("debtor") or {}).get("name", "")
        code_obj = txn.get("bank_transaction_code") or {}
        category = code_obj.get("description") or ""
        remittance = txn.get("remittance_information") or []
        description = (
            " | ".join(r.strip() for r in remittance) if remittance else counterparty
        )
        notes = txn.get("note") or ""
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
