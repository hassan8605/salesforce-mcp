import structlog
import httpx
from fastapi import APIRouter

from src.auth.token_manager import is_connected, load_tokens
from src.response import BuildJSONResponses

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/health")


@router.get("/salesforce")
async def salesforce_health(user_id: str):
    """
    Deep health check: verifies live Salesforce API connectivity using the
    OAuth userinfo endpoint. Returns org identity info on success.

    Usage: GET /api/health/salesforce?user_id=your-user-id
    """
    try:
        if not await is_connected(user_id):
            return BuildJSONResponses.raise_exception(
                f"User '{user_id}' has not connected Salesforce. "
                f"Call GET /api/auth/start?user_id={user_id} first.",
                status_code=401,
            )

        tokens = await load_tokens(user_id)
        instance_url = tokens["instance_url"]
        access_token = tokens["access_token"]

        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{instance_url}/services/oauth2/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            response.raise_for_status()
            identity = response.json()

        return BuildJSONResponses.success_response(
            data={
                "connected": True,
                "user_id": user_id,
                "username": identity.get("preferred_username") or identity.get("email"),
                "org_id": identity.get("organization_id"),
                "display_name": identity.get("name"),
                "instance_url": instance_url,
            },
            message="Salesforce connection is healthy.",
        )
    except Exception as exc:
        logger.error("salesforce.health_check_failed", user_id=user_id, error=str(exc))
        return BuildJSONResponses.server_error(
            f"Salesforce connectivity check failed: {exc}"
        )
