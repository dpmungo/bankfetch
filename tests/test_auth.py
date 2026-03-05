"""Tests for bankfetch.auth (SessionStore, make_jwt, AuthClient)."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

import jwt

from bankfetch.auth import AuthClient, SessionStore, make_jwt
from bankfetch.config import Config


# ---------------------------------------------------------------------------
# make_jwt
# ---------------------------------------------------------------------------


class TestMakeJwt:
    def test_valid_rs256_jwt(self, config: Config):
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        private_pem = key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
        public_pem = key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )

        token = make_jwt(private_pem, "test-app-id")
        decoded = jwt.decode(
            token,
            public_pem,
            algorithms=["RS256"],
            audience="api.enablebanking.com",
        )
        assert decoded["iss"] == "enablebanking.com"
        assert decoded["aud"] == "api.enablebanking.com"
        assert "exp" in decoded

    def test_kid_header_matches_app_id(self, config: Config):
        key_bytes = config.read_private_key()
        token = make_jwt(key_bytes, config.app_id)
        header = jwt.get_unverified_header(token)
        assert header["kid"] == config.app_id
        assert header["alg"] == "RS256"


# ---------------------------------------------------------------------------
# SessionStore
# ---------------------------------------------------------------------------


class TestSessionStore:
    def test_load_returns_none_when_missing(self, config: Config):
        store = SessionStore(config.session_file)
        assert store.load() is None

    def test_save_and_load_roundtrip(self, config: Config):
        store = SessionStore(config.session_file)
        data = {"session_id": "sid-123", "accounts": ["uid-1"]}
        store.save(data)
        assert store.load() == data

    def test_is_valid_false_when_missing(self, config: Config):
        assert not SessionStore(config.session_file).is_valid()

    def test_is_valid_false_when_no_accounts(self, config: Config):
        store = SessionStore(config.session_file)
        store.save({"session_id": "sid", "accounts": []})
        assert not store.is_valid()

    def test_is_valid_true_when_complete(self, config: Config):
        store = SessionStore(config.session_file)
        store.save({"session_id": "sid", "accounts": ["uid-1"]})
        assert store.is_valid()

    def test_clear_removes_file(self, config: Config):
        store = SessionStore(config.session_file)
        store.save({"session_id": "x", "accounts": ["y"]})
        store.clear()
        assert not Path(config.session_file).exists()

    def test_clear_noop_when_missing(self, config: Config):
        SessionStore(config.session_file).clear()  # must not raise


# ---------------------------------------------------------------------------
# AuthClient.get_valid_session
# ---------------------------------------------------------------------------


class TestAuthClientGetValidSession:
    def test_returns_stored_session_when_authorized(self, config: Config):
        store = SessionStore(config.session_file)
        stored = {"session_id": "sid-ok", "accounts": ["uid-1"]}
        store.save(stored)

        auth = AuthClient(config)
        with patch.object(auth, "check_session", return_value="authorized"):
            result = auth.get_valid_session()

        assert result == stored

    def test_triggers_login_when_no_session(self, config: Config):
        auth = AuthClient(config)
        with patch.object(
            auth, "login", return_value={"session_id": "new", "accounts": ["u"]}
        ) as mock_login:
            auth.get_valid_session()

        mock_login.assert_called_once()

    def test_triggers_login_when_session_expired(self, config: Config):
        store = SessionStore(config.session_file)
        store.save({"session_id": "old-sid", "accounts": ["uid-1"]})

        auth = AuthClient(config)
        with patch.object(auth, "check_session", return_value="expired"):
            with patch.object(auth, "login", return_value={}) as mock_login:
                auth.get_valid_session()

        mock_login.assert_called_once()

    def test_triggers_login_on_http_error(self, config: Config):
        import requests as req

        store = SessionStore(config.session_file)
        store.save({"session_id": "bad-sid", "accounts": ["uid-1"]})

        auth = AuthClient(config)
        with patch.object(auth, "check_session", side_effect=req.HTTPError("401")):
            with patch.object(auth, "login", return_value={}) as mock_login:
                auth.get_valid_session()

        mock_login.assert_called_once()


# ---------------------------------------------------------------------------
# AuthClient._start_auth — aspsp field is optional
# ---------------------------------------------------------------------------


class TestStartAuth:
    def _mock_post(self, url: str, state: str) -> MagicMock:
        """Return a mock that simulates a successful POST /auth response."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"url": url}
        mock_resp.raise_for_status.return_value = None
        return mock_resp

    def test_aspsp_included_when_configured(self, config: Config):
        config.aspsp_name = "Banca Mediolanum"
        config.aspsp_country = "IT"
        auth = AuthClient(config)

        with patch("bankfetch.auth.requests.post") as mock_post:
            mock_post.return_value = self._mock_post("https://bank.example/login", "s")
            with patch.object(auth, "_headers", return_value={}):
                auth._start_auth()

        body = mock_post.call_args.kwargs["json"]
        assert body["aspsp"] == {"name": "Banca Mediolanum", "country": "IT"}

    def test_aspsp_omitted_when_not_configured(self, config: Config):
        # aspsp_name=None, aspsp_country=None → ValueError before any HTTP call
        auth = AuthClient(config)

        with patch("bankfetch.auth.requests.post") as mock_post:
            with patch.object(auth, "_headers", return_value={}):
                with pytest.raises(ValueError, match="aspsp_name"):
                    auth._start_auth()

        mock_post.assert_not_called()
