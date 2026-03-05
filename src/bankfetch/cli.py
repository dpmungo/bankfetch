from pathlib import Path
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

_ENV_TEMPLATE = """\
EB_APP_ID=<your-app-uuid>
EB_PRIVATE_KEY_PATH=<path-to-key.pem>
EB_REDIRECT_URL=https://localhost/auth_redirect
EB_SESSION_FILE=.session.json
EB_ACCESS_DAYS=30
# Bank to connect to — run `bankfetch aspsps` for available names and country codes.
EB_ASPSP_NAME=<bank-name>
EB_ASPSP_COUNTRY=<two-letter-country-code>
"""


@app.command()
def init() -> None:
    """Create a .env template in the current directory."""
    env_file = Path(".env")
    if env_file.exists():
        typer.echo(".env already exists. Remove it first if you want to reset it.")
        raise typer.Exit(1)
    env_file.write_text(_ENV_TEMPLATE)
    env_file.chmod(0o600)
    typer.echo("Created .env — open it and fill in EB_APP_ID and EB_PRIVATE_KEY_PATH.")


@app.command()
def parsers() -> None:
    """List available transaction parsers."""
    for name in list_parsers():
        typer.echo(name)


@app.command()
def aspsps(
    country: Annotated[
        str | None,
        typer.Option(
            "--country",
            "-c",
            metavar="CC",
            help="Filter by two-letter country code (e.g. IT, DE, FI).",
        ),
    ] = None,
) -> None:
    """List banks available via Enable Banking."""
    config = Config.from_env()
    client = EnableBankingClient(config)
    results = client.get_aspsps(country=country)
    if not results:
        typer.echo("No banks found.")
        return
    for aspsp in sorted(results, key=lambda a: (a["country"], a["name"])):
        typer.echo(f"{aspsp['country']}  {aspsp['name']}")


@app.command()
def auth(
    bank: Annotated[
        str | None,
        typer.Option(
            "--bank",
            "-b",
            metavar="NAME",
            help="Bank name (overrides EB_ASPSP_NAME). Run 'bankfetch aspsps' to list options.",
        ),
    ] = None,
    country: Annotated[
        str | None,
        typer.Option(
            "--country",
            "-c",
            metavar="CC",
            help="Two-letter country code (overrides EB_ASPSP_COUNTRY, e.g. IT).",
        ),
    ] = None,
) -> None:
    """Authenticate with the bank and save the session locally."""
    config = Config.from_env()
    if bank:
        config.aspsp_name = bank
    if country:
        config.aspsp_country = country.upper()
    if not (config.aspsp_name and config.aspsp_country):
        logger.error(
            "Bank name and country are required. "
            "Set EB_ASPSP_NAME and EB_ASPSP_COUNTRY in your .env file, "
            "or pass --bank and --country. "
            "Run 'bankfetch aspsps' to list available banks."
        )
        raise typer.Exit(1)
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
