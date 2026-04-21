import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src import api_router
from src.context import current_user_id
from src.mcp_server.server import create_mcp_server
from src.settings import settings


class UserIDMiddleware:
    """
    Pure-ASGI middleware that reads ?user_id= from the SSE connection URL
    and injects it into the current_user_id ContextVar before the request
    is handled. All MCP tool calls within that connection inherit the value.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            query_string = scope.get("query_string", b"").decode()
            params: dict[str, str] = {}
            for part in query_string.split("&"):
                if "=" in part:
                    k, v = part.split("=", 1)
                    params[k] = v
            token = current_user_id.set(params.get("user_id", ""))
            try:
                await self.app(scope, receive, send)
            finally:
                current_user_id.reset(token)
        else:
            await self.app(scope, receive, send)


app = FastAPI(
    title="Salesforce MCP",
    description="Multi-user Salesforce MCP Server — FastAPI + FastMCP + OAuth + SSE",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# REST API: /api/auth/*, /api/health/*
app.include_router(api_router, prefix="/api")

# MCP server wrapped with UserIDMiddleware so each SSE connection
# carries its own user_id via: GET /mcp/sse?user_id=alice
_mcp = create_mcp_server()
app.mount("/mcp", UserIDMiddleware(_mcp.sse_app()))


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "healthy", "version": "2.0.0", "service": "salesforce-mcp"}


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.APP_HOST,
        port=settings.APP_PORT,
        reload=settings.ENVIRONMENT == "development",
    )
