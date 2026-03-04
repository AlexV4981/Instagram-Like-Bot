"""
session_manager.py — Manages Instagram sessions via instagrapi.

No browser needed — uses Instagram Private API.
Uses Instagram's Private Mobile API through instagrapi.
Sessions are saved/loaded as JSON via dump_settings/load_settings.
Credentials stored in .env via python-dotenv.
"""

import os
import json
from pathlib import Path
from dotenv import load_dotenv
from cryptography.fernet import Fernet, InvalidToken

BASE_DIR   = Path(__file__).parent
DATA_DIR   = BASE_DIR / "data"
KEY_FILE   = DATA_DIR / "vault.key"
SESSION_FILE = DATA_DIR / "session.json"
VAULT_FILE = DATA_DIR / "session.vault"
LINKS_FILE = DATA_DIR / "liked_posts.json"
ENV_FILE   = BASE_DIR / ".env"


def ensure_dirs():
    DATA_DIR.mkdir(exist_ok=True)


# ── encryption helpers ────────────────────────────────────────
def _get_or_create_key() -> bytes:
    ensure_dirs()
    if KEY_FILE.exists():
        return KEY_FILE.read_bytes()
    key = Fernet.generate_key()
    KEY_FILE.write_bytes(key)
    return key


def _cipher() -> Fernet:
    return Fernet(_get_or_create_key())


# ── session vault (encrypted instagrapi settings) ─────────────
def save_session(settings: dict) -> None:
    """Encrypt instagrapi settings dict and write to vault."""
    ensure_dirs()
    payload = json.dumps(settings).encode("utf-8")
    VAULT_FILE.write_bytes(_cipher().encrypt(payload))


def load_session() -> dict | None:
    """Decrypt vault and return instagrapi settings dict, or None."""
    if not VAULT_FILE.exists():
        return None
    try:
        decrypted = _cipher().decrypt(VAULT_FILE.read_bytes())
        return json.loads(decrypted.decode("utf-8"))
    except (InvalidToken, json.JSONDecodeError):
        return None


def session_exists() -> bool:
    return VAULT_FILE.exists()


def delete_session() -> None:
    if VAULT_FILE.exists():
        VAULT_FILE.unlink()


# ── liked links (plain JSON) ─────────────────────────────────
def save_liked_link(url: str) -> None:
    ensure_dirs()
    data = load_liked_links()
    if url not in data:
        data.append(url)
        LINKS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_liked_links() -> list[str]:
    if not LINKS_FILE.exists():
        return []
    try:
        return json.loads(LINKS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


# ── .env helpers ──────────────────────────────────────────────
def load_env() -> dict:
    load_dotenv(ENV_FILE)
    return {
        "username": os.getenv("IG_USERNAME", ""),
        "password": os.getenv("IG_PASSWORD", ""),
    }


def save_env(username: str, password: str) -> None:
    ENV_FILE.write_text(
        f"IG_USERNAME={username}\nIG_PASSWORD={password}\n",
        encoding="utf-8",
    )
