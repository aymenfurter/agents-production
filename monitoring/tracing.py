import os
import logging
from opentelemetry import trace

logger = logging.getLogger(__name__)

def setup_azure_monitor_tracing():
    connection_string = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")
    logger.info(f"Setting up Azure Monitor tracing...")
    logger.info(f"Connection string available: {'Yes' if connection_string else 'No'}")
    
    if not connection_string:
        logger.warning("APPLICATIONINSIGHTS_CONNECTION_STRING not set. Tracing will not be enabled.")
        return
        
    try:
        from azure.monitor.opentelemetry._configure import configure_azure_monitor
        logger.info("Configuring Azure Monitor with connection string...")
        configure_azure_monitor(
            connection_string=connection_string,
            disable_offline_storage=True,
        )
        logger.info("Azure Monitor tracing configured successfully.")
        logger.info(f"Tracer provider: {trace.get_tracer_provider()}")
    except Exception as e:
        logger.error(f"Failed to configure Azure Monitor tracing: {e}", exc_info=True)

def get_tracer(name: str):
    tracer = trace.get_tracer(name)
    logger.info(f"Created tracer for: {name}")
    return tracer