import os
import json
import time
import argparse
import asyncio
import uuid
from pathlib import Path
import logging
import tiktoken

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential

from dotenv import load_dotenv
load_dotenv()

os.environ.setdefault(
    "OTEL_INSTRUMENTATION_HTTP_EXCLUDED_URLS",
    "https://.*\\.in\\.applicationinsights\\.azure\\.com/.*,https://.*\\.applicationinsights\\.azure\\.com/.*"
)
os.environ.setdefault("OTEL_PYTHON_DISABLED_INSTRUMENTATIONS", "urllib3,requests")

from .tools import *
from .prompt import build_agent_instructions
from .tracing import setup_azure_monitor_tracing, get_tracer
from .evaluation_sdk import SDKEvaluationManager
from .tracing_utils import SpanManager

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

logging.getLogger("azure.core.pipeline.policies.http_logging_policy").setLevel(logging.WARNING)
logging.getLogger("azure.monitor.opentelemetry").setLevel(logging.WARNING)

setup_azure_monitor_tracing()
tracer = get_tracer(__name__)

class ContosoCareAgent:
    def __init__(self, endpoint: str, model: str):
        logger.info(f"Initializing ContosoCareAgent - endpoint: {endpoint}, model: {model}")
        
        self.client = AIProjectClient(
            endpoint=endpoint, 
            credential=DefaultAzureCredential()
        )
        
        handbook_path = Path(__file__).parent.parent / "contoso-handbook.md"
        with open(handbook_path) as file:
            handbook_content = file.read()
        
        self.agent = self.client.agents.create_agent(
            model=model,
            name="ContosoCare",
            instructions=build_agent_instructions(handbook_content),
            tools=get_tool_definitions()
        )
        
        self.thread = self.client.agents.threads.create()
        
        self._tool_functions = {
            "update_internal_scratchpad": update_internal_scratchpad,
            "message_to_user": message_to_user,
            "make_warranty_decision_with_log": make_warranty_decision_with_log
        }
        
        self.evaluation_manager = SDKEvaluationManager(tracer, self.client)
        self.span_manager = SpanManager(tracer)
        
        try:
            self.tokenizer = tiktoken.get_encoding("cl100k_base")
        except Exception:
            self.tokenizer = None
            logger.warning("Failed to initialize tiktoken, falling back to word count approximation")
        
        logger.info(f"Agent created with ID: {self.agent.id}")
        logger.info(f"Thread created with ID: {self.thread.id}")
    
    def __del__(self):
        try:
            # Shutdown evaluation manager first
            if hasattr(self, 'evaluation_manager'):
                self.evaluation_manager.shutdown()
                
            if hasattr(self, 'thread'):
                self.client.agents.threads.delete(thread_id=self.thread.id)
            if hasattr(self, 'agent'):
                self.client.agents.delete_agent(agent_id=self.agent.id)
        except:
            pass
    
    def _count_tokens(self, text: str) -> int:
        if self.tokenizer:
            try:
                return len(self.tokenizer.encode(text))
            except Exception:
                pass
        return len(text.split())
    
    def process(self, user_message: str, context_id: str = None) -> dict:
        if not context_id:
            context_id = str(uuid.uuid4())
        
        logger.info(f"Processing message - context: {context_id}, message length: {len(user_message)}")
        
        input_tokens = self._count_tokens(user_message)
        
        # Create the main inference span as a dependency (what the queries look for)
        with self.span_manager.create_inference_span(context_id, user_message) as span:
            self.span_manager.set_token_usage(span, input_tokens)
            
            try:
                start_time = time.time()
                
                thread_id = f"thread_{context_id}"
                run_id = f"run_{uuid.uuid4().hex}"
                message_id = f"msg_{uuid.uuid4().hex}"
                
                logger.info(f"Starting agent run - thread: {thread_id}, run: {run_id}")
                
                self.span_manager.set_thread_attributes(span, thread_id, True)
                self.span_manager.set_run_attributes(span, run_id, "in_progress")
                
                # Execute the agent run directly within the inference span
                self.client.agents.messages.create(
                    thread_id=self.thread.id,
                    role="user",
                    content=user_message
                )
                
                run = self.client.agents.runs.create(
                    thread_id=self.thread.id,
                    agent_id=self.agent.id
                )
                
                logger.info(f"Agent run created with status: {run.status}")
                
                captured_tool_calls = []
                while run.status in ("queued", "in_progress", "requires_action"):
                    time.sleep(1)
                    run = self.client.agents.runs.get(
                        thread_id=self.thread.id,
                        run_id=run.id
                    )
                    logger.debug(f"Run status: {run.status}")
                    
                    if run.status == "requires_action":
                        logger.info(f"Executing tool calls - count: {len(run.required_action.submit_tool_outputs.tool_calls)}")
                        tool_outputs = self._execute_tool_calls(
                            run.required_action.submit_tool_outputs.tool_calls,
                            captured_tool_calls
                        )
                        self.client.agents.runs.submit_tool_outputs(
                            thread_id=self.thread.id,
                            run_id=run.id,
                            tool_outputs=tool_outputs
                        )
                
                logger.info(f"Agent run completed with status: {run.status}")
                logger.info(f"Total tool calls executed: {len(captured_tool_calls)}")
                
                last_message = None
                extracted_tool_calls = []
                
                for call in captured_tool_calls:
                    if call["name"] == "message_to_user":
                        last_message = call["output"].get("message")
                    
                    # Extract tool calls for evaluation
                    extracted_tool_calls.append({
                        "type": "tool_call",
                        "tool_call_id": f"call_{uuid.uuid4().hex}",
                        "name": call["name"],
                        "arguments": call["arguments"]
                    })
                
                # Calculate final metrics
                output_tokens = self._count_tokens(last_message) if last_message else 0
                self.span_manager.set_execution_timing(span, start_time)
                self.span_manager.set_token_usage(span, input_tokens, output_tokens)
                self.span_manager.set_run_attributes(span, run_id, "completed")
                self.span_manager.set_success_result(span, last_message or "No user message")
                
                logger.info(f"Token usage - input: {input_tokens}, output: {output_tokens}")
                logger.info(f"Response message length: {len(last_message) if last_message else 0}")
                
                # Create separate span for assistant message logging (traces table)
                with self.span_manager.create_assistant_message_span(thread_id, run_id, message_id):
                    logger.info(f"Assistant message logged for thread {thread_id}")
                
                # Submit evaluation to background thread - NON-BLOCKING
                if last_message:
                    logger.info("Submitting evaluation to background thread...")
                    self.evaluation_manager.evaluate_conversation_background(
                        thread_id, run_id, user_message, last_message, 
                        input_tokens, output_tokens, extracted_tool_calls,
                        response_id=self.span_manager.current_response_id
                    )
                    logger.info("Evaluation submitted - returning response immediately")
                
                return {
                    "message": last_message,
                    "actual_tool_calls": captured_tool_calls
                }
                
            except Exception as e:
                error_message = f"Error: {str(e)}"
                self.span_manager.set_error_result(span, e, error_message)
                logger.error(f"Processing failed: {e}", exc_info=True)
                return {
                    "message": error_message,
                    "actual_tool_calls": []
                }
    
    def _execute_tool_calls(self, tool_calls: list, captured_calls: list) -> list:
        logger.info(f"Executing {len(tool_calls)} tool calls")
        tool_outputs = []
        
        for i, tool_call in enumerate(tool_calls):
            tool_name = tool_call.function.name
            tool_args = json.loads(tool_call.function.arguments)
            
            logger.info(f"Executing tool call {i+1}/{len(tool_calls)}: {tool_name}")
            logger.debug(f"Tool arguments: {tool_args}")
            
            tool_function = self._tool_functions[tool_name]
            result = tool_function(**tool_args)
            
            if isinstance(result, str):
                result_dict = json.loads(result)
            else:
                result_dict = result
            
            logger.debug(f"Tool result: {result_dict}")
            
            captured_calls.append({
                "name": tool_name,
                "arguments": tool_args,
                "output": result_dict
            })
            
            tool_outputs.append({
                "tool_call_id": tool_call.id,
                "output": json.dumps(result_dict) if isinstance(result, dict) else result
            })
        
        logger.info(f"All tool calls executed successfully")
        return tool_outputs

