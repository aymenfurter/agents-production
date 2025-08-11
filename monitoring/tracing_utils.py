import os
import time
import uuid
import logging
from opentelemetry import trace
from opentelemetry.trace import SpanKind
from typing import Optional

logger = logging.getLogger(__name__)

class SpanManager:
    def __init__(self, tracer):
        self.tracer = tracer
        self.current_response_id = None
        logger.info(f"SpanManager initialized with tracer: {tracer}")
    
    def create_inference_span(self, context_id: str, user_input: str):
        # Create a dependency span (what the queries look for)
        span = self.tracer.start_span("azure_openai_inference", kind=SpanKind.CLIENT)
        
        # Generate response ID for tracking
        self.current_response_id = f"response_{uuid.uuid4().hex}"
        
        # Set attributes according to Azure AI Foundry schema for dependencies table
        span.set_attribute("gen_ai.operation.name", "chat")  # Required by queries
        span.set_attribute("gen_ai.system", "azure_openai")  # Required by queries
        span.set_attribute("gen_ai.response.id", self.current_response_id)
        span.set_attribute("context_id", context_id)
        
        # Model attributes - queries check both request and response model
        model_name = os.environ.get("MODEL_DEPLOYMENT_NAME", "gpt-4o")
        span.set_attribute("gen_ai.request.model", model_name)
        span.set_attribute("gen_ai.response.model", model_name)
        
        # Agent attributes
        span.set_attribute("gen_ai.agent.name", "contoso-care-agent")
        span.set_attribute("gen_ai.agent.version", "1.0.0")
        
        # Set dependency type for Application Insights
        span.set_attribute("dependency.type", "Http")  # Required for dependencies table
        span.set_attribute("dependency.target", "azure_openai")
        
        logger.info(f"Created inference dependency span - response_id: {self.current_response_id}, context: {context_id}")
        return span
    
    def create_assistant_message_span(self, thread_id: str, run_id: str, message_id: str):
        span = self.tracer.start_span("gen_ai.assistant.message", kind=SpanKind.INTERNAL)
        span.set_attribute("gen_ai.system", "azure.openai")
        span.set_attribute("gen_ai.thread.id", thread_id)
        span.set_attribute("gen_ai.thread.run.id", run_id)
        span.set_attribute("gen_ai.message.id", message_id)
        span.set_attribute("gen_ai.event.content", '{"role": "assistant"}')
        
        # Link to the current inference call
        if self.current_response_id:
            span.set_attribute("gen_ai.response.id", self.current_response_id)
        
        logger.info(f"Created assistant message span - thread: {thread_id}, run: {run_id}")
        return span
    
    def set_token_usage(self, span, input_tokens: int, output_tokens: Optional[int] = None):
        # Queries expect integer values, so ensure they're properly formatted
        span.set_attribute("gen_ai.usage.input_tokens", input_tokens)
        if output_tokens is not None:
            span.set_attribute("gen_ai.usage.output_tokens", output_tokens)
            span.set_attribute("gen_ai.usage.total_tokens", input_tokens + output_tokens)
        else:
            span.set_attribute("gen_ai.usage.output_tokens", 0)
            span.set_attribute("gen_ai.usage.total_tokens", input_tokens)
        
        logger.debug(f"Set token usage - input: {input_tokens}, output: {output_tokens}")
    
    def set_execution_timing(self, span, start_time: float):
        duration_ms = (time.time() - start_time) * 1000
        span.set_attribute("gen_ai.execution.duration_ms", duration_ms)
        
        logger.debug(f"Set execution timing - duration: {duration_ms:.2f}ms")
    
    def set_thread_attributes(self, span, thread_id: str, is_new_thread: bool):
        span.set_attribute("gen_ai.thread.id", thread_id)
        span.set_attribute("gen_ai.thread.created", is_new_thread)
        
        logger.debug(f"Set thread attributes - id: {thread_id}, new: {is_new_thread}")
    
    def set_run_attributes(self, span, run_id: str, status: str):
        span.set_attribute("gen_ai.run.id", run_id)
        span.set_attribute("gen_ai.run.status", status)
        
        logger.debug(f"Set run attributes - id: {run_id}, status: {status}")
    
    def set_success_result(self, span, response_text: str):
        span.set_attribute("agent.response", response_text)
        # Set success=true for the dependencies table queries
        span.set_status(trace.Status(trace.StatusCode.OK))
        
        logger.info(f"Set success result - response length: {len(response_text) if response_text else 0}")
    
    def set_error_result(self, span, error: Exception, error_message: str):
        span.set_attribute("gen_ai.error.type", type(error).__name__)
        span.set_attribute("gen_ai.error.message", str(error))
        span.record_exception(error)
        # Set success=false for the dependencies table queries
        span.set_status(trace.Status(trace.StatusCode.ERROR, description=error_message))
        
        logger.error(f"Set error result - {type(error).__name__}: {error}")
    
    def set_failure_result(self, span, error_message: str):
        span.set_attribute("gen_ai.error.message", error_message)
        # Set success=false for the dependencies table queries
        span.set_status(trace.Status(trace.StatusCode.ERROR, description=error_message))
        
        logger.error(f"Set failure result - {error_message}")

    def emit_user_feedback(self, feedback_symbol: str, details: Optional[str] = None):
        """
        Record user feedback (+/-) tied to the most recent gen_ai.response.id.
        KQL expects:
          event.name == 'gen_ai.evaluation.user_feedback'
          gen_ai.evaluation.score == -1 for Positive (+), 1 for Negative (-)
        """
        symbol = (feedback_symbol or "").strip()
        
        score_map = {"+": -1, "-": 1}
        if symbol not in score_map:
            logger.warning(f"Ignoring invalid feedback symbol: {symbol!r}")
            return

        evaluation_id = str(uuid.uuid4())
        response_id = self.current_response_id or "unknown"

        event_attributes = {
            "event.name": "gen_ai.evaluation.user_feedback",
            "gen_ai.evaluation.id": evaluation_id,
            "gen_ai.evaluator.name": "UserFeedback",
            "gen_ai.evaluation.score": str(score_map[symbol]),
            "gen_ai.response.id": response_id
        }
        if details:
            event_attributes["gen_ai.evaluation.reasoning"] = details

        # Emit to traces table (customDimensions)
        telemetry_logger = logging.getLogger("gen_ai.evaluation")
        telemetry_logger.info("gen_ai.evaluation.user_feedback", extra=event_attributes)

        # Also add as an event on a short-lived span
        with self.tracer.start_as_current_span("user_feedback_telemetry") as span:
            span.add_event(
                name="gen_ai.evaluation.user_feedback",
                attributes=event_attributes
            )
            span.set_status(trace.Status(trace.StatusCode.OK))

        logger.info(f"Recorded user feedback: {symbol} (score={score_map[symbol]}) for response_id: {response_id}")