import json
import time
from typing import Dict, List, Optional, Union
from azure.ai.agents.models import FunctionTool


def update_internal_scratchpad(
    reasoning: str,
    confidence_level: str = "medium",
    red_flags: Optional[Union[List, str]] = None
) -> str:
    """Update the agent's internal scratchpad for tracking thought process.
    
    This should be called FIRST before any other action to help the agent
    organize its thoughts and plan next steps.
    
    Args:
        reasoning: Current reasoning about the case
        confidence_level: How confident the agent is ("low", "medium", "high")
        red_flags: Any concerning aspects of the claim
        
    Returns:
        JSON string with the scratchpad update
    """
    def normalize_input(value, as_list=False):
        """Normalize input to consistent format."""
        if not value:
            return [] if as_list else {}
        
        if as_list:
            return [value] if isinstance(value, str) else value
        else:
            return {"notes": value} if isinstance(value, str) else value
    
    scratchpad_data = {
        "reasoning": reasoning,
        "confidence_level": confidence_level,
        "red_flags": normalize_input(red_flags, as_list=True)
    }
    
    return json.dumps(scratchpad_data)


def message_to_user(message: str) -> str:
    """Ask the customer a follow-up message to gather more information.
    
    Args:
        message: The message to ask the customer
                 
    Returns:
        JSON string with the message details
    """
    message_data = {
        "action": "message_to_user",
        "message": message,
        "status": "waiting_for_response"
    }
    
    return json.dumps(message_data)


def make_warranty_decision_with_log(
    decision: str,
    reason: str,
    deductible_amount: Optional[float] = None,
    customer_info: Optional[Dict] = None,
    device_info: Optional[Dict] = None,
    incident_info: Optional[Dict] = None,
    coverage_info: Optional[Dict] = None,
    summary: Optional[str] = None
) -> str:
    """Make a warranty coverage decision and log claim details in one action.
    
    Args:
        decision: Either "covered" or "needs_human_review"
                 NEVER use "not_covered" or "denied"
        reason: Explanation for the decision
        deductible_amount: For covered claims, any deductible amount
        customer_info: Customer details (name, email, phone, etc.)
        device_info: Device details (model, serial, purchase date, etc.)
        incident_info: Incident details (description, date, cause, etc.)
        coverage_info: Coverage details (plan type, status, etc.)
        summary: Brief summary if only partial information available
        
    Returns:
        JSON string with the decision and logged details
    """
    # Ensure we never deny claims directly - always send to human review
    if decision not in ["covered", "needs_human_review"]:
        decision = "needs_human_review"
    
    # Explicitly convert "not_covered" to human review
    if decision == "not_covered":
        decision = "needs_human_review"
    
    result_data = {
        "action": "warranty_decision_with_log",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "decision": decision,
        "reason": reason,
        "status": "decision_logged"
    }
    
    # Add service details only for covered claims
    if decision == "covered":
        if deductible_amount is not None:
            result_data["deductible_amount"] = deductible_amount
    
    # Add any provided claim information
    info_fields = [
        ("customer_info", customer_info),
        ("device_info", device_info),
        ("incident_info", incident_info),
        ("coverage_info", coverage_info),
        ("summary", summary)
    ]
    
    for field_name, field_value in info_fields:
        if field_value:
            result_data[field_name] = field_value
    
    return json.dumps(result_data)


# Export all tool functions for the agent
user_functions = {
    update_internal_scratchpad,
    message_to_user,
    make_warranty_decision_with_log
}


def get_tool_definitions():
    """Get tool definitions formatted for Azure AI Agents.
    
    Returns:
        Tool definitions compatible with AIProjectClient agents
    """
    return FunctionTool(functions=user_functions).definitions