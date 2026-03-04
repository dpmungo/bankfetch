import json
import os
import uuid
import webbrowser
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import jwt
import requests
from loguru import logger

from .config import API_BASE, Config

# Maximum length accepted for the user-pasted redirect URL (DoS / injection guard)
_MAX_REDIRECT_URL_LEN = 4096


# ---------------------------------------------------------------------------
# JWT helper
# ---------------------------------------------------------------------------


def make_jwt(private_key: bytes, app_id: str) -> str:
    """Sign a short-lived RS256 JWT used as Bearer token on every API call.

    * ``exp`` is 60 seconds — enough for a single HTTP round-trip.
    * ``jti`` is a per-call UUID that prevents token replay within the exp window.
    """
    now = int(datetime.now(timezone.utc).timestamp())
    return jwt.encode(
        {
            "iss": "enablebanking.com",
            "aud": "api.enablebanking.com",
            "iat": now,
            "exp": now + 60,  # 60-second window — one request only
            "jti": str(uuid.uuid4()),  # unique token ID; thwarts replay attacks
        },
        private_key,
        algorithm="RS256",
        headers={"kid": app_id},
    )


# ---------------------------------------------------------------------------
# Auth code extraction (manual paste flow)
# ---------------------------------------------------------------------------


def _extract_code(
    redirected_url: str,
    expected_state: str,
    expected_redirect_prefix: str,
) -> str:
    """Parse and validate the authorization code from the redirect URL pasted by the user.

    Enforces:
    - URL length limit (DoS guard)
    - Scheme and host must match the registered redirect URL
    - ``state`` must match the value sent in ``POST /auth`` (CSRF guard)
    - Error strings from the bank are never forwarded verbatim to the caller
    """
    if len(redirected_url) > _MAX_REDIRECT_URL_LEN:
        raise ValueError("Redirect URL is too long.")

    parsed = urlparse(redirected_url)
    expected = urlparse(expected_redirect_prefix)

    if parsed.scheme != expected.scheme:
        raise ValueError(
            "Redirect URL scheme does not match the registered redirect URL."
        )
    if parsed.netloc != expected.netloc:
        raise ValueError(
            "Redirect URL host does not match the registered redirect URL."
        )

    params = parse_qs(parsed.query)

    if "error" in params:
        # Log the raw bank error only at DEBUG to avoid leaking it to stdout/logs
        logger.debug("Bank returned auth error: {!r}", params["error"][0])
        raise RuntimeError("Authentication was denied by the bank.")

    if "code" not in params:
        raise ValueError("Invalid redirect URL: 'code' parameter not found.")

    if "state" not in params:
        raise ValueError("Invalid redirect URL: 'state' parameter not found.")

    if params["state"][0] != expected_state:
        raise ValueError("State mismatch — possible CSRF attack. Aborting.")

    return params["code"][0]


# ---------------------------------------------------------------------------
# Session store
# ---------------------------------------------------------------------------


class SessionStore:
    """Persists session_id and account UIDs to a local JSON file."""

    def __init__(self, path: str) -> None:
        self._path = Path(path)

    def load(self) -> dict | None:
        if not self._path.exists():
            return None
        return json.loads(self._path.read_text())

    def save(self, data: dict) -> None:
        self._path.write_text(json.dumps(data, indent=2))
        # Restrict to owner-only: session_id is a long-lived credential
        os.chmod(self._path, 0o600)

    def is_valid(self) -> bool:
        data = self.load()
        if not data:
            return False
        return bool(data.get("session_id")) and bool(data.get("accounts"))

    def clear(self) -> None:
        if self._path.exists():
            self._path.unlink()


# ---------------------------------------------------------------------------
# Auth client
# ---------------------------------------------------------------------------


class AuthClient:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.store = SessionStore(config.session_file)
        # Private key is NOT cached — it is loaded fresh, used, and zeroed per call.

    def _headers(self) -> dict:
        """Load the private key, sign a JWT, then zero and discard the key bytes."""
        key = bytearray(self.config.read_private_key())
        try:
            token = make_jwt(bytes(key), self.config.app_id)
        finally:
            # Best-effort in-process zeroing before the GC can observe the bytes
            for i in range(len(key)):
                key[i] = 0
            del key
        return {"Authorization": f"Bearer {token}"}

    def _start_auth(self) -> tuple[str, str]:
        """POST /auth — returns (auth_url, state).

        The ``state`` value must be stored by the caller and verified against the
        callback parameter to prevent CSRF.
        """
        state = str(uuid.uuid4())
        valid_until = (
            datetime.now(timezone.utc) + timedelta(days=self.config.access_days)
        ).isoformat()
        body = {
            "access": {"valid_until": valid_until},
            "aspsp": {"name": "Banca Mediolanum", "country": "IT"},
            "state": state,
            "redirect_url": self.config.redirect_url,
            "psu_type": "personal",
        }
        resp = requests.post(
            f"{API_BASE}/auth", json=body, headers=self._headers(), timeout=30
        )
        resp.raise_for_status()
        data = resp.json()
        return data["url"], state

    def _create_session(self, code: str) -> dict:
        """POST /sessions — exchange auth code for session."""
        resp = requests.post(
            f"{API_BASE}/sessions",
            json={"code": code},
            headers=self._headers(),
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    def check_session(self, session_id: str) -> str:
        """Return session status string (e.g. 'authorized', 'expired')."""
        resp = requests.get(
            f"{API_BASE}/sessions/{session_id}",
            headers=self._headers(),
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json().get("status", "unknown")

    def login(self) -> dict:
        """
        Full authorization flow:
        1. POST /auth  → get the bank redirect URL + a CSRF state token
        2. Open browser; user authenticates at the bank
        3. Browser is redirected to the registered URL (which won't load);
           user copies that URL from the address bar and pastes it here
        4. Redirect URL is validated (scheme/host/state) before extracting the code
        5. POST /sessions → exchange code for session_id + account UIDs
        6. Persist to disk with restricted permissions (0o600)
        """
        auth_url, state = self._start_auth()
        logger.info(f"Opening browser for authentication:\n\n  {auth_url}\n")
        webbrowser.open(auth_url)

        print(
            "After completing authentication, your browser will be redirected\n"
            f"to a URL starting with: {self.config.redirect_url}\n"
            "That page will not load — this is expected.\n"
            "Copy the full URL from the browser address bar and paste it here:\n"
        )
        redirected_url = input("Redirect URL: ").strip()
        code = _extract_code(redirected_url, state, self.config.redirect_url)

        session = self._create_session(code)

        record = {
            "session_id": session["session_id"],
            "accounts": [a["uid"] for a in session.get("accounts", [])],
        }
        self.store.save(record)
        logger.info("Authentication completed and session saved.")
        return record

    def get_valid_session(self) -> dict:
        """Return stored session if still alive, otherwise run login."""
        stored = self.store.load()
        if stored and stored.get("session_id"):
            try:
                status = self.check_session(stored["session_id"])
                if status.lower() == "authorized":
                    return stored
                logger.info(f"Session status: {status!r}. Re-authenticating...")
            except requests.HTTPError:
                logger.info("Session check failed. Re-authenticating...")
        return self.login()
