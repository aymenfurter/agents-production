import os
import json
import argparse
from pathlib import Path
from glob import glob
from typing import Dict, Any, Optional

from dotenv import load_dotenv
from openai import AsyncAzureOpenAI
from agents import Agent, Runner, OpenAIChatCompletionsModel
from agents.memory import SQLiteSession

from .tools import update_internal_scratchpad, message_to_user, make_warranty_decision_with_log
from .prompt import build_agent_instructions

load_dotenv()

# --- Workaround: make ChatCompletionMessageToolCallParam callable and dict-backed ---
import json as _json
import agents.models.chatcmpl_converter as _cc

def _ToolCallParam(**kwargs):
    fn = kwargs.get("function", {})
    args = fn.get("arguments", "{}")
    if not isinstance(args, str):
        fn["arguments"] = _json.dumps(args)
        kwargs["function"] = fn
    return kwargs

# Replace the typing.Union alias with a callable that returns the right dict shape
_cc.ChatCompletionMessageToolCallParam = _ToolCallParam
# --- End workaround ---

class ContosoCareAgent:
    def __init__(self, model: str, session_id: Optional[str] = None):
        api_key = os.getenv("OPENAI_AGENTS_API_KEY") or os.getenv("EVAL_MODEL_API_KEY")
        endpoint = os.getenv("OPENAI_AGENTS_ENDPOINT") or os.getenv("EVAL_MODEL_ENDPOINT")
        api_version = os.getenv("OPENAI_AGENTS_API_VERSION") or "2024-08-01-preview"

        self.openai_client = AsyncAzureOpenAI(
            api_key=api_key,
            api_version=api_version,
            azure_endpoint=endpoint
        )
        
        handbook_path = Path(__file__).parent.parent.parent / "contoso-handbook.md"
        handbook_content = handbook_path.read_text()
        
        self.agent = Agent(
            name="ContosoCare",
            instructions=build_agent_instructions(handbook_content),
            model=OpenAIChatCompletionsModel(model=model, openai_client=self.openai_client),
            tools=[update_internal_scratchpad, message_to_user, make_warranty_decision_with_log]
        )
        
        # Create one session per agent instance (similar to thread per agent in Foundry)
        if session_id:
            # Use persistent SQLite storage for session with provided ID
            db_path = Path(__file__).parent.parent.parent / "data" / "agent_sessions.db"
            db_path.parent.mkdir(exist_ok=True)
            self.session = SQLiteSession(session_id=session_id, db_path=str(db_path))
        else:
            # Use in-memory session for temporary conversations
            import uuid
            temp_session_id = f"temp_{uuid.uuid4().hex[:8]}"
            self.session = SQLiteSession(session_id=temp_session_id)
    
    def __del__(self):
        """Clean up resources when the agent is destroyed."""
        self.close_session()
    
    def close_session(self) -> None:
        """Close the session database connection."""
        try:
            if hasattr(self, 'session') and self.session:
                self.session.close()
                self.session = None
        except Exception as e:
            print(f"Warning: Error closing session: {e}")
    
    async def process(self, user_message: str) -> Dict[str, Any]:
        # Run the agent with the persistent session for conversation history
        result = await Runner.run(self.agent, input=user_message, session=self.session, max_turns=20)
        
        captured_tool_calls = []
        last_message = None
        
        for i, item in enumerate(result.new_items):
            if hasattr(item, 'raw_item') and hasattr(item.raw_item, 'name'):
                tool_name = item.raw_item.name
                tool_args_str = getattr(item.raw_item, 'arguments', '{}')
                
                tool_args = json.loads(tool_args_str) if isinstance(tool_args_str, str) else tool_args_str
                
                tool_output = {}
                if i + 1 < len(result.new_items):
                    next_item = result.new_items[i + 1]
                    if hasattr(next_item, 'output') and next_item.output:
                        try:
                            tool_output = json.loads(next_item.output) if isinstance(next_item.output, str) else next_item.output
                        except json.JSONDecodeError:
                            tool_output = {"result": next_item.output}
                
                captured_tool_calls.append({
                    "name": tool_name,
                    "arguments": tool_args,
                    "output": tool_output
                })
                
                if tool_name == 'message_to_user':
                    last_message = tool_args.get('message', '')
        
        if last_message is None:
            last_message = result.final_output
        
        return {
            "message": last_message,
            "actual_tool_calls": captured_tool_calls
        }
    
    async def get_conversation_history(self, limit: Optional[int] = None) -> list:
        """Get conversation history from the session."""
        return await self.session.get_items(limit=limit)
    
    async def clear_conversation(self) -> None:
        """Clear the conversation history."""
        await self.session.clear_session()


async def run_interactive_mode(model: str) -> int:
    agent = ContosoCareAgent(model)
    print("Agent: What happened to your device?")
    
    while True:
        user_input = input("\nYou: ").strip()
        
        if not user_input or user_input.lower() in ("quit", "exit"):
            break
        
        result = await agent.process(user_input)
        
        if result.get("message"):
            print(f"\nAgent: {result['message']}")
        
        for call in result.get("actual_tool_calls", []):
            print(f"[TOOL] {call['name']} {call['arguments']}")
    
    return 0


async def run_evaluation_mode(models: list, output_pattern: str) -> int:
    # Use relative path from current file location
    current_dir = Path(__file__).resolve().parent.parent.parent
    eval_path = current_dir / "quality_evals" / "scenarios"
    
    eval_files = [str(eval_path)] if eval_path.is_file() else sorted(glob(str(eval_path / "*.json")))
    
    base_name = Path(output_pattern).stem
    output_file = f"{base_name}_gpt_5.jsonl"
    
    Path(output_file).unlink(missing_ok=True)
    
    results_written = 0
    with Path(output_file).open("w") as output:
        for eval_file in eval_files:
            scenario = json.loads(Path(eval_file).read_text())
            
            print(f"Processing scenario: {scenario.get('id', 'unknown')}")
            
            import uuid
            fresh_session_id = f"eval_{uuid.uuid4().hex[:8]}"
            agent = ContosoCareAgent("gpt-5", session_id=fresh_session_id)
            
            conversation = scenario.get("conversation", [])
            if conversation:
                last_user_message = None
                for message in conversation:
                    if message["role"] == "user":
                        last_user_message = message["content"]
                
                result = await agent.process(last_user_message or "Continue with the warranty claim process.")
                 
                eval_result = {
                    "id": scenario.get("id"),
                    "description": scenario.get("description"),
                    "model": "gpt-5",
                    "conversation": conversation,
                    "expected_tool_calls": scenario.get("expected_tool_calls", []),
                    "actual_tool_calls": result["actual_tool_calls"]
                }
                
                output.write(json.dumps(eval_result) + "\n")
                results_written += 1
            
            # Clean up session resources for this scenario
            agent.close_session()
    
    print(f"Wrote {results_written} results to {output_file}")
    return 0


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--interactive", action="store_true")
    parser.add_argument("-o", "--output", default="eval_results")
    parser.add_argument("--models", nargs="+")
    args = parser.parse_args()
    
    if args.interactive:
        return await run_interactive_mode("gpt-5")
    else:
        return await run_evaluation_mode(["gpt-5"], args.output)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())