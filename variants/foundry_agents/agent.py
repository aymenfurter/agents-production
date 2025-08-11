import os
import json
import time
import argparse
from pathlib import Path
from glob import glob
from typing import Dict, Any

from dotenv import load_dotenv
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential

from .tools import *
from .prompt import build_agent_instructions


# Load environment variables
load_dotenv()


class ContosoCareAgent:
    """AI agent for processing ContosoCare warranty claims."""
    
    def __init__(self, endpoint: str, model: str):
        """Initialize the ContosoCare agent with Azure AI services.
        
        Args:
            endpoint: Azure AI project endpoint
            model: Model deployment name (e.g., 'gpt-4o')
        """
        # Connect to Azure AI Project
        self.client = AIProjectClient(
            endpoint=endpoint, 
            credential=DefaultAzureCredential()
        )
        
        # Load company handbook for agent context
        handbook_path = Path(__file__).parent.parent.parent / "contoso-handbook.md"
        with open(handbook_path) as file:
            handbook_content = file.read()
        
        # Create the AI agent with instructions and tools
        self.agent = self.client.agents.create_agent(
            model=model,
            name="ContosoCare",
            instructions=build_agent_instructions(handbook_content),
            tools=get_tool_definitions()
        )
        
        # Create a conversation thread
        self.thread = self.client.agents.threads.create()
        
        # Map tool names to their implementation functions
        self._tool_functions = {
            "update_internal_scratchpad": update_internal_scratchpad,
            "message_to_user": message_to_user,
            "make_warranty_decision_with_log": make_warranty_decision_with_log
        }
    
    def __del__(self):
        """Clean up resources when the agent is destroyed."""
        self.close_session()
    
    def close_session(self):
        """Clean up Azure AI resources."""
        try:
            if hasattr(self, 'thread') and self.thread:
                self.client.agents.threads.delete(thread_id=self.thread.id)
                self.thread = None
            if hasattr(self, 'agent') and self.agent:
                self.client.agents.delete_agent(agent_id=self.agent.id)
                self.agent = None
        except Exception as e:
            print(f"Warning: Error during cleanup: {e}")
    
    def process(self, user_message: str) -> Dict[str, Any]:
        """Process a user message and return tool calls and last user-facing message (if any)."""
        self.client.agents.messages.create(
            thread_id=self.thread.id,
            role="user",
            content=user_message
        )
        run = self.client.agents.runs.create(
            thread_id=self.thread.id,
            agent_id=self.agent.id
        )
        captured_tool_calls = []
        while run.status in ("queued", "in_progress", "requires_action"):
            time.sleep(1)
            run = self.client.agents.runs.get(
                thread_id=self.thread.id,
                run_id=run.id
            )
            if run.status == "requires_action":
                tool_outputs = self._execute_tool_calls(
                    run.required_action.submit_tool_outputs.tool_calls,
                    captured_tool_calls
                )
                self.client.agents.runs.submit_tool_outputs(
                    thread_id=self.thread.id,
                    run_id=run.id,
                    tool_outputs=tool_outputs
                )
        # Derive last message_to_user text if present
        last_message = None
        for call in captured_tool_calls:
            if call["name"] == "message_to_user":
                last_message = call["output"].get("message")
        return {
            "message": last_message,
            "actual_tool_calls": captured_tool_calls
        }
    
    def _execute_tool_calls(self, tool_calls: list, captured_calls: list) -> list:
        """Execute requested tool calls and capture results.
        
        Args:
            tool_calls: List of tool calls requested by the agent
            captured_calls: List to append captured call details to
            
        Returns:
            List of tool outputs to submit back to the agent
        """
        tool_outputs = []
        
        for tool_call in tool_calls:
            # Extract tool name and arguments
            tool_name = tool_call.function.name
            tool_args = json.loads(tool_call.function.arguments)
            
            # Execute the tool function
            tool_function = self._tool_functions.get(
                tool_name,
                lambda **x: {"error": f"Unknown tool: {tool_name}"}
            )
            result = tool_function(**tool_args)
            
            # Convert result to dictionary if needed
            if isinstance(result, str):
                result_dict = json.loads(result)
            else:
                result_dict = result
            
            # Capture for debugging/evaluation
            captured_calls.append({
                "name": tool_name,
                "arguments": tool_args,
                "output": result_dict
            })
            
            # Prepare output for agent
            tool_outputs.append({
                "tool_call_id": tool_call.id,
                "output": json.dumps(result_dict) if isinstance(result, dict) else result
            })
        
        return tool_outputs
    
    def clear_conversation(self) -> None:
        """Clear the conversation history by creating a new thread."""
        try:
            # Delete the old thread
            if hasattr(self, 'thread') and self.thread:
                self.client.agents.threads.delete(thread_id=self.thread.id)
            
            # Create a new thread
            self.thread = self.client.agents.threads.create()
            
        except Exception as e:
            print(f"Warning: Error clearing conversation: {e}")
            # Fallback: try to create a new thread even if deletion failed
            try:
                self.thread = self.client.agents.threads.create()
            except Exception as fallback_error:
                print(f"Error: Could not create new thread: {fallback_error}")


