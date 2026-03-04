import pytest

from bankfetch.config import Config


@pytest.fixture
def config(tmp_path) -> Config:
    # Write a minimal RSA private key for tests (2048-bit, generated once)
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    )
    key_path = tmp_path / "test_key.pem"
    key_path.write_bytes(pem)

    return Config(
        app_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        private_key_path=str(key_path),
        redirect_url="http://localhost:8080/auth_redirect",
        session_file=str(tmp_path / "session.json"),
    )


SAMPLE_TRANSACTIONS = [
    {
        "transaction_id": "TX001",
        "booking_date": "2024-11-01",
        "value_date": "2024-11-01",
        "credit_debit_indicator": "DBIT",
        "transaction_amount": {"amount": "125.50", "currency": "EUR"},
        "remittance_information": ["Electricity bill October"],
        "creditor": {"name": "Power Co."},
        "bank_transaction_code": {"family_code": "PMNT", "sub_family_code": "ESCT"},
    },
    {
        "transaction_id": "TX002",
        "booking_date": "2024-11-05",
        "value_date": "2024-11-05",
        "credit_debit_indicator": "CRDT",
        "transaction_amount": {"amount": "2500.00", "currency": "EUR"},
        "remittance_information": ["Salary November"],
        "debtor": {"name": "Acme Ltd"},
    },
    {
        "transaction_id": "TX003",
        "booking_date": "2024-11-10",
        "value_date": "2024-11-10",
        "credit_debit_indicator": "DBIT",
        "transaction_amount": {"amount": "50.00", "currency": "EUR"},
        "remittance_information": ["Mortgage payment", "Nov 2024"],
        "bank_transaction_code": {"family_code": "LDAS", "sub_family_code": "DDWN"},
    },
    {
        "transaction_id": "TX004",
        "booking_date": "2024-11-15",
        "value_date": "2024-11-15",
        "credit_debit_indicator": "DBIT",
        "transaction_amount": {"amount": "20.00", "currency": "EUR"},
        "creditor": {"name": "Grocery Store XYZ"},
        "bank_transaction_code": {"family_code": "PMNT", "sub_family_code": "POSD"},
    },
]
