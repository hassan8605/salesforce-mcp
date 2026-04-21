import structlog
from fastapi import APIRouter
from pydantic import BaseModel, Field

from src.auth.token_manager import is_connected
from src.response import BuildJSONResponses
from src.salesforce.service import process_query

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/salesforce")


class QueryRequest(BaseModel):
    user_id: str = Field(..., description="Unique identifier for the user")
    message: str = Field(..., description="Plain-English question or instruction")
    timezone: str = Field("UTC", description="IANA timezone e.g. America/New_York")


@router.post("/query")
async def salesforce_query(request: QueryRequest):
    """
    Send a plain-English query and get a response powered by Claude.
    Claude will decide which Salesforce tools to call and return a human-readable answer.

    Example body:
    {
      "user_id": "hassan",
      "message": "Show me the 5 most recently created Accounts",
      "timezone": "UTC"
    }
    """
    try:
        if not await is_connected(request.user_id):
            return BuildJSONResponses.raise_exception(
                f"User '{request.user_id}' has not connected Salesforce. "
                f"Visit /api/auth/start?user_id={request.user_id} first.",
                status_code=401,
            )

        result = await process_query(
            user_id=request.user_id,
            message=request.message,
            timezone=request.timezone,
        )

        return BuildJSONResponses.success_response(
            data=result,
            message="Query completed successfully.",
        )

    except RuntimeError as exc:
        logger.error("salesforce.query.runtime_error", user_id=request.user_id, error=str(exc))
        return BuildJSONResponses.raise_exception(str(exc), status_code=401)
    except Exception as exc:
        logger.error("salesforce.query.error", user_id=request.user_id, error=str(exc))
        return BuildJSONResponses.server_error(str(exc))
