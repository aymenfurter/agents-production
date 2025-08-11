import os
import json
import argparse
from pathlib import Path
from glob import glob
from typing import Dict, Any, Optional

from dotenv import load_dotenv
from azure.ai.contentsafety import ContentSafetyClient
from azure.ai.contentsafety.models import AnalyzeTextOptions
from azure.core.credentials import AzureKeyCredential
from .client import AzureMLClient

load_dotenv()

class SafetyThresholds:
    """Define safety thresholds for content analysis."""
    THRESHOLD = 2

class DirectInferenceAgent:
    """Direct inference agent for processing ContosoCare warranty claims."""
    
    def __init__(self, endpoint: str, use_guardrails: bool = False):
        """Initialize the direct inference agent.
        
        Args:
            endpoint: Azure ML endpoint URL
            use_guardrails: Whether to enable content safety guardrails
        """
        self.client = AzureMLClient(endpoint)
        self.use_guardrails = use_guardrails
        self.content_safety_client = None
        
        if self.use_guardrails:
            self._initialize_content_safety()
    
    def _initialize_content_safety(self):
        """Initialize content safety client for guardrails."""
        content_safety_endpoint = os.getenv("CONTENT_SAFETY_ENDPOINT")
        content_safety_key = os.getenv("CONTENT_SAFETY_KEY")
        
        if not content_safety_endpoint or not content_safety_key:
            print("Warning: Content safety credentials not found. Guardrails disabled.")
            self.use_guardrails = False
            return
        
        try:
            self.content_safety_client = ContentSafetyClient(
                endpoint=content_safety_endpoint,
                credential=AzureKeyCredential(content_safety_key)
            )
        except Exception as e:
            print(f"Warning: Failed to initialize content safety client: {e}")
            self.use_guardrails = False
    
    def analyze_content_safety(self, text: str) -> Dict[str, Any]:
        """Analyze text for content safety violations."""
        if not self.content_safety_client:
            return {'safe': True, 'violations': []}
        
        try:
            response = self.content_safety_client.analyze_text(
                AnalyzeTextOptions(text=text)
            )
            
            categories = {
                item.category.lower(): item.severity 
                for item in response.categories_analysis
            }
            
            violations = []
            safe = True
            
            for cat, sev in categories.items():
                if sev >= SafetyThresholds.THRESHOLD:
                    safe = False
                    violations.append(f"{cat}: {sev}")
            
            return {'safe': safe, 'violations': violations}
            
        except Exception as e:
            print(f"Content safety analysis failed: {e}")
            return {'safe': False, 'violations': ['Analysis failed']}
    
    def process(self, user_message: str) -> Dict[str, Any]:
        """Process a user message and return mock tool calls and response."""
        # Input safety check if guardrails enabled
        if self.use_guardrails:
            input_safety = self.analyze_content_safety(user_message)
            if not input_safety['safe']:
                safety_response = "I cannot process this request due to safety concerns."
                mock_tool_calls = [
                    {
                        "name": "message_to_user",
                        "arguments": {"message": safety_response},
                        "output": {"action": "message_to_user", "message": safety_response, "status": "safety_blocked"}
                    }
                ]
                return {
                    "message": safety_response,
                    "actual_tool_calls": mock_tool_calls
                }
        
        # Get model response directly
        try:
            response = self.client.predict(user_message)
        except Exception as e:
            error_response = "I encountered an error processing your request."
            mock_tool_calls = [
                {
                    "name": "message_to_user",
                    "arguments": {"message": error_response},
                    "output": {"action": "message_to_user", "message": error_response, "status": "error"}
                }
            ]
            return {
                "message": error_response,
                "actual_tool_calls": mock_tool_calls
            }
        
        # Clean up response
        response = response.strip()
        
        # Output safety check if guardrails enabled
        if self.use_guardrails and response:
            output_safety = self.analyze_content_safety(response)
            if not output_safety['safe']:
                safety_response = "I cannot provide this response due to safety concerns."
                mock_tool_calls = [
                    {
                        "name": "message_to_user",
                        "arguments": {"message": safety_response},
                        "output": {"action": "message_to_user", "message": safety_response, "status": "safety_blocked"}
                    }
                ]
                return {
                    "message": safety_response,
                    "actual_tool_calls": mock_tool_calls
                }
        
        # Create mock tool calls to match expected format
        mock_tool_calls = [
            {
                "name": "message_to_user",
                "arguments": {"message": response},
                "output": {"action": "message_to_user", "message": response, "status": "waiting_for_response"}
            }
        ]
        
        return {
            "message": response,
            "actual_tool_calls": mock_tool_calls
        }


