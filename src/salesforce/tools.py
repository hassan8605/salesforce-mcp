"""
Salesforce tool implementations — all scoped to a specific user_id.

Each function takes user_id as the first argument and loads that user's
OAuth-authenticated Salesforce connection. Synchronous simple-salesforce
calls are wrapped in asyncio.to_thread() to avoid blocking the event loop.
"""

import asyncio
from typing import Any

import structlog

from src.salesforce.client import get_salesforce_client

logger = structlog.get_logger(__name__)

VALID_METADATA_TYPES = {
    "CustomObject",
    "Flow",
    "FlowDefinition",
    "CustomField",
    "ValidationRule",
    "ApexClass",
    "ApexTrigger",
    "WorkflowRule",
    "Layout",
}


# ── Query Tools ───────────────────────────────────────────────────────────────

async def soql_query(user_id: str, query: str) -> dict[str, Any]:
    sf = await get_salesforce_client(user_id)

    def _execute() -> dict:
        result = sf.query_all(query)
        records = result["records"]

        # Normalize COUNT() aggregate queries.
        # Salesforce returns totalSize=1 with records=[{"expr0": N}] for COUNT().
        # Extract the real count so Claude reads it correctly.
        is_count_query = (
            len(records) == 1
            and result["totalSize"] == 1
            and "expr0" in records[0]
            and not any(k for k in records[0] if k not in ("attributes", "expr0"))
        )
        if is_count_query:
            return {
                "totalSize": records[0]["expr0"],
                "done": True,
                "records": [],
                "count": records[0]["expr0"],
            }

        return {
            "totalSize": result["totalSize"],
            "done": result["done"],
            "records": records,
        }

    return await asyncio.to_thread(_execute)


async def tooling_query(user_id: str, query: str) -> dict[str, Any]:
    sf = await get_salesforce_client(user_id)

    def _execute() -> dict:
        result = sf.toolingexecute(f"query?q={query}")
        return {
            "totalSize": result.get("size", result.get("totalSize", 0)),
            "done": result.get("done", True),
            "records": result.get("records", []),
        }

    return await asyncio.to_thread(_execute)


# ── Metadata Tools ────────────────────────────────────────────────────────────

async def describe_object(user_id: str, object_name: str, detailed: bool = False) -> dict[str, Any]:
    sf = await get_salesforce_client(user_id)

    def _execute() -> dict:
        desc = sf.__getattr__(object_name).describe()
        return {
            "name": desc.get("name"),
            "label": desc.get("label"),
            "labelPlural": desc.get("labelPlural"),
            "keyPrefix": desc.get("keyPrefix"),
            "createable": desc.get("createable"),
            "updateable": desc.get("updateable"),
            "deletable": desc.get("deletable"),
            "queryable": desc.get("queryable"),
            "fields": desc.get("fields", []) if detailed else [],
            "childRelationships": desc.get("childRelationships", []) if detailed else [],
            "recordTypeInfos": desc.get("recordTypeInfos", []),
        }

    return await asyncio.to_thread(_execute)


async def metadata_retrieve(user_id: str, metadata_type: str, full_names: list[str]) -> dict[str, Any]:
    if metadata_type not in VALID_METADATA_TYPES:
        raise ValueError(
            f"Invalid metadata type '{metadata_type}'. "
            f"Must be one of: {', '.join(sorted(VALID_METADATA_TYPES))}"
        )

    sf = await get_salesforce_client(user_id)

    def _execute() -> dict:
        result = sf.mdapi.read(metadata_type, full_names)
        if isinstance(result, dict):
            result = [result]
        return {"type": metadata_type, "records": result, "count": len(result)}

    return await asyncio.to_thread(_execute)


# ── CRUD Tools ────────────────────────────────────────────────────────────────

async def get_record(user_id: str, object_name: str, record_id: str) -> dict[str, Any]:
    sf = await get_salesforce_client(user_id)

    def _execute() -> dict:
        return dict(sf.__getattr__(object_name).get(record_id))

    return await asyncio.to_thread(_execute)


async def create_record(user_id: str, object_name: str, data: dict[str, Any]) -> dict[str, Any]:
    sf = await get_salesforce_client(user_id)

    def _execute() -> dict:
        result = sf.__getattr__(object_name).create(data)
        return {
            "id": result.get("id"),
            "success": result.get("success", False),
            "errors": result.get("errors", []),
            "object": object_name,
        }

    return await asyncio.to_thread(_execute)


async def update_record(
    user_id: str, object_name: str, record_id: str, data: dict[str, Any]
) -> dict[str, Any]:
    sf = await get_salesforce_client(user_id)

    def _execute() -> dict:
        http_status = sf.__getattr__(object_name).update(record_id, data)
        return {
            "id": record_id,
            "object": object_name,
            "updated": http_status == 204,
            "httpStatusCode": http_status,
        }

    return await asyncio.to_thread(_execute)


async def delete_record(user_id: str, object_name: str, record_id: str) -> dict[str, Any]:
    sf = await get_salesforce_client(user_id)

    def _execute() -> dict:
        http_status = sf.__getattr__(object_name).delete(record_id)
        return {
            "id": record_id,
            "object": object_name,
            "deleted": http_status == 204,
            "httpStatusCode": http_status,
        }

    return await asyncio.to_thread(_execute)
