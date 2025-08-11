import os
import uuid
import logging
import time
import concurrent.futures
import threading
from typing import Optional, Dict, List
from opentelemetry import trace

logger = logging.getLogger(__name__)

from azure.identity import DefaultAzureCredential

class SDKEvaluationManager:
    def __init__(self, tracer, project_client=None):
        self.tracer = tracer
        self.project_client = project_client
        self.evaluation_available = False
        self.evaluators = {}
        self.agent_evaluators = {}
        self.safety_evaluators = {}
        self.model_config = None
        self.reasoning_model_config = None
        self.converter = None
        
        # Background execution setup
        self.executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=3, 
            thread_name_prefix="evaluation_"
        )
        self._shutdown_event = threading.Event()
        
        self._initialize_evaluation()

    def __del__(self):
        """Cleanup thread pool on deletion."""
        try:
            if hasattr(self, 'executor'):
                self.executor.shutdown(wait=False)
        except:
            pass

    def shutdown(self):
        """Gracefully shutdown the evaluation manager."""
        logger.info("Shutting down evaluation manager...")
        self._shutdown_event.set()
        if hasattr(self, 'executor'):
            self.executor.shutdown(wait=True, timeout=30)

    def _initialize_evaluation(self):
        try:
            from azure.ai.evaluation import (
                RelevanceEvaluator, 
                CoherenceEvaluator, 
                FluencyEvaluator,
                # six built-in evaluators
                HateUnfairnessEvaluator,
                ViolenceEvaluator,
                SelfHarmEvaluator,
                IndirectAttackEvaluator,
                CodeVulnerabilityEvaluator,
                # keep these agent evaluators
                IntentResolutionEvaluator,
                TaskAdherenceEvaluator,
                ToolCallAccuracyEvaluator,
                AzureOpenAIModelConfiguration,
                AIAgentConverter,
                AzureAIProject
            )
            
            required_vars = ["OPENAI_AGENTS_ENDPOINT", "OPENAI_AGENTS_API_KEY"]
            if all(os.getenv(var) for var in required_vars):
                self.azure_ai_project = AzureAIProject(
                        subscription_id=os.getenv("AZURE_SUBSCRIPTION_ID"),
                        resource_group_name=os.getenv("AZURE_RESOURCE_GROUP"),
                        project_name=os.getenv("AZURE_PROJECT_NAME"),
                )

                self.credential = DefaultAzureCredential(exclude_interactive_browser_credential=True)
                
                self.model_config = AzureOpenAIModelConfiguration(
                    azure_endpoint=os.environ["OPENAI_AGENTS_ENDPOINT"],
                    azure_deployment=os.getenv("MODEL_DEPLOYMENT_NAME", "gpt-4o"),
                    api_version=os.getenv("OPENAI_AGENTS_API_VERSION", "2024-08-01-preview"),
                    api_key=os.environ["OPENAI_AGENTS_API_KEY"]
                )
                
                # Check if reasoning model is available for agent evaluators
                reasoning_model = os.getenv("REASONING_MODEL_DEPLOYMENT_NAME", "o3-mini")
                self.reasoning_model_config = AzureOpenAIModelConfiguration(
                    azure_endpoint=os.environ["OPENAI_AGENTS_ENDPOINT"],
                    azure_deployment=reasoning_model,
                    api_version=os.getenv("OPENAI_AGENTS_API_VERSION", "2024-08-01-preview"),
                    api_key=os.environ["OPENAI_AGENTS_API_KEY"]
                )
                
                # Standard quality evaluators
                self.evaluators = {
                    "relevance": RelevanceEvaluator(self.model_config),
                    "coherence": CoherenceEvaluator(self.model_config),
                    "fluency": FluencyEvaluator(self.model_config),
                }
                
                # Six built-in evaluators your KQL tracks
                self.safety_evaluators = {}
                def _safe_create_evaluator(evaluator_cls):
                    # try with project + credential; fall back to default ctor if signature differs
                    try:
                        return evaluator_cls(azure_ai_project=self.azure_ai_project, credential=self.credential)
                    except TypeError:
                        return evaluator_cls()
                self.safety_evaluators["hate_unfairness"] = _safe_create_evaluator(HateUnfairnessEvaluator)
                self.safety_evaluators["violence"] = _safe_create_evaluator(ViolenceEvaluator)
                self.safety_evaluators["self_harm"] = _safe_create_evaluator(SelfHarmEvaluator)
                self.safety_evaluators["indirect_attack"] = _safe_create_evaluator(IndirectAttackEvaluator)
                self.safety_evaluators["code_vulnerability"] = _safe_create_evaluator(CodeVulnerabilityEvaluator)

                # Keep agent evaluators (remove content_safety/protected_material)
                self.agent_evaluators = {
                    "intent_resolution": IntentResolutionEvaluator(
                        model_config=self.reasoning_model_config, is_reasoning_model=True
                    ),
                    "task_adherence": TaskAdherenceEvaluator(
                        model_config=self.reasoning_model_config, is_reasoning_model=True
                    ),
                    "tool_call_accuracy": ToolCallAccuracyEvaluator(
                        model_config=self.reasoning_model_config, is_reasoning_model=True
                    ),
                }

                # Initialize converter if project client is available
                if self.project_client:
                    self.converter = AIAgentConverter(self.project_client)
                
                self.evaluation_available = True
                logger.info("Azure AI Evaluation SDK initialized with safety + agent evaluators")
            else:
                logger.warning("Required environment variables missing for evaluation")
                
        except ImportError as e:
            logger.warning(f"Azure AI Evaluation SDK not available: {e}")
        except Exception as e:
            logger.warning(f"Failed to initialize evaluation: {e}")

    def evaluate_conversation_background(self, 
                                      thread_id: str, 
                                      run_id: str, 
                                      user_input: str, 
                                      assistant_response: str,
                                      input_tokens: int,
                                      output_tokens: int,
                                      tool_calls: Optional[List[Dict]] = None,
                                      response_id: Optional[str] = None):
        """Submit evaluation to background thread pool - non-blocking."""
        if not self.evaluation_available:
            logger.debug("Evaluation not available, skipping background evaluation")
            return
            
        if self._shutdown_event.is_set():
            logger.debug("Evaluation manager shutting down, skipping new evaluations")
            return

        # Submit to thread pool for background execution
        future = self.executor.submit(
            self._run_evaluation_sync,
            thread_id, run_id, user_input, assistant_response,
            input_tokens, output_tokens, tool_calls, response_id
        )
        
        # Add completion callback for logging
        future.add_done_callback(self._evaluation_complete_callback)
        
        logger.info(f"Evaluation submitted to background thread - thread_id: {thread_id}")

    def _run_evaluation_sync(self, 
                           thread_id: str, 
                           run_id: str, 
                           user_input: str, 
                           assistant_response: str,
                           input_tokens: int,
                           output_tokens: int,
                           tool_calls: Optional[List[Dict]] = None,
                           response_id: Optional[str] = None):
        """Run evaluation synchronously in background thread."""
        try:
            logger.info(f"Starting background evaluation - thread_id: {thread_id}")
            
            evaluation_id = str(uuid.uuid4())
            
            for evaluator_name, evaluator in self.evaluators.items():
                if self._shutdown_event.is_set():
                    logger.info("Evaluation shutdown requested, stopping early")
                    return
                    
                try:
                    self._run_single_evaluation_sync(
                        evaluator_name, evaluator, evaluation_id, 
                        thread_id, run_id, user_input, assistant_response,
                        input_tokens, output_tokens, response_id=response_id
                    )
                except Exception as e:
                    logger.error(f"Failed to run {evaluator_name} evaluation: {e}")
            
            # Run the six built-in safety evaluators
            for evaluator_name, evaluator in self.safety_evaluators.items():
                if self._shutdown_event.is_set():
                    return
                    
                try:
                    self._run_single_evaluation_sync(
                        evaluator_name, evaluator, evaluation_id,
                        thread_id, run_id, user_input, assistant_response,
                        input_tokens, output_tokens, response_id=response_id
                    )
                except Exception as e:
                    logger.error(f"Failed to run safety {evaluator_name} evaluation: {e}")

            # Run agent evaluators
            for evaluator_name, evaluator in self.agent_evaluators.items():
                if self._shutdown_event.is_set():
                    return
                    
                try:
                    self._run_agent_evaluation_sync(
                        evaluator_name, evaluator, evaluation_id,
                        thread_id, run_id, user_input, assistant_response,
                        input_tokens, output_tokens, tool_calls, response_id=response_id
                    )
                except Exception as e:
                    logger.error(f"Failed to run agent {evaluator_name} evaluation: {e}")
                    
            logger.info(f"Background evaluation completed - thread_id: {thread_id}")
            
        except Exception as e:
            logger.error(f"Background evaluation failed - thread_id: {thread_id}: {e}", exc_info=True)

    def _evaluation_complete_callback(self, future):
        """Callback when background evaluation completes."""
        try:
            future.result()  # This will raise any exception that occurred
            logger.debug("Background evaluation completed successfully")
        except Exception as e:
            logger.error(f"Background evaluation failed: {e}")

    def _run_single_evaluation_sync(self, 
                                  evaluator_name: str,
                                  evaluator,
                                  evaluation_id: str,
                                  thread_id: str,
                                  run_id: str,
                                  query: str,
                                  response: str,
                                  input_tokens: int,
                                  output_tokens: int,
                                  response_id: Optional[str] = None):
        """Synchronous version of single evaluation."""
        result = evaluator(query=query, response=response)
        
        score = self._extract_score(result, evaluator_name)
        reasoning = self._extract_reasoning(result, evaluator_name)
        
        self._emit_evaluation_telemetry(
            evaluator_name, evaluation_id, thread_id, run_id,
            score, reasoning, input_tokens, output_tokens,
            response_id=response_id
        )
        
        logger.info(f"Safety/quality evaluation completed - {evaluator_name}: {score}")

    def _run_agent_evaluation_sync(self,
                                 evaluator_name: str,
                                 evaluator,
                                 evaluation_id: str,
                                 thread_id: str,
                                 run_id: str,
                                 query: str,
                                 response: str,
                                 input_tokens: int,
                                 output_tokens: int,
                                 tool_calls: Optional[List[Dict]] = None,
                                 response_id: Optional[str] = None):
        """Synchronous version of agent evaluation."""
        # Prepare evaluation parameters based on evaluator type
        eval_params = {"query": query, "response": response}
        
        # Add tool calls for evaluators that support them
        if tool_calls and evaluator_name in ["intent_resolution", "task_adherence"]:
            eval_params["tool_calls"] = tool_calls
        elif evaluator_name == "tool_call_accuracy" and tool_calls:
            eval_params["tool_calls"] = tool_calls
            eval_params["tool_definitions"] = self._get_tool_definitions()
        
        result = evaluator(**eval_params)
        
        score = self._extract_score(result, evaluator_name)
        reasoning = self._extract_reasoning(result, evaluator_name)
        
        self._emit_evaluation_telemetry(
            evaluator_name, evaluation_id, thread_id, run_id,
            score, reasoning, input_tokens, output_tokens,
            response_id=response_id
        )
        
        logger.info(f"Agent evaluation completed - {evaluator_name}: {score}")

    async def evaluate_conversation(self, 
                                  thread_id: str, 
                                  run_id: str, 
                                  user_input: str, 
                                  assistant_response: str,
                                  input_tokens: int,
                                  output_tokens: int,
                                  tool_calls: Optional[List[Dict]] = None,
                                  response_id: Optional[str] = None):
        """Legacy async method - now delegates to background version."""
        self.evaluate_conversation_background(
            thread_id, run_id, user_input, assistant_response,
            input_tokens, output_tokens, tool_calls, response_id
        )

    def _get_tool_definitions(self) -> List[Dict]:
        """Get tool definitions for tool call accuracy evaluation."""
        return [
            {
                "name": "update_internal_scratchpad",
                "description": "Update the agent's internal scratchpad for tracking thought process.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "reasoning": {"type": "string", "description": "Current reasoning about the case"},
                        "confidence_level": {"type": "string", "description": "Confidence level"},
                        "red_flags": {"type": "array", "description": "Any concerning aspects"}
                    }
                }
            },
            {
                "name": "message_to_user",
                "description": "Ask the customer a follow-up message to gather more information.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "message": {"type": "string", "description": "Message to ask the customer"}
                    }
                }
            },
            {
                "name": "make_warranty_decision_with_log",
                "description": "Make a warranty coverage decision and log claim details.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "decision": {"type": "string", "description": "Either covered or needs_human_review"},
                        "reason": {"type": "string", "description": "Explanation for the decision"},
                        "deductible_amount": {"type": "number", "description": "Deductible amount if covered"},
                        "customer_info": {"type": "object", "description": "Customer details"},
                        "device_info": {"type": "object", "description": "Device details"},
                        "incident_info": {"type": "object", "description": "Incident details"}
                    }
                }
            }
        ]

    def evaluate_with_converter(self, thread_id: str, run_id: str):
        """Use AIAgentConverter to evaluate agent thread data."""
        if not self.converter:
            logger.warning("AIAgentConverter not available")
            return
        
        try:
            converted_data = self.converter.convert(thread_id, run_id)
            
            # Run all evaluators on converted data
            all_evaluators = {**self.evaluators, **self.agent_evaluators}
            results = {}
            
            for name, evaluator in all_evaluators.items():
                try:
                    result = evaluator(**converted_data)
                    results[name] = result
                    logger.info(f"Converter evaluation completed - {name}: {result.get('score', 'N/A')}")
                except Exception as e:
                    logger.error(f"Failed converter evaluation for {name}: {e}")
            
            return results
            
        except Exception as e:
            logger.error(f"Failed to convert and evaluate agent data: {e}")
            return None

    def _extract_score(self, result, evaluator_name: str) -> Optional[float]:
        if hasattr(result, evaluator_name):
            return getattr(result, evaluator_name)
        if hasattr(result, 'score'):
            return result.score
        if isinstance(result, dict):
            return result.get(evaluator_name) or result.get('score')
        return None

    def _extract_reasoning(self, result, evaluator_name: str) -> Optional[str]:
        reasoning_key = f"{evaluator_name}_reason"
        if hasattr(result, reasoning_key):
            return getattr(result, reasoning_key)
        if hasattr(result, 'reason'):
            return result.reason
        if isinstance(result, dict):
            return result.get(reasoning_key) or result.get('reason')
        return None

    def _emit_evaluation_telemetry(self, 
                                 evaluator_name: str,
                                 evaluation_id: str,
                                 thread_id: str,
                                 run_id: str,
                                 score: Optional[float],
                                 reasoning: Optional[str],
                                 input_tokens: int,
                                 output_tokens: int,
                                 response_id: Optional[str] = None):
        logger.info(f"Emitting evaluation telemetry - evaluator: {evaluator_name}, score: {score}")
        
        with self.tracer.start_as_current_span("evaluation_telemetry") as span:
            # Set span attributes for context
            span.set_attribute("gen_ai.evaluation.id", evaluation_id)
            # keep snake_case to align with your KQL's get_evaluator_name fallback behavior
            span.set_attribute("gen_ai.evaluator.name", evaluator_name)
            span.set_attribute("gen_ai.thread.id", thread_id)
            span.set_attribute("gen_ai.thread.run.id", run_id)
            if response_id:
                span.set_attribute("gen_ai.response.id", response_id)
            
            # Create the event attributes that the dashboard looks for
            event_attributes = {
                "event.name": "gen_ai.evaluation.result",
                "gen_ai.evaluation.id": evaluation_id,
                "gen_ai.evaluator.id": f"azureai://built-in/evaluators/{evaluator_name}",
                "gen_ai.evaluator.name": evaluator_name,
                "gen_ai.thread.id": thread_id,
                "gen_ai.thread.run.id": run_id,
                "gen_ai.usage.input_tokens": str(input_tokens),
                "gen_ai.usage.output_tokens": str(output_tokens)
            }
            if response_id:
                event_attributes["gen_ai.response.id"] = response_id
            
            if score is not None:
                event_attributes["gen_ai.evaluation.score"] = str(score)
            if reasoning:
                event_attributes["gen_ai.evaluation.reasoning"] = reasoning
            
            # Add the trace event to the span
            span.add_event(
                name="gen_ai.evaluation.result",
                attributes=event_attributes
            )
            
            # Also emit as a trace entry for Application Insights traces table
            telemetry_logger = logging.getLogger("gen_ai.evaluation")
            telemetry_logger.info("gen_ai.evaluation.result", extra=event_attributes)
            
            span.set_status(trace.Status(trace.StatusCode.OK))