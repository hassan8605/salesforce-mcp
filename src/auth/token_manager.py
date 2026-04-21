"""
Per-user Salesforce OAuth token storage.

Tokens are stored as JSON files: {TOKENS_DIR}/{user_id}.json
Each file contains: access_token, refresh_token, instance_url, token_type
"""

import asyncio
import json
import time
from pathlib import Path
from typing import Optional

import httpx
import structlog

from src.settings import settings

logger = structlog.get_logger(__name__)

_write_lock = asyncio.Lock()


_OAUTH_STATE_TTL = 600  # 10 minutes


def _token_path(user_id: str) -> Path:
    return Path(settings.SF_TOKENS_DIR) / f"{user_id}.json"


def _state_path(state: str) -> Path:
    return Path(settings.SF_TOKENS_DIR) / f"state_{state}.json"


async def save_oauth_state(state: str, user_id: str) -> None:
    """Persist an OAuth CSRF state token to disk so server restarts don't lose it."""
    path = _state_path(state)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"user_id": user_id, "expires_at": time.time() + _OAUTH_STATE_TTL}
    await asyncio.to_thread(path.write_text, json.dumps(payload), "utf-8")
    _purge_expired_states()


async def load_oauth_state(state: str) -> Optional[str]:
    """Load and consume an OAuth CSRF state token. Returns user_id or None if missing/expired."""
    path = _state_path(state)
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    path.unlink(missing_ok=True)
    if time.time() > data.get("expires_at", 0):
        return None
    return data.get("user_id")


def _purge_expired_states() -> None:
    """Delete expired state files to avoid accumulation."""
    tokens_dir = Path(settings.SF_TOKENS_DIR)
    now = time.time()
    for f in tokens_dir.glob("state_*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if now > data.get("expires_at", 0):
                f.unlink(missing_ok=True)
        except Exception:
            pass


async def load_tokens(user_id: str) -> Optional[dict]:
    path = _token_path(user_id)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


async def save_tokens(user_id: str, tokens: dict) -> None:
    path = _token_path(user_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    async with _write_lock:
        await asyncio.to_thread(
            path.write_text, json.dumps(tokens, indent=2), "utf-8"
        )
    logger.info("tokens.saved", user_id=user_id, instance_url=tokens.get("instance_url"))


async def delete_tokens(user_id: str) -> bool:
    path = _token_path(user_id)
    if path.exists():
        path.unlink()
        logger.info("tokens.deleted", user_id=user_id)
        return True
    return False


async def refresh_access_token(user_id: str) -> dict:
    """
    Use the stored refresh_token to get a new access_token from Salesforce.
    Salesforce does NOT rotate refresh tokens — the existing one stays valid.
    """
    tokens = await load_tokens(user_id)
    if not tokens or not tokens.get("refresh_token"):
        raise RuntimeError(f"No refresh token found for user '{user_id}'. Re-authorization required.")

    logger.info("tokens.refreshing", user_id=user_id)

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{settings.SF_LOGIN_URL}/services/oauth2/token",
            data={
                "grant_type": "refresh_token",
                "client_id": settings.SF_CLIENT_ID,
                "client_secret": settings.SF_CLIENT_SECRET,
                "refresh_token": tokens["refresh_token"],
            },
        )
        response.raise_for_status()
        new_data = response.json()

    updated = {
        **tokens,
        "access_token": new_data["access_token"],
        "instance_url": new_data.get("instance_url", tokens["instance_url"]),
    }
    await save_tokens(user_id, updated)
    logger.info("tokens.refreshed", user_id=user_id)
    return updated


async def get_valid_tokens(user_id: str) -> dict:
    """
    Load tokens and test connectivity. Refresh automatically if the access
    token is expired (Salesforce returns 401 on expired sessions).
    """
    tokens = await load_tokens(user_id)
    if not tokens:
        raise RuntimeError(
            f"User '{user_id}' has not connected Salesforce. "
            f"Call GET /api/auth/start?user_id={user_id} first."
        )

    # Probe: lightweight identity call to detect expired session
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{tokens['instance_url']}/services/oauth2/userinfo",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )

    if response.status_code == 401:
        logger.warning("tokens.access_expired", user_id=user_id, action="refreshing")
        tokens = await refresh_access_token(user_id)

    return tokens


async def is_connected(user_id: str) -> bool:
    path = _token_path(user_id)
    return path.exists()
