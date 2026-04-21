"""
MCP server exposing 8 Salesforce tools via FastMCP (SSE transport).

user_id is injected per SSE connection via UserIDMiddleware (main.py),
which reads the ?user_id= query param from the SSE URL and sets the
current_user_id ContextVar. Tools read it via get_current_user().

Claude Desktop config (%APPDATA%\\Claude\\claude_desktop_config.json):
    {
      "mcpServers": {
        "salesforce-alice": {
          "url": "http://localhost:8000/mcp/sse?user_id=alice",
          "transport": "sse"
        }
      }
    }
"""

import json
from typing import Any

import structlog
from mcp.server.fastmcp import FastMCP

from src.context import current_user_id
from src.salesforce import tools as sf_tools

logger = structlog.get_logger(__name__)


def get_current_user() -> str:
    user_id = current_user_id.get()
    if not user_id:
        raise RuntimeError(
            "No user_id provided. Connect via /mcp/sse?user_id=YOUR_ID "
            "and ensure you have authorized at /api/auth/start?user_id=YOUR_ID"
        )
    return user_id


def create_mcp_server() -> FastMCP:
    mcp = FastMCP(name="salesforce-mcp")

    # ── Query Tools ───────────────────────────────────────────────

    @mcp.tool()
    async def query(query: str) -> str:
        """
        Execute a SOQL query against the user's Salesforce org.
        Pagination is handled automatically — all matching records are returned.
        Example: SELECT Id, Name, AccountNumber FROM Account WHERE CreatedDate = TODAY LIMIT 10
        """
        try:
            uid = get_current_user()
            return json.dumps(await sf_tools.soql_query(uid, query), default=str)
        except Exception as exc:
            logger.error("tool.query.error", error=str(exc))
            return json.dumps({"error": str(exc)})

    @mcp.tool()
    async def tooling_query(query: str) -> str:
        """
        Execute a Tooling API SOQL query against the user's Salesforce org.
        Use this to inspect developer artifacts: ApexClass, ApexTrigger, CustomField.
        Example: SELECT Id, Name, Body FROM ApexClass WHERE Name = 'MyClass'
        """
        try:
            uid = get_current_user()
            return json.dumps(await sf_tools.tooling_query(uid, query), default=str)
        except Exception as exc:
            logger.error("tool.tooling_query.error", error=str(exc))
            return json.dumps({"error": str(exc)})

    # ── Metadata Tools ────────────────────────────────────────────

    @mcp.tool()
    async def describe_object(object_name: str, detailed: bool = False) -> str:
        """
        Return schema metadata for any Salesforce object (standard or custom).
        Set detailed=true to include all fields and child relationships.
        Example object_name values: Account, Contact, Opportunity, My_Custom_Object__c
        """
        try:
            uid = get_current_user()
            return json.dumps(
                await sf_tools.describe_object(uid, object_name, detailed), default=str
            )
        except Exception as exc:
            logger.error("tool.describe_object.error", object_name=object_name, error=str(exc))
            return json.dumps({"error": str(exc)})

    @mcp.tool()
    async def metadata_retrieve(metadata_type: str, full_names: str) -> str:
        """
        Retrieve Salesforce metadata components by type and full API name.

        metadata_type must be one of:
          CustomObject, Flow, FlowDefinition, CustomField, ValidationRule,
          ApexClass, ApexTrigger, WorkflowRule, Layout

        full_names is a comma-separated list of component API names.
        Example: metadata_type="ApexClass", full_names="MyController,MyService"
        """
        try:
            uid = get_current_user()
            names = [n.strip() for n in full_names.split(",") if n.strip()]
            return json.dumps(
                await sf_tools.metadata_retrieve(uid, metadata_type, names), default=str
            )
        except Exception as exc:
            logger.error("tool.metadata_retrieve.error", type=metadata_type, error=str(exc))
            return json.dumps({"error": str(exc)})

    # ── Record CRUD Tools ─────────────────────────────────────────

    @mcp.tool()
    async def get_record(object_name: str, record_id: str) -> str:
        """
        Retrieve a single Salesforce record by its ID.
        Example: object_name="Account", record_id="0015g00000AbCdEAAV"
        """
        try:
            uid = get_current_user()
            return json.dumps(
                await sf_tools.get_record(uid, object_name, record_id), default=str
            )
        except Exception as exc:
            logger.error("tool.get_record.error", object=object_name, id=record_id, error=str(exc))
            return json.dumps({"error": str(exc)})

    @mcp.tool()
    async def create_record(object_name: str, data: str) -> str:
        """
        Create a new Salesforce record.
        data must be a JSON string of field name to value pairs.
        Example: object_name="Contact", data='{"FirstName":"Jane","LastName":"Doe","Email":"jane@acme.com"}'
        Returns the new record ID on success.
        """
        try:
            uid = get_current_user()
            record_data: dict[str, Any] = json.loads(data)
            return json.dumps(
                await sf_tools.create_record(uid, object_name, record_data), default=str
            )
        except json.JSONDecodeError as exc:
            return json.dumps({"error": f"data must be valid JSON: {exc}"})
        except Exception as exc:
            logger.error("tool.create_record.error", object=object_name, error=str(exc))
            return json.dumps({"error": str(exc)})

    @mcp.tool()
    async def update_record(object_name: str, record_id: str, data: str) -> str:
        """
        Update fields on an existing Salesforce record.
        data must be a JSON string containing only the fields to change.
        Example: object_name="Account", record_id="0015g00000AbCdEAAV", data='{"Name":"New Name"}'
        """
        try:
            uid = get_current_user()
            record_data: dict[str, Any] = json.loads(data)
            return json.dumps(
                await sf_tools.update_record(uid, object_name, record_id, record_data), default=str
            )
        except json.JSONDecodeError as exc:
            return json.dumps({"error": f"data must be valid JSON: {exc}"})
        except Exception as exc:
            logger.error("tool.update_record.error", object=object_name, id=record_id, error=str(exc))
            return json.dumps({"error": str(exc)})

    @mcp.tool()
    async def delete_record(object_name: str, record_id: str) -> str:
        """
        Permanently delete a Salesforce record. This action cannot be undone.
        Example: object_name="Contact", record_id="0035g00000AbCdEAAV"
        """
        try:
            uid = get_current_user()
            return json.dumps(
                await sf_tools.delete_record(uid, object_name, record_id), default=str
            )
        except Exception as exc:
            logger.error("tool.delete_record.error", object=object_name, id=record_id, error=str(exc))
            return json.dumps({"error": str(exc)})

    return mcp