async def run_interactive_mode(endpoint: str, model: str) -> int:
    print("=" * 60)
    print("ContosoCare System with Monitoring")
    print("=" * 60)
    
    logger.info("Starting interactive mode")
    logger.info(f"Endpoint: {endpoint}")
    logger.info(f"Model: {model}")
    logger.info(f"Application Insights Connection String: {'Set' if os.getenv('APPLICATIONINSIGHTS_CONNECTION_STRING') else 'Not Set'}")
    
    try:
        agent = ContosoCareAgent(endpoint, model)
        print("Agent: What happened to your device?")
        
        conversation_count = 0
        
        while True:
            user_input = input("\nYou: ").strip()
            
            if not user_input:
                continue
            
            if user_input.lower() in ("quit", "exit"):
                break
            
            conversation_count += 1
            logger.info(f"Processing conversation #{conversation_count}")
            
            print("[Processing...]")
            result = agent.process(user_input)
            
            if result.get("message"):
                print(f"\nAgent: {result['message']}")
            
            for call in result.get("actual_tool_calls", []):
                print(f"[TOOL] {call['name']} {call['arguments']}")
                
        logger.info(f"Interactive session completed - {conversation_count} conversations")
                
    except KeyboardInterrupt:
        print("\n\nGoodbye!")
    except Exception as e:
        logger.error(f"Application failed: {e}", exc_info=True)
        return 1
    
    return 0

def main():
    parser = argparse.ArgumentParser(description="ContosoCare Warranty Claim Agent with Monitoring")
    parser.add_argument(
        "-i", "--interactive",
        action="store_true",
        default=True,
        help="Run in interactive chat mode (default)"
    )
    args = parser.parse_args()
    
    endpoint = os.getenv("PROJECT_ENDPOINT", "").strip('"\'')
    default_model = os.getenv("MODEL_DEPLOYMENT_NAME", "gpt-4o").strip('"\'')
    
    if not endpoint:
        print("ERROR: Please set PROJECT_ENDPOINT in .env file")
        return 1
    
    return asyncio.run(run_interactive_mode(endpoint, default_model))

if __name__ == "__main__":
    raise SystemExit(main())