"""
NLP agentic loop for Salesforce queries.

Accepts plain-English messages, uses Claude to decide which Salesforce
tools to call, executes them against the user's org, and returns a
human-readable answer.
"""

import json
from functools import partial
from typing import Any

import anthropic
import structlog

from src.salesforce import tools as sf_tools
from src.settings import settings

logger = structlog.get_logger(__name__)

# ── Tool definitions (JSON schema for Claude) ─────────────────────────────────

TOOL_DEFINITIONS: list[dict] = [
    {
        "name": "query",
        "description": "Execute a SOQL query against the Salesforce org. Pagination is handled automatically.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "SOQL query to execute"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "tooling_query",
        "description": "Execute a Tooling API SOQL query to inspect Apex classes, triggers, custom fields.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Tooling API SOQL query"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "describe_object",
        "description": "Get schema metadata for any Salesforce object (standard or custom). Use detailed=true to include all fields.",
        "input_schema": {
            "type": "object",
            "properties": {
                "object_name": {"type": "string", "description": "API name of the object e.g. Account, Contact, My_Object__c"},
                "detailed": {"type": "boolean", "description": "Include all fields and relationships", "default": False},
            },
            "required": ["object_name"],
        },
    },
    {
        "name": "metadata_retrieve",
        "description": "Retrieve Salesforce metadata components (ApexClass, Flow, CustomObject, etc.)",
        "input_schema": {
            "type": "object",
            "properties": {
                "metadata_type": {
                    "type": "string",
                    "description": "Metadata type",
                    "enum": ["CustomObject", "Flow", "FlowDefinition", "CustomField",
                             "ValidationRule", "ApexClass", "ApexTrigger", "WorkflowRule", "Layout"],
                },
                "full_names": {
                    "type": "string",
                    "description": "Comma-separated list of component API names",
                },
            },
            "required": ["metadata_type", "full_names"],
        },
    },
    {
        "name": "get_record",
        "description": "Retrieve a single Salesforce record by its ID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "object_name": {"type": "string", "description": "Salesforce object API name"},
                "record_id": {"type": "string", "description": "18-character Salesforce record ID"},
            },
            "required": ["object_name", "record_id"],
        },
    },
    {
        "name": "create_record",
        "description": "Create a new Salesforce record.",
        "input_schema": {
            "type": "object",
            "properties": {
                "object_name": {"type": "string", "description": "Salesforce object API name"},
                "data": {"type": "string", "description": "JSON string of field name to value pairs"},
            },
            "required": ["object_name", "data"],
        },
    },
    {
        "name": "update_record",
        "description": "Update fields on an existing Salesforce record.",
        "input_schema": {
            "type": "object",
            "properties": {
                "object_name": {"type": "string", "description": "Salesforce object API name"},
                "record_id": {"type": "string", "description": "18-character Salesforce record ID"},
                "data": {"type": "string", "description": "JSON string of fields to update"},
            },
            "required": ["object_name", "record_id", "data"],
        },
    },
    {
        "name": "delete_record",
        "description": "Permanently delete a Salesforce record by ID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "object_name": {"type": "string", "description": "Salesforce object API name"},
                "record_id": {"type": "string", "description": "18-character Salesforce record ID"},
            },
            "required": ["object_name", "record_id"],
        },
    },
]


# ── Tool dispatch ─────────────────────────────────────────────────────────────

def _build_dispatch(user_id: str) -> dict[str, Any]:
    """Map tool names → async callables with user_id pre-bound."""

    async def _metadata_retrieve(metadata_type: str, full_names: str) -> dict:
        names = [n.strip() for n in full_names.split(",") if n.strip()]
        return await sf_tools.metadata_retrieve(user_id, metadata_type, names)

    async def _create_record(object_name: str, data: str) -> dict:
        return await sf_tools.create_record(user_id, object_name, json.loads(data))

    async def _update_record(object_name: str, record_id: str, data: str) -> dict:
        return await sf_tools.update_record(user_id, object_name, record_id, json.loads(data))

    return {
        "query":             partial(sf_tools.soql_query, user_id),
        "tooling_query":     partial(sf_tools.tooling_query, user_id),
        "describe_object":   partial(sf_tools.describe_object, user_id),
        "metadata_retrieve": _metadata_retrieve,
        "get_record":        partial(sf_tools.get_record, user_id),
        "create_record":     _create_record,
        "update_record":     _update_record,
        "delete_record":     partial(sf_tools.delete_record, user_id),
    }


# ── Agentic loop ──────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a Salesforce assistant with access to the user's Salesforce org.
Use the available tools to answer questions and perform operations.
Always be concise and return structured data when helpful.
When querying records, limit results to a reasonable number (e.g. LIMIT 10) unless the user asks for more.
"""


async def process_query(user_id: str, message: str, timezone: str = "UTC") -> dict[str, Any]:
    """
    Run the Claude agentic loop for a plain-English Salesforce query.
    Returns the final text response and a list of tool calls made.
    """
    client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    dispatch = _build_dispatch(user_id)

    messages = [{"role": "user", "content": message}]
    tool_calls_made: list[str] = []

    logger.info("nlp.query.start", user_id=user_id, message=message[:80])

    for iteration in range(10):
        response = await client.messages.create(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOL_DEFINITIONS,
            messages=messages,
        )

        # Append assistant response to conversation
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            # Claude is done — extract final text
            final_text = next(
                (block.text for block in response.content if hasattr(block, "text")),
                "No response generated.",
            )
            logger.info("nlp.query.done", user_id=user_id, iterations=iteration + 1, tools=tool_calls_made)
            return {
                "answer": final_text,
                "tool_calls_made": tool_calls_made,
                "iterations": iteration + 1,
            }

        # Execute all tool calls in this response
        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue

            tool_name = block.name
            tool_calls_made.append(tool_name)
            logger.info("nlp.tool_call", user_id=user_id, tool=tool_name)

            try:
                fn = dispatch[tool_name]
                result = await fn(**block.input)
                content = json.dumps(result, default=str)
            except Exception as exc:
                logger.error("nlp.tool_error", tool=tool_name, error=str(exc))
                content = json.dumps({"error": str(exc)})

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": content,
            })

        messages.append({"role": "user", "content": tool_results})

    return {
        "answer": "Reached maximum iterations without a final response.",
        "tool_calls_made": tool_calls_made,
        "iterations": 10,
    }
