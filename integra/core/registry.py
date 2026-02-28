"""Tool registry with HIL flags and async dispatch."""

import logging
from collections.abc import Awaitable, Callable
from typing import TypedDict

logger = logging.getLogger(__name__)


class ToolSchema(TypedDict):
    """Claude API tool definition."""

    name: str
    description: str
    input_schema: dict[str, object]


class ToolDef(TypedDict):
    """Registry entry for a single tool."""

    handler: Callable[..., Awaitable[str]]
    requires_confirmation: bool
    schema: ToolSchema


# Confirm function signature: receives tool name + input, returns "APPROVED" or "DENIED"
ConfirmFn = Callable[[str, dict[str, object]], Awaitable[str]]


async def _placeholder_handler(**_kwargs: object) -> str:
    """Placeholder until real handlers are wired during app init."""
    return "Handler not yet configured."


TOOL_REGISTRY: dict[str, ToolDef] = {
    "ask_user_confirmation": {
        "handler": _placeholder_handler,
        "requires_confirmation": False,
        "schema": {
            "name": "ask_user_confirmation",
            "description": ("Ask the user a yes/no confirmation question via Telegram. Returns the user's response."),
            "input_schema": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "The question to ask the user.",
                    },
                },
                "required": ["question"],
            },
        },
    },
    "notify_user": {
        "handler": _placeholder_handler,
        "requires_confirmation": False,
        "schema": {
            "name": "notify_user",
            "description": "Send a notification message to the user via Telegram.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "The message to send.",
                    },
                },
                "required": ["message"],
            },
        },
    },
    "collect_supplement_stack": {
        "handler": _placeholder_handler,
        "requires_confirmation": False,
        "schema": {
            "name": "collect_supplement_stack",
            "description": ("Add a supplement or medication to the user's stack. Stores encrypted in data lake."),
            "input_schema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Supplement/medication name."},
                    "dose": {"type": "string", "description": "Dose amount (e.g. '5000')."},
                    "unit": {"type": "string", "description": "Unit (e.g. 'mg', 'IU')."},
                    "frequency": {
                        "type": "string",
                        "description": "Dosing frequency: daily, twice_daily, weekly, as_needed.",
                        "enum": ["daily", "twice_daily", "weekly", "as_needed"],
                    },
                    "time_of_day": {"type": "string", "description": "When taken (e.g. 'morning')."},
                    "category": {
                        "type": "string",
                        "description": "Category: supplement, medication, or addiction-therapy.",
                        "enum": ["supplement", "medication", "addiction-therapy"],
                    },
                    "notes": {"type": "string", "description": "Optional notes."},
                },
                "required": ["name", "dose", "unit"],
            },
        },
    },
    "log_drug_intake": {
        "handler": _placeholder_handler,
        "requires_confirmation": False,
        "schema": {
            "name": "log_drug_intake",
            "description": (
                "Log a single drug or substance intake event with timestamp. "
                "Supports addiction-therapy tracking with daily quotas."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "substance": {"type": "string", "description": "Substance name."},
                    "amount": {"type": "string", "description": "Amount taken."},
                    "unit": {"type": "string", "description": "Unit (e.g. 'mg')."},
                    "category": {
                        "type": "string",
                        "description": "Category: supplement, medication, or addiction-therapy.",
                        "enum": ["supplement", "medication", "addiction-therapy"],
                    },
                    "daily_quota": {
                        "type": "string",
                        "description": "Target max per day (for addiction-therapy).",
                    },
                    "notes": {"type": "string", "description": "Optional notes."},
                },
                "required": ["substance", "amount", "unit"],
            },
        },
    },
    "log_meal": {
        "handler": _placeholder_handler,
        "requires_confirmation": False,
        "schema": {
            "name": "log_meal",
            "description": "Log a dietary intake entry (meal or snack).",
            "input_schema": {
                "type": "object",
                "properties": {
                    "meal_type": {
                        "type": "string",
                        "description": "Type of meal.",
                        "enum": ["breakfast", "lunch", "dinner", "snack"],
                    },
                    "items": {"type": "string", "description": "Food items consumed."},
                    "notes": {"type": "string", "description": "Optional notes (portions, etc)."},
                },
                "required": ["meal_type", "items"],
            },
        },
    },
    "query_health_data": {
        "handler": _placeholder_handler,
        "requires_confirmation": False,
        "schema": {
            "name": "query_health_data",
            "description": (
                "Query health data from the encrypted data lake. Supports supplements, intake, and dietary categories."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "Data category to query.",
                        "enum": ["supplements", "intake", "dietary"],
                    },
                    "filters": {
                        "type": "object",
                        "description": "Optional key-value filters to match records.",
                    },
                },
                "required": ["category"],
            },
        },
    },
    "ingest_cc_history": {
        "handler": _placeholder_handler,
        "requires_confirmation": True,
        "schema": {
            "name": "ingest_cc_history",
            "description": (
                "Ingest Claude Code session history from a zip archive into "
                "the encrypted data lake. Requires user confirmation."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "archive_path": {
                        "type": "string",
                        "description": "Path to the zip archive containing CC session data.",
                    },
                },
                "required": ["archive_path"],
            },
        },
    },
    "analyze_cc_productivity": {
        "handler": _placeholder_handler,
        "requires_confirmation": False,
        "schema": {
            "name": "analyze_cc_productivity",
            "description": (
                "Cross-reference Claude Code session data with drug intake records to analyze productivity patterns."
            ),
            "input_schema": {
                "type": "object",
                "properties": {},
            },
        },
    },
}


def get_tool_schemas() -> list[ToolSchema]:
    """Return list of Claude API tool definitions from the registry."""
    return [tool["schema"] for tool in TOOL_REGISTRY.values()]


def register_handler(tool_name: str, handler: Callable[..., Awaitable[str]]) -> None:
    """Wire a real handler into an existing registry entry."""
    if tool_name not in TOOL_REGISTRY:
        msg = f"Unknown tool: {tool_name}"
        raise KeyError(msg)
    TOOL_REGISTRY[tool_name]["handler"] = handler


async def dispatch_tool(
    name: str,
    input_data: dict[str, object],
    confirm_fn: ConfirmFn | None = None,
) -> str:
    """Look up and execute a tool, enforcing HIL confirmation if required.

    Args:
        name: Tool name from the registry.
        input_data: Arguments for the tool handler.
        confirm_fn: Async callback for HIL approval. Required when a tool
            has requires_confirmation=True.

    Returns:
        The tool's string result, or an error message.
    """
    if name not in TOOL_REGISTRY:
        logger.error("Unknown tool requested: %s", name)
        return f"Error: unknown tool '{name}'"

    tool = TOOL_REGISTRY[name]

    if tool["requires_confirmation"]:
        if confirm_fn is None:
            logger.warning("Tool %s requires confirmation but no confirm_fn provided", name)
            return f"Error: tool '{name}' requires confirmation but no confirm function available"

        verdict = await confirm_fn(name, input_data)
        if verdict != "APPROVED":
            logger.info("Tool %s was denied by user", name)
            return f"Tool '{name}' was denied by user."

    try:
        result = await tool["handler"](**input_data)
    except Exception:
        logger.exception("Error executing tool %s", name)
        return f"Error: tool '{name}' execution failed"

    return result
