from typing import Any, Dict, List, Optional

def extract_message_from_tool_calls(tool_calls: List[Dict[str, Any]], tool_name: str = "message_to_user") -> Optional[str]:
    """Return the last 'message' argument from the given tool name (if present)."""
    msg = None
    for call in tool_calls or []:
        if call.get("name") == tool_name:
            args = call.get("arguments") or {}
            if isinstance(args, dict):
                msg = args.get("message", "")
    return msg


def extract_tool_names_from_calls(tool_calls: List[Dict[str, Any]]) -> str:
    """Return a comma-separated list of tool names from tool_calls."""
    return ", ".join([c["name"] for c in tool_calls or [] if c.get("name")])


def tool_definition(tool_name: str) -> Dict[str, Any]:
    """Return a schema/definition for a known tool (fallback to a generic definition)."""
    if tool_name == "update_internal_scratchpad":
        return {
            "name": "update_internal_scratchpad",
            "type": "function",
            "description": "Update the agent's internal scratchpad for tracking thought process.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reasoning": {"type": "string", "description": "Current reasoning about the case"},
                    "confidence_level": {"type": "string", "description": "How confident the agent is"},
                    "red_flags": {"type": "string", "description": "Any concerning aspects"},
                },
                "required": ["reasoning"],
            },
        }
    if tool_name == "message_to_user":
        return {
            "name": "message_to_user",
            "type": "function",
            "description": "Ask the customer a follow-up message to gather more information.",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {"type": "string", "description": "The message to ask the customer"},
                },
                "required": ["message"],
            },
        }
    if tool_name == "make_warranty_decision_with_log":
        return {
            "name": "make_warranty_decision_with_log",
            "type": "function",
            "description": "Make a warranty coverage decision and log claim details.",
            "parameters": {
                "type": "object",
                "properties": {
                    "decision": {"type": "string", "description": "Either 'covered' or 'needs_human_review'"},
                    "reason": {"type": "string", "description": "Explanation for the decision"},
                },
                "required": ["decision", "reason"],
            },
        }
    return {
        "name": tool_name,
        "type": "function",
        "description": f"Tool function: {tool_name}",
        "parameters": {"type": "object", "properties": {}, "required": []},
    }


def build_tool_definitions(tool_calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Build distinct tool definitions based on tool calls."""
    tool_names = {c.get("name") for c in (tool_calls or []) if c.get("name")}
    return [tool_definition(n) for n in tool_names]


def format_tool_calls(tool_calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Normalize tool calls into the structure evaluators expect."""
    formatted: List[Dict[str, Any]] = []
    for i, c in enumerate(tool_calls or []):
        formatted.append(
            {
                "type": "tool_call",
                "tool_call_id": f"call_{i}_{c.get('name', 'unknown')}",
                "name": c.get("name"),
                "arguments": c.get("arguments", {}),
            }
        )
    return formatted
