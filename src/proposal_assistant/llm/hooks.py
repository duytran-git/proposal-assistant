"""Security hooks for the Claude Agent SDK.

Provides pre/post-tool-use hooks for audit logging and blocking
dangerous operations, following CLAUDE.md §5.7.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from claude_agent_sdk import HookContext, HookMatcher

logger = logging.getLogger(__name__)

# Patterns that must never execute (CLAUDE.md §5.7)
_DANGEROUS_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"rm\s+-rf\b"),
    re.compile(r"\bsudo\b"),
    re.compile(r"chmod\s+777\b"),
    re.compile(r"curl\s+.*\|\s*sh"),
]


async def log_tool_usage(
    input_data: dict[str, Any],
    tool_use_id: str | None,
    context: HookContext,
) -> dict[str, Any]:
    """Audit-log every MCP tool invocation.

    Logs tool name and tool_use_id only — never secrets or full arguments
    (CLAUDE.md §15 rule 3).
    """
    event = input_data.get("hook_event_name", "unknown")
    tool_name = input_data.get("tool_name", "unknown")
    logger.info(
        "Hook [%s] tool=%s tool_use_id=%s",
        event,
        tool_name,
        tool_use_id or "n/a",
    )
    return {}


async def block_dangerous_operations(
    input_data: dict[str, Any],
    tool_use_id: str | None,
    context: HookContext,
) -> dict[str, Any]:
    """Deny tool calls that contain dangerous shell commands.

    Only inspects PreToolUse events. Checks the ``command`` field of
    tool_input against a list of forbidden patterns (rm -rf, sudo,
    chmod 777, curl | sh).
    """
    if input_data.get("hook_event_name") != "PreToolUse":
        return {}

    command = input_data.get("tool_input", {}).get("command", "")
    if not command:
        return {}

    for pattern in _DANGEROUS_PATTERNS:
        if pattern.search(command):
            reason = f"Blocked dangerous command matching /{pattern.pattern}/: {command!r}"
            logger.warning("SECURITY: %s", reason)
            return {
                "hookSpecificOutput": {
                    "hookEventName": input_data["hook_event_name"],
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }

    return {}


def get_security_hooks() -> dict[str, list[HookMatcher]]:
    """Return the hook configuration dict for ClaudeAgentOptions.

    Wire this into the agent options:
        ClaudeAgentOptions(..., hooks=get_security_hooks())
    """
    return {
        "PreToolUse": [
            HookMatcher(hooks=[log_tool_usage, block_dangerous_operations]),
        ],
        "PostToolUse": [
            HookMatcher(hooks=[log_tool_usage]),
        ],
    }