def run_interactive_mode(endpoint: str) -> int:
    """Run the agent in interactive chat mode."""
    print("=" * 60)
    print("ContosoCare System (Direct Inference)")
    print("=" * 60)
    
    agent = DirectInferenceAgent(endpoint)
    print("Agent: What happened to your device?")
    
    try:
        while True:
            user_input = input("\nYou: ").strip()
            
            # Skip empty input
            if not user_input:
                continue
            
            # Check for exit commands
            if user_input.lower() in ("quit", "exit"):
                break
            
            # Process the message
            print("[Processing...]")
            try:
                result = agent.process(user_input)
                
                # Display response
                if result.get("message"):
                    print(f"\nAgent: {result['message']}")
                
                # Show tool calls for debugging
                for call in result.get("actual_tool_calls", []):
                    print(f"[TOOL] {call['name']} {call['arguments']}")
                    
            except Exception as e:
                print(f"Error: {e}")
                
    except KeyboardInterrupt:
        print("\n\nGoodbye!")
    
    return 0


def run_evaluation_mode(endpoint: str, output_file: str) -> int:
    """Run the agent in evaluation mode against test cases."""
    # Use relative path from current file location
    current_dir = Path(__file__).resolve().parent.parent.parent
    eval_path = current_dir / "quality_evals" / "scenarios"
    
    if eval_path.is_file():
        eval_files = [str(eval_path)]
    else:
        eval_files = sorted(glob(str(eval_path / "*.json")))
    
    if not eval_files:
        print("No evaluation files found")
        return 2
    
    # Remove old eval results file if it exists
    output_path = Path(output_file)
    if output_path.exists():
        output_path.unlink()
        print(f"Removed old evaluation results: {output_file}")
    
    print(f"Running evaluation with direct inference...")
    
    # Create agent
    agent = DirectInferenceAgent(endpoint)
    
    with output_path.open("w") as output:
        for i, eval_file in enumerate(eval_files, 1):
            print(f"Processing [{i}/{len(eval_files)}]: {Path(eval_file).name}")
            
            # Load test scenario
            with open(eval_file) as f:
                scenario = json.load(f)
            
            # Get conversation history
            conversation = scenario.get("conversation", [])
            
            # Find the last user message
            last_user_message = None
            for message in reversed(conversation):
                if message.get("role") == "user":
                    last_user_message = message.get("content")
                    break
            
            # Use last user message or default
            if last_user_message:
                result = agent.process(last_user_message)
            else:
                result = agent.process("Please help me with my warranty claim.")
            
            eval_result = {
                "id": scenario.get("id"),
                "description": scenario.get("description"),
                "model": "direct_inference",
                "conversation": conversation,
                "expected_tool_calls": scenario.get("expected_tool_calls", []),
                "actual_tool_calls": result["actual_tool_calls"]
            }
            
            output.write(json.dumps(eval_result) + "\n")
    
    print(f"Wrote {len(eval_files)} results to {output_file}")
    return 0


def main():
    """Main entry point for the direct inference agent."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="ContosoCare Direct Inference Agent")
    parser.add_argument(
        "-i", "--interactive",
        action="store_true",
        help="Run in interactive chat mode"
    )
    parser.add_argument(
        "-o", "--output",
        default="eval_results_gpt-2.jsonl",
        help="Output file for evaluation results"
    )
    args = parser.parse_args()
    
    # Get configuration from environment
    endpoint = os.getenv("AZURE_ML_ENDPOINT", "").strip('"\'')
    
    # Validate configuration
    if not endpoint:
        print("ERROR: Please set AZURE_ML_ENDPOINT in .env file")
        return 1
    
    if args.interactive:
        return run_interactive_mode(endpoint)
    else:
        return run_evaluation_mode(endpoint, args.output)