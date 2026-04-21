import structlog
from fastapi import APIRouter
from fastapi.responses import RedirectResponse

from src.auth import oauth, token_manager
from src.response import BuildJSONResponses
from src.salesforce.client import evict_client

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/auth")


@router.get("/start")
async def auth_start(user_id: str):
    """
    Step 1 of OAuth: redirect the user to Salesforce login.
    The user authorizes your Connected App, then Salesforce calls /auth/callback.

    Usage: GET /api/auth/start?user_id=your-unique-user-id
    """
    try:
        auth_url = await oauth.build_authorization_url(user_id)
        return RedirectResponse(url=auth_url)
    except Exception as exc:
        logger.error("auth.start_failed", user_id=user_id, error=str(exc))
        return BuildJSONResponses.server_error(str(exc))


@router.get("/callback")
async def auth_callback(code: str, state: str):
    """
    Step 2 of OAuth: Salesforce redirects here after user authorization.
    Exchanges the code for tokens and saves them.
    """
    try:
        user_id = await oauth.handle_callback(code, state)
        return BuildJSONResponses.success_response(
            data={"user_id": user_id, "connected": True},
            message=f"Salesforce connected successfully for user '{user_id}'.",
        )
    except ValueError as exc:
        logger.error("auth.callback_invalid_state", error=str(exc))
        return BuildJSONResponses.raise_exception(str(exc), status_code=400)
    except Exception as exc:
        logger.error("auth.callback_failed", error=str(exc))
        return BuildJSONResponses.server_error(str(exc))


@router.get("/status")
async def auth_status(user_id: str):
    """
    Check whether a user has connected their Salesforce org.

    Usage: GET /api/auth/status?user_id=your-user-id
    """
    connected = await token_manager.is_connected(user_id)
    return BuildJSONResponses.success_response(
        data={"user_id": user_id, "connected": connected},
        message="Connected." if connected else "Not connected — call /api/auth/start first.",
    )


@router.delete("/disconnect")
async def auth_disconnect(user_id: str):
    """
    Remove a user's stored Salesforce tokens, disconnecting them.

    Usage: DELETE /api/auth/disconnect?user_id=your-user-id
    """
    deleted = await token_manager.delete_tokens(user_id)
    await evict_client(user_id)
    return BuildJSONResponses.success_response(
        data={"user_id": user_id, "disconnected": deleted},
        message="Disconnected." if deleted else "User was not connected.",
    )
