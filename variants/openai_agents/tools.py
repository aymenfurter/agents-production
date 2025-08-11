import json
import time
from typing import Optional
from agents import function_tool


@function_tool
def update_internal_scratchpad(
    reasoning: str,
    confidence_level: str = "medium",
    red_flags: Optional[str] = None
) -> str:
    scratchpad_data = {
        "reasoning": reasoning,
        "confidence_level": confidence_level,
        "red_flags": [red_flags] if red_flags else []
    }
    
    return json.dumps(scratchpad_data)


@function_tool
def message_to_user(message: str) -> str:
    message_data = {
        "message": message
    }
    
    return json.dumps(message_data)


@function_tool
def make_warranty_decision_with_log(
    decision: str,
    reason: str,
    deductible_amount: Optional[float] = None,
    customer_info: Optional[str] = None,
    device_info: Optional[str] = None,
    incident_info: Optional[str] = None,
    coverage_info: Optional[str] = None,
    summary: Optional[str] = None
) -> str:
    if decision not in ["covered", "needs_human_review"]:
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
    
    info_fields = [
        ("customer_info", customer_info),
        ("device_info", device_info),
        ("incident_info", incident_info),
        ("coverage_info", coverage_info),
        ("summary", summary)
    ]
    
    for field_name, field_value in info_fields:
        if field_value:
            result_data[field_name] = json.loads(field_value) if isinstance(field_value, str) else field_value
    
    return json.dumps(result_data)