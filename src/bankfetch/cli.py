from typing import Annotated

import typer
from loguru import logger

from .auth import AuthClient
from .client import EnableBankingClient
from .config import Config
from .export import to_csv
from .parsers import list_parsers

app = typer.Typer(
    name="bankfetch",
    help="Download your bank account transactions via the Enable Banking API.",
    no_args_is_help=True,
)


@app.command()
def auth() -> None:
    """Authenticate with the bank and save the session locally."""
    config = Config.from_env()
    auth_client = AuthClient(config)
    auth_client.store.clear()
    auth_client.login()


@app.command()
def fetch(
    from_date: Annotated[
        str | None,
        typer.Option(
            "--from", metavar="YYYY-MM-DD", help="Start date (e.g. 2024-01-01)"
        ),
    ] = None,
    to_date: Annotated[
        str | None,
        typer.Option(
            "--to", metavar="YYYY-MM-DD", help="End date (default: no upper limit)"
        ),
    ] = None,
    output: Annotated[
        str,
        typer.Option("--output", "-o", metavar="FILE", help="Output CSV file"),
    ] = "transactions.csv",
    account: Annotated[
        str | None,
        typer.Option(
            "--account",
            metavar="IBAN|UID",
            help="Account IBAN or UID (default: first available)",
        ),
    ] = None,
    parser: Annotated[
        str,
        typer.Option(
            "--parser",
            metavar="NAME",
            help="Bank-specific transaction parser (default: generic)",
        ),
    ] = "generic",
) -> None:
    """Fetch transactions and export them to a CSV file."""
    config = Config.from_env()
    auth_client = AuthClient(config)
    session = auth_client.get_valid_session()

    account_uids: list[str] = session["accounts"]
    if not account_uids:
        logger.error("No accounts found in session.")
        raise typer.Exit(1)

    client = EnableBankingClient(config)
    accounts = client.get_accounts(account_uids)

    if account:
        selected = next(
            (
                a
                for a in accounts
                if a.get("account_id", {}).get("iban") == account
                or a.get("uid") == account
            ),
            None,
        )
        if selected is None:
            logger.error(f"Account not found: {account}")
            raise typer.Exit(1)
    else:
        selected = accounts[0]
        if len(accounts) > 1:
            iban = (selected.get("account_id") or {}).get("iban") or selected.get("uid")
            logger.info(f"Found {len(accounts)} accounts. Using: {iban}")

    transactions = client.get_transactions(
        selected["uid"],
        date_from=from_date,
        date_to=to_date,
    )

    available = list_parsers()
    if parser not in available:
        logger.error(f"Unknown parser '{parser}'. Available: {', '.join(available)}")
        raise typer.Exit(1)

    count = to_csv(transactions, output, parser=parser)
    logger.info(f"Exported {count} transactions to '{output}'")


def main() -> None:
    app()
