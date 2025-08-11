import json
import time
from typing import Dict, List, Optional, Union
from azure.ai.agents.models import FunctionTool


def update_internal_scratchpad(
    reasoning: str,
    confidence_level: str = "medium",
    red_flags: Optional[Union[List, str]] = None
) -> str:
    def normalize_input(value, as_list=False):
        if not value:
            return [] if as_list else {}
        return [value] if isinstance(value, str) and as_list else value
    
    return json.dumps({
        "reasoning": reasoning,
        "confidence_level": confidence_level,
        "red_flags": normalize_input(red_flags, as_list=True)
    })


def message_to_user(message: str) -> str:
    return json.dumps({
        "action": "message_to_user",
        "message": message,
        "status": "waiting_for_response"
    })


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
    if decision not in ["covered", "needs_human_review"]:
        decision = "needs_human_review"
    
    if decision == "not_covered":
        decision = "needs_human_review"
    
    result_data = {
        "action": "warranty_decision_with_log",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "decision": decision,
        "reason": reason,
        "status": "decision_logged"
    }
    
    if decision == "covered" and deductible_amount is not None:
        result_data["deductible_amount"] = deductible_amount
    
    for field_name, field_value in [("customer_info", customer_info), ("device_info", device_info),
                                   ("incident_info", incident_info), ("coverage_info", coverage_info),
                                   ("summary", summary)]:
        if field_value:
            result_data[field_name] = field_value
    
    return json.dumps(result_data)


user_functions = {
    update_internal_scratchpad,
    message_to_user,
    make_warranty_decision_with_log
}


def get_tool_definitions():
    return FunctionTool(functions=user_functions).definitions