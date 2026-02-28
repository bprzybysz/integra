"""Claude agentic conversation loop with tool dispatch."""

import logging

import anthropic

from integra.core.config import settings
from integra.core.registry import ConfirmFn, dispatch_tool, get_tool_schemas

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 15

SYSTEM_PROMPT = (
    "You are Integra, a personal AI orchestrator. You help the user manage health data, "
    "habits, medications, and daily routines. You have access to tools for interacting "
    "with the user via Telegram and querying a secure data lake. Always be concise, "
    "accurate, and privacy-conscious. Never reveal raw encryption keys or internal paths."
)


async def run_conversation(
    user_message: str,
    conversation_history: list[anthropic.types.MessageParam] | None = None,
    confirm_fn: ConfirmFn | None = None,
) -> str:
    """Run an agentic conversation loop with Claude.

    Args:
        user_message: The user's input message.
        conversation_history: Optional prior messages for multi-turn context.
        confirm_fn: Async callback for HIL tool confirmation.

    Returns:
        The final text response from Claude.
    """
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    messages: list[anthropic.types.MessageParam] = list(conversation_history or [])
    messages.append({"role": "user", "content": user_message})

    tools = get_tool_schemas()

    for round_num in range(1, MAX_TOOL_ROUNDS + 1):
        logger.info("Orchestrator round %d/%d", round_num, MAX_TOOL_ROUNDS)

        response = await client.messages.create(
            model=settings.anthropic_model,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=tools,  # type: ignore[arg-type]
            messages=messages,
        )

        # Collect text and tool_use blocks
        tool_use_blocks: list[anthropic.types.ToolUseBlock] = []
        text_parts: list[str] = []

        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_use_blocks.append(block)

        # If no tool use, we're done
        if not tool_use_blocks:
            return "\n".join(text_parts) if text_parts else ""

        # Append assistant message with all content blocks
        messages.append({"role": "assistant", "content": response.content})

        # Process each tool call
        tool_results: list[anthropic.types.ToolResultBlockParam] = []
        for tool_block in tool_use_blocks:
            result = await dispatch_tool(
                name=tool_block.name,
                input_data=dict(tool_block.input) if isinstance(tool_block.input, dict) else {},
                confirm_fn=confirm_fn,
            )
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tool_block.id,
                    "content": result,
                }
            )

        messages.append({"role": "user", "content": tool_results})

    # Exceeded max rounds
    logger.warning("Max tool rounds (%d) exceeded", MAX_TOOL_ROUNDS)
    return "I've reached the maximum number of processing steps. Please try a simpler request."
