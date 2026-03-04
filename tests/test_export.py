"""Tests for bankfetch.export and the generic parser."""

import csv
from pathlib import Path


from bankfetch.export import to_csv
from bankfetch.parsers.generic import GenericParser, _signed_amount
from tests.conftest import SAMPLE_TRANSACTIONS


# ---------------------------------------------------------------------------
# _signed_amount
# ---------------------------------------------------------------------------


class TestSignedAmount:
    def test_dbit_becomes_negative(self):
        txn = {
            "credit_debit_indicator": "DBIT",
            "transaction_amount": {"amount": "100.00", "currency": "EUR"},
        }
        assert _signed_amount(txn) == "-100.00"

    def test_crdt_stays_positive(self):
        txn = {
            "credit_debit_indicator": "CRDT",
            "transaction_amount": {"amount": "2500.00", "currency": "EUR"},
        }
        assert _signed_amount(txn) == "2500.00"

    def test_already_negative_dbit_not_doubled(self):
        txn = {
            "credit_debit_indicator": "DBIT",
            "transaction_amount": {"amount": "-100.00", "currency": "EUR"},
        }
        assert _signed_amount(txn) == "-100.00"

    def test_missing_amount_returns_empty(self):
        assert _signed_amount({}) == ""


# ---------------------------------------------------------------------------
# GenericParser
# ---------------------------------------------------------------------------


class TestGenericParser:
    def setup_method(self):
        self.parser = GenericParser()

    def test_counterparty_from_creditor(self):
        txn = {
            "booking_date": "2024-11-01",
            "credit_debit_indicator": "DBIT",
            "transaction_amount": {"amount": "125.50", "currency": "EUR"},
            "remittance_information": ["Electricity bill October"],
            "creditor": {"name": "Power Co."},
        }
        row = self.parser.parse(txn)
        assert row.counterparty == "Power Co."
        assert row.direction == "debit"
        assert row.amount == "-125.50"
        assert row.currency == "EUR"

    def test_counterparty_from_debtor(self):
        txn = {
            "booking_date": "2024-11-05",
            "credit_debit_indicator": "CRDT",
            "transaction_amount": {"amount": "2500.00", "currency": "EUR"},
            "remittance_information": ["Salary November"],
            "debtor": {"name": "Acme Ltd"},
        }
        row = self.parser.parse(txn)
        assert row.counterparty == "Acme Ltd"
        assert row.direction == "credit"

    def test_description_is_joined_remittance(self):
        txn = {
            "booking_date": "2024-11-10",
            "credit_debit_indicator": "DBIT",
            "transaction_amount": {"amount": "50.00", "currency": "EUR"},
            "remittance_information": ["Mortgage payment", "Nov 2024"],
        }
        row = self.parser.parse(txn)
        assert row.description == "Mortgage payment | Nov 2024"

    def test_description_falls_back_to_counterparty_when_no_remittance(self):
        txn = {
            "booking_date": "2024-11-15",
            "credit_debit_indicator": "DBIT",
            "transaction_amount": {"amount": "20.00", "currency": "EUR"},
            "creditor": {"name": "Grocery Store XYZ"},
        }
        row = self.parser.parse(txn)
        assert row.description == "Grocery Store XYZ"

    def test_category_from_bank_transaction_code(self):
        txn = {
            "booking_date": "2024-11-01",
            "credit_debit_indicator": "DBIT",
            "transaction_amount": {"amount": "10.00", "currency": "EUR"},
            "bank_transaction_code": {"description": "Card payment"},
        }
        row = self.parser.parse(txn)
        assert row.category == "Card payment"

    def test_notes_from_api_note_field(self):
        txn = {
            "booking_date": "2024-11-01",
            "credit_debit_indicator": "DBIT",
            "transaction_amount": {"amount": "10.00", "currency": "EUR"},
            "note": "personal reminder",
        }
        row = self.parser.parse(txn)
        assert row.notes == "personal reminder"

    def test_notes_empty_when_no_note_field(self):
        txn = {
            "booking_date": "2024-11-01",
            "credit_debit_indicator": "DBIT",
            "transaction_amount": {"amount": "10.00", "currency": "EUR"},
            "remittance_information": ["Note: some note"],
        }
        row = self.parser.parse(txn)
        assert row.notes == ""

    def test_falls_back_to_value_date(self):
        txn = {
            "value_date": "2024-12-01",
            "credit_debit_indicator": "DBIT",
            "transaction_amount": {"amount": "10.00", "currency": "EUR"},
        }
        row = self.parser.parse(txn)
        assert row.date == "2024-12-01"

    def test_empty_transaction(self):
        row = self.parser.parse({})
        assert row.date == ""
        assert row.amount == ""
        assert row.currency == ""
        assert row.direction == "credit"
        assert row.counterparty == ""
        assert row.category == ""
        assert row.description == ""
        assert row.notes == ""


# ---------------------------------------------------------------------------
# to_csv (end-to-end)
# ---------------------------------------------------------------------------


class TestToCsv:
    def test_writes_header_and_rows(self, tmp_path: Path):
        output = str(tmp_path / "out.csv")
        count = to_csv(SAMPLE_TRANSACTIONS, output, parser="generic")

        assert count == len(SAMPLE_TRANSACTIONS)
        with open(output, encoding="utf-8", newline="") as f:
            rows = list(csv.reader(f))
        assert rows[0] == [
            "Date",
            "Amount",
            "Currency",
            "Direction",
            "Counterparty",
            "Category",
            "Description",
            "Notes",
        ]
        assert len(rows) == len(SAMPLE_TRANSACTIONS) + 1

    def test_dbit_amount_negative_in_csv(self, tmp_path: Path):
        output = str(tmp_path / "out.csv")
        to_csv(SAMPLE_TRANSACTIONS, output, parser="generic")

        with open(output, encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))

        assert rows[0]["Date"] == "2024-11-01"
        assert rows[0]["Amount"] == "-125.50"
        assert rows[0]["Direction"] == "debit"

    def test_crdt_amount_positive_in_csv(self, tmp_path: Path):
        output = str(tmp_path / "out.csv")
        to_csv(SAMPLE_TRANSACTIONS, output, parser="generic")

        with open(output, encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))

        assert rows[1]["Amount"] == "2500.00"
        assert rows[1]["Direction"] == "credit"

    def test_counterparty_and_description_in_csv(self, tmp_path: Path):
        output = str(tmp_path / "out.csv")
        to_csv(SAMPLE_TRANSACTIONS, output, parser="generic")

        with open(output, encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))

        # TX001: has both creditor and remittance
        assert rows[0]["Counterparty"] == "Power Co."
        assert rows[0]["Description"] == "Electricity bill October"
        # TX004: no remittance — description falls back to counterparty name
        assert rows[3]["Counterparty"] == "Grocery Store XYZ"
        assert rows[3]["Description"] == "Grocery Store XYZ"

    def test_empty_list_writes_only_header(self, tmp_path: Path):
        output = str(tmp_path / "out.csv")
        count = to_csv([], output, parser="generic")

        assert count == 0
        with open(output, encoding="utf-8", newline="") as f:
            rows = list(csv.reader(f))
        assert rows == [
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
        ]

    def test_fallback_to_value_date(self, tmp_path: Path):
        txn = {
            "value_date": "2024-12-01",
            "credit_debit_indicator": "DBIT",
            "transaction_amount": {"amount": "10.00", "currency": "EUR"},
        }
        output = str(tmp_path / "out.csv")
        to_csv([txn], output, parser="generic")

        with open(output, encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))

        assert rows[0]["Date"] == "2024-12-01"