def run_interactive_mode(endpoint: str, model: str) -> int:
    """Run the agent in interactive chat mode."""
    print("=" * 60)
    print("ContosoCare System")
    print("=" * 60)
    
    agent = ContosoCareAgent(endpoint, model)
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
            result = agent.process(user_input)
            
            # Display response
            if result.get("message"):
                print(f"\nAgent: {result['message']}")
            
            # Always show raw tool calls
            for call in result.get("actual_tool_calls", []):
                print(f"[TOOL] {call['name']} {call['arguments']}")
                
    except KeyboardInterrupt:
        print("\n\nGoodbye!")
    
    return 0


def run_evaluation_mode(endpoint: str, models: list, output_pattern: str) -> int:
    """Run the agent in evaluation mode against test cases with multiple models."""
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
    
    # Process each model
    for model in models:
        # Create model-specific output file
        base_name = Path(output_pattern).stem
        output_file = f"{base_name}_{model.replace('.', '_')}.jsonl"
        
        # Remove old eval results file if it exists
        output_path = Path(output_file)
        if output_path.exists():
            output_path.unlink()
            print(f"Removed old evaluation results: {output_file}")
        
        print(f"Evaluating with model: {model}")
        
        # Create agent for this model
        agent = ContosoCareAgent(endpoint, model)
        
        with Path(output_file).open("w") as output:
            for i, eval_file in enumerate(eval_files, 1):
                print(f"Processing [{i}/{len(eval_files)}]: {Path(eval_file).name}")
                # Load test scenario
                with open(eval_file) as f:
                    scenario = json.load(f)
                
                # Create fresh thread for this scenario
                agent.thread = agent.client.agents.threads.create()
                
                # Load conversation history if provided
                conversation = scenario.get("conversation", [])
                if conversation:
                    for message in conversation:
                        agent.client.agents.messages.create(
                            thread_id=agent.thread.id,
                            role=message["role"],
                            content=message["content"]
                        )
                    
                    # Process the conversation
                    result = agent.process("Continue.")
                    
                    eval_result = {
                        "id": scenario.get("id"),
                        "description": scenario.get("description"),
                        "model": model,  # Add model info to results
                        "conversation": conversation,
                        "expected_tool_calls": scenario.get("expected_tool_calls", []),
                        "actual_tool_calls": result["actual_tool_calls"]
                    }
                    
                    output.write(json.dumps(eval_result) + "\n")
        
        print(f"Wrote {len(eval_files)} results to {output_file}")
        
        # Clean up agent resources
        del agent
    
    return 0


def main():
    """Main entry point for the ContosoCare agent."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="ContosoCare Warranty Claim Agent")
    parser.add_argument(
        "-i", "--interactive",
        action="store_true",
        help="Run in interactive chat mode"
    )
    parser.add_argument(
        "-o", "--output",
        default="eval_results",
        help="Output file pattern for evaluation results (model name will be appended)"
    )
    parser.add_argument(
        "--models",
        nargs="+",
        help="Model deployment names to evaluate (space-separated)"
    )
    args = parser.parse_args()
    
    # Get configuration from environment
    endpoint = os.getenv("PROJECT_ENDPOINT", "").strip('"\'')
    default_model = os.getenv("MODEL_DEPLOYMENT_NAME", "gpt-4o").strip('"\'')
    
    # Validate configuration
    if not endpoint:
        print("ERROR: Please set PROJECT_ENDPOINT in .env file")
        return 1
    
    if args.interactive:
        # Interactive mode uses default model
        return run_interactive_mode(endpoint, default_model)
    else:
        # Evaluation mode - use provided models or defaults
        if args.models:
            models = args.models
        else:
            # Default to two models from environment
            models = [
                os.getenv("MODEL_DEPLOYMENT_NAME", "gpt-4.1").strip('"\''),
                os.getenv("MODEL_DEPLOYMENT_NAME_ALT", "gpt-35-turbo").strip('"\'')
            ]
        
        return run_evaluation_mode(endpoint, models, args.output)