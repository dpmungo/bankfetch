# BankFetch, download your own bank account transactions via Enable Banking API

CLI tool that fetches bank account transactions via [Enable Banking](https://enablebanking.com) and exports them to CSV. Enable Banking acts as the licensed AISP intermediary, so you don't need an eIDAS certificate or TPP registration of your own.

Built primarily for accessing transactions in my Banca Mediolanum account, but you implement your own parser to support other banks in a hopefully straightforward way.

## Requirements

- Python 3.14+
- [uv](https://docs.astral.sh/uv/)
- An Enable Banking account with a registered app and a linked bank account

## Setup

1. Register at [enablebanking.com/cp/applications](https://enablebanking.com/cp/applications) and create a **Production (Restricted)** app (free for personal use on your own accounts).
2. During app creation, set the redirect URL to `https://localhost/auth_redirect`. This must match exactly what the tool uses for the OAuth callback.
3. Download the generated `.pem` private key.
4. In the Control Panel, activate the app by linking your bank account ("Activate" button next to the app).
5. Copy `.env.example` to `.env` and fill in the values:

```
EB_APP_ID=<your-app-uuid>
EB_PRIVATE_KEY_PATH=<path-to-key.pem>
EB_REDIRECT_URL=https://localhost/auth_redirect   # default, must match Control Panel
EB_SESSION_FILE=.session.json                     # default
EB_ACCESS_DAYS=30                                 # how many days ahead the bank access grant is valid
```

Both `.env` and the `.pem` file must be owner-readable only (`chmod 600`). The tool refuses to start if they are world-readable.

6. Install dependencies:

```bash
just install
```

## Usage

A [Justfile](Justfile) is included with shortcuts for all common tasks. Run `just` or `just --list` to see everything available.

**Authenticate:**

```bash
just auth
```

This opens a browser to the bank's login page. After completing authentication, the browser redirects to `https://localhost/auth_redirect` (which will not load — that's expected). Copy the full URL from the address bar and paste it into the terminal. The session is saved to `.session.json` and reused on subsequent calls. Re-authentication is triggered automatically when the session expires.

**Fetch transactions to CSV:**

```bash
just fetch --from 2024-01-01
just fetch --from 2024-01-01 --output my-transactions.csv
just fetch --from 2024-01-01 --to 2024-12-31 --account IT60X0542811101000000123456
just fetch --help
```

### Options for `fetch`

| Option | Default | Description |
|---|---|---|
| `--from YYYY-MM-DD` | none | Start date (inclusive) |
| `--to YYYY-MM-DD` | none | End date (inclusive) |
| `--output FILE` | `transactions.csv` | Output path |
| `--account IBAN\|UID` | first available | Target account |
| `--parser NAME` | `generic` | Transaction parser to use |

## CSV format

```
Date, Type, Description, Notes, Amount
```

- `Date` - booking date, falls back to value date
- `Type` - movement category
- `Description` - merchant, counterparty, or reference text
- `Notes` - free-text note left by the user in the banking app (parser-dependent)
- `Amount` - signed amount (negative = debit)

## Parsers

Parsers translate raw Enable Banking transaction objects into the CSV columns above. Selected with `--parser NAME`.

| Name | Description |
|---|---|
| `generic` | Default. Works with any bank. Uses `bank_transaction_code`, creditor/debtor name, and the first remittance segment. |
| `mediolanum` | Banca Mediolanum. Parses the bank's `remittance_information` segments in detail to extract movement category, merchant/counterparty, and user notes. |

### Adding a parser

Create a module under `src/bankfetch/parsers/`, subclass `BaseParser`, and decorate the class with `@register("your-name")`. It will be auto-discovered at import time — no manual wiring needed.

```python
from . import BaseParser, ParsedTransaction, register

@register("mybank")
class MyBankParser(BaseParser):
    def parse(self, txn: dict) -> ParsedTransaction:
        ...
```

## Repository layout

```
src/bankfetch/
├── config.py          Config dataclass; loads .env; enforces file permissions
├── auth.py            RS256 JWT signing; OAuth2 redirect flow; SessionStore
├── client.py          EnableBankingClient: account details + paginated transactions
├── export.py          to_csv(): runs a parser over transactions and writes CSV
├── cli.py             Typer CLI — `auth` and `fetch` subcommands
└── parsers/
    ├── __init__.py    BaseParser ABC; @register decorator; auto-discovery
    ├── generic.py     GenericParser — works with any bank
    └── mediolanum.py  MediolanumParser — Banca Mediolanum remittance parsing

tests/
├── conftest.py        Shared fixtures (RSA key generation, sample transactions)
├── test_auth.py       JWT generation, redirect URL validation, session flow
├── test_client.py     Account and transaction fetch, pagination
└── test_export.py     GenericParser, _variazione, to_csv()
```

## Development

```bash
just install  # install dependencies including dev and pre-commit hooks
just test     # run all tests
```

Linting, formatting, and type-checking run automatically via pre-commit on every commit.