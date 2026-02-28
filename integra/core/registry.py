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
