"""
Salesforce OAuth 2.0 Web Server Flow.

Flow:
  1. GET /api/auth/start?user_id=xxx  → redirect user to Salesforce login
  2. User authorizes your Connected App
  3. Salesforce redirects to SF_REDIRECT_URI?code=ABC&state=XYZ
  4. GET /api/auth/callback?code=ABC&state=XYZ → exchange code, save tokens
"""

import secrets
from urllib.parse import urlencode

import httpx
import structlog

from src.auth.token_manager import load_oauth_state, save_oauth_state, save_tokens
from src.settings import settings

logger = structlog.get_logger(__name__)


async def build_authorization_url(user_id: str) -> str:
    """
    Generate the Salesforce OAuth authorization URL and persist the CSRF state to disk.
    Redirect the user to the returned URL.
    """
    state = secrets.token_urlsafe(32)
    await save_oauth_state(state, user_id)

    params = {
        "response_type": "code",
        "client_id": settings.SF_CLIENT_ID,
        "redirect_uri": settings.SF_REDIRECT_URI,
        "scope": "api refresh_token",
        "state": state,
    }
    auth_url = f"{settings.SF_LOGIN_URL}/services/oauth2/authorize?{urlencode(params)}"
    logger.info("oauth.auth_url_created", user_id=user_id)
    return auth_url


async def handle_callback(code: str, state: str) -> str:
    """
    Exchange the authorization code for access + refresh tokens.
    Save tokens to disk and return the user_id.
    """
    user_id = await load_oauth_state(state)
    if user_id is None:
        raise ValueError("Unknown or expired OAuth state. Please start the auth flow again.")

    logger.info("oauth.exchanging_code", user_id=user_id)

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{settings.SF_LOGIN_URL}/services/oauth2/token",
            data={
                "grant_type": "authorization_code",
                "client_id": settings.SF_CLIENT_ID,
                "client_secret": settings.SF_CLIENT_SECRET,
                "redirect_uri": settings.SF_REDIRECT_URI,
                "code": code,
            },
        )

    if response.status_code != 200:
        raise RuntimeError(f"Salesforce token exchange failed: {response.text}")

    token_data = response.json()

    await save_tokens(
        user_id,
        {
            "access_token": token_data["access_token"],
            "refresh_token": token_data.get("refresh_token", ""),
            "instance_url": token_data["instance_url"],
            "token_type": token_data.get("token_type", "Bearer"),
            "scope": token_data.get("scope", ""),
            "id": token_data.get("id", ""),
        },
    )

    logger.info("oauth.tokens_saved", user_id=user_id, instance_url=token_data["instance_url"])
    return user_id
