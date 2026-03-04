import requests

from .auth import make_jwt
from .config import API_BASE, Config


class EnableBankingClient:
    """
    Client for the Enable Banking AIS REST API.

    Every request carries a freshly-signed RS256 JWT as Bearer token.
    Transactions are fetched with continuation_key pagination.
    """

    def __init__(self, config: Config) -> None:
        self.config = config
        self._key = config.read_private_key()

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {make_jwt(self._key, self.config.app_id)}"}

    def get_accounts(self, account_uids: list[str]) -> list[dict]:
        """
        Fetch account details for each UID returned in the session.
        Returns a list of account dicts with at minimum 'uid', 'account_id' (IBAN), 'currency'.
        """
        accounts = []
        for uid in account_uids:
            resp = requests.get(
                f"{API_BASE}/accounts/{uid}/details",
                headers=self._headers(),
                timeout=30,
            )
            resp.raise_for_status()
            accounts.append(resp.json())
        return accounts

    def get_transactions(
        self,
        account_uid: str,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[dict]:
        """
        Fetch all transactions for *account_uid*, following continuation_key pagination.

        date_from / date_to: ISO 8601 date strings (YYYY-MM-DD).
        Returns a flat list of transaction dicts.
        """
        params: dict[str, str] = {}
        if date_from:
            params["date_from"] = date_from
        if date_to:
            params["date_to"] = date_to

        all_transactions: list[dict] = []
        while True:
            resp = requests.get(
                f"{API_BASE}/accounts/{account_uid}/transactions",
                params=params,
                headers=self._headers(),
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            all_transactions.extend(data.get("transactions", []))
            continuation_key = data.get("continuation_key")
            if not continuation_key:
                break
            params["continuation_key"] = continuation_key

        return all_transactions
