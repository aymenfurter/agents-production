import gradio as gr
import os
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables from .env file at the project root
dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
load_dotenv(dotenv_path=dotenv_path)

from interactive_chat import create_interactive_chat_tab
from evals import create_quality_evals_tab
from safety_guardrails import create_safety_guardrails_tab
from brand_integrity import create_brand_integrity_tab
from monitoring_tab import create_monitoring_tab
from theme import ContosoCareTheme

def create_ui():
    """Creates the main Gradio UI with all tabs."""
    # Use custom theme instead of CSS overrides
    custom_theme = ContosoCareTheme()
    
    with gr.Blocks(theme=custom_theme, title="ContosoCare Agent Hub") as demo:
        gr.Markdown("# ContosoCare - Agents in Production")
        
        with gr.Tabs():
            with gr.TabItem("Interactive Chat"):
                create_interactive_chat_tab()
            
            with gr.TabItem("Quality Evaluation"):
                create_quality_evals_tab()

            with gr.TabItem("Safety Guardrails"):
                create_safety_guardrails_tab()

            with gr.TabItem("Brand Integrity"):
                create_brand_integrity_tab()

            with gr.TabItem("Live Monitoring"):
                create_monitoring_tab()

    return demo

if __name__ == "__main__":
    # Validate essential environment variables
    required_vars = [
        "PROJECT_ENDPOINT", "AZURE_ML_ENDPOINT", "EVAL_MODEL_ENDPOINT", 
        "EVAL_MODEL_API_KEY", "AZURE_SUBSCRIPTION_ID", "AZURE_RESOURCE_GROUP", 
        "AZURE_PROJECT_NAME", "APPLICATIONINSIGHTS_CONNECTION_STRING"
    ]
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    if missing_vars:
        print(f"Warning: The following environment variables are not set in your .env file: {', '.join(missing_vars)}")
        print("Some application features may not work correctly.")

    app_ui = create_ui()
    app_ui.launch(share=False, debug=True)