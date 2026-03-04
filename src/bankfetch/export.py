import csv
from pathlib import Path

from .parsers import BaseParser, get_parser


def to_csv(
    transactions: list[dict],
    output_path: str,
    parser: "BaseParser | str" = "generic",
) -> int:
    """
    Write *transactions* to a CSV file at *output_path*.

    *parser* can be either a BaseParser instance or a registered parser name
    (e.g. ``"mediolanum"``, ``"generic"``).

    Columns:
      Date         → booking_date (fallback: value_date)
      Amount       → signed decimal (negative = debit / outflow)
      Currency     → ISO 4217 (e.g. EUR)
      Direction    → "credit" | "debit"
      Counterparty → creditor or debtor name
      Category     → transaction type label
      Description  → payment narrative
      Notes        → free-text note

    Returns the number of rows written.
    """
    if isinstance(parser, str):
        parser = get_parser(parser)

    path = Path(output_path)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "Date",
                "Amount",
                "Currency",
                "Direction",
                "Counterparty",
                "Category",
                "Description",
                "Notes",
            ]
        )
        count = 0
        for txn in transactions:
            row = parser.parse(txn)
            writer.writerow(
                [
                    row.date,
                    row.amount,
                    row.currency,
                    row.direction,
                    row.counterparty,
                    row.category,
                    row.description,
                    row.notes,
                ]
            )
            count += 1
    return count
