"""
Per-user Salesforce client factory.

Each user has their own OAuth tokens (stored in SF_TOKENS_DIR/{user_id}.json).
Connections are cached in memory per user_id and refreshed on 401.
"""

import threading

import structlog
from simple_salesforce import Salesforce

from src.auth.token_manager import get_valid_tokens

logger = structlog.get_logger(__name__)

# user_id → Salesforce instance
_clients: dict[str, Salesforce] = {}
_lock = threading.Lock()


def _build_client(tokens: dict) -> Salesforce:
    return Salesforce(
        instance_url=tokens["instance_url"],
        session_id=tokens["access_token"],
    )


async def get_salesforce_client(user_id: str) -> Salesforce:
    """
    Return a Salesforce client for the given user.
    Loads OAuth tokens from disk, refreshes if expired, caches in memory.
    """
    # Validate tokens (refreshes if needed) — this also raises if not connected
    tokens = await get_valid_tokens(user_id)

    with _lock:
        if user_id not in _clients:
            _clients[user_id] = _build_client(tokens)
        else:
            # Update client if token was refreshed
            existing = _clients[user_id]
            if existing.session_id != tokens["access_token"]:
                _clients[user_id] = _build_client(tokens)

    return _clients[user_id]


async def evict_client(user_id: str) -> None:
    """Remove a user's cached client (e.g. after disconnect)."""
    with _lock:
        _clients.pop(user_id, None)
