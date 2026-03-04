"""Tests for bankfetch.client."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from bankfetch.client import EnableBankingClient
from bankfetch.config import Config


@pytest.fixture
def client(config: Config) -> EnableBankingClient:
    return EnableBankingClient(config)


def _mock_resp(data: dict) -> MagicMock:
    m = MagicMock()
    m.raise_for_status = MagicMock()
    m.json.return_value = data
    return m


class TestGetAccounts:
    def test_fetches_each_uid(self, client: EnableBankingClient):
        responses = [
            _mock_resp({"uid": "uid-1", "account_id": {"iban": "IT60X..."}}),
            _mock_resp({"uid": "uid-2", "account_id": {"iban": "IT60Y..."}}),
        ]
        with patch("requests.get", side_effect=responses) as mock_get:
            accounts = client.get_accounts(["uid-1", "uid-2"])

        assert len(accounts) == 2
        assert mock_get.call_count == 2

    def test_url_contains_uid(self, client: EnableBankingClient):
        with patch("requests.get", return_value=_mock_resp({"uid": "abc"})) as mock_get:
            client.get_accounts(["abc"])

        url = mock_get.call_args[0][0]
        assert "accounts/abc" in url

    def test_empty_uid_list(self, client: EnableBankingClient):
        with patch("requests.get") as mock_get:
            accounts = client.get_accounts([])
        assert accounts == []
        mock_get.assert_not_called()

    def test_raises_on_http_error(self, client: EnableBankingClient):
        m = MagicMock()
        m.raise_for_status.side_effect = requests.HTTPError("404")
        with patch("requests.get", return_value=m):
            with pytest.raises(requests.HTTPError):
                client.get_accounts(["bad-uid"])


class TestGetTransactions:
    def test_returns_transactions(self, client: EnableBankingClient):
        txns = [{"transaction_id": "T1"}, {"transaction_id": "T2"}]
        with patch(
            "requests.get",
            return_value=_mock_resp({"transactions": txns}),
        ):
            result = client.get_transactions("uid-1")

        assert result == txns

    def test_follows_continuation_key(self, client: EnableBankingClient):
        page1 = _mock_resp(
            {"transactions": [{"transaction_id": "T1"}], "continuation_key": "page2"}
        )
        page2 = _mock_resp({"transactions": [{"transaction_id": "T2"}]})

        with patch("requests.get", side_effect=[page1, page2]) as mock_get:
            result = client.get_transactions("uid-1")

        assert len(result) == 2
        assert mock_get.call_count == 2
        # Second call must include continuation_key in params
        second_params = mock_get.call_args_list[1][1]["params"]
        assert second_params["continuation_key"] == "page2"

    def test_date_params_forwarded(self, client: EnableBankingClient):
        with patch(
            "requests.get", return_value=_mock_resp({"transactions": []})
        ) as mock_get:
            client.get_transactions(
                "uid-1", date_from="2024-01-01", date_to="2024-12-31"
            )

        params = mock_get.call_args[1]["params"]
        assert params["date_from"] == "2024-01-01"
        assert params["date_to"] == "2024-12-31"

    def test_no_date_params_when_not_provided(self, client: EnableBankingClient):
        with patch(
            "requests.get", return_value=_mock_resp({"transactions": []})
        ) as mock_get:
            client.get_transactions("uid-1")

        params = mock_get.call_args[1]["params"]
        assert "date_from" not in params
        assert "date_to" not in params

    def test_raises_on_http_error(self, client: EnableBankingClient):
        m = MagicMock()
        m.raise_for_status.side_effect = requests.HTTPError("403")
        with patch("requests.get", return_value=m):
            with pytest.raises(requests.HTTPError):
                client.get_transactions("uid-1")
