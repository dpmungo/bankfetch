import os
import stat
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

API_BASE = "https://api.enablebanking.com"

_ENV_FILE = Path(".env")


def _check_file_permissions(path: Path, label: str) -> None:
    """Raise ``PermissionError`` if *path* is readable or writable by others.

    Sensitive files (.env, private key) must be accessible only by the owner
    (mode 0o600 or stricter).  World-readable credentials are a common source
    of credential leaks in shared / multi-user environments.
    """
    if not path.exists():
        return
    mode = path.stat().st_mode
    if mode & stat.S_IRWXO:
        raise PermissionError(
            f"{label} ({path}) must not be accessible by other users. "
            f"Fix with: chmod 600 {path}"
        )


@dataclass
class Config:
    app_id: str  # UUID from Enable Banking Control Panel
    private_key_path: str  # Path to the .pem file downloaded during app registration
    redirect_url: str  # Must match what's registered in the Control Panel
    session_file: str  # Local file to persist session_id + account UIDs
    access_days: int = 30  # How many days ahead the bank access grant is valid
    aspsp_name: str | None = None  # Bank name, e.g. "Banca Mediolanum" (required for auth)
    aspsp_country: str | None = None  # Two-letter ISO country code, e.g. "IT" (required for auth)

    @classmethod
    def from_env(cls) -> "Config":
        # Check sensitive files are not world-readable before loading secrets
        _check_file_permissions(_ENV_FILE, ".env")
        private_key_path = os.environ["EB_PRIVATE_KEY_PATH"]
        _check_file_permissions(Path(private_key_path), "private key")
        return cls(
            app_id=os.environ["EB_APP_ID"],
            private_key_path=private_key_path,
            redirect_url=os.environ.get(
                "EB_REDIRECT_URL", "https://localhost/auth_redirect"
            ),
            session_file=os.environ.get("EB_SESSION_FILE", ".session.json"),
            access_days=int(os.environ.get("EB_ACCESS_DAYS", "30")),
            aspsp_name=os.environ.get("EB_ASPSP_NAME") or None,
            aspsp_country=os.environ.get("EB_ASPSP_COUNTRY") or None,
        )

    def read_private_key(self) -> bytes:
        return Path(self.private_key_path).read_bytes()
