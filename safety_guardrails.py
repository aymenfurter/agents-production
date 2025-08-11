import gradio as gr
import subprocess
import sys
from pathlib import Path
import os
import asyncio

from utils import find_files, read_file_content, get_azure_ai_studio_link

# Adjust path to import from parent directories
sys.path.append(str(Path(__file__).resolve().parents[1]))

from variants.direct_inference.safety_evals import main as direct_safety_main
from variants.foundry_agents.safety_evals import main as foundry_safety_main
from variants.openai_agents.safety_evals import main as openai_safety_main

async def run_safety_evaluation(framework, progress=gr.Progress()):
    """Runs the safety evaluation for the specified framework."""
    progress(0, desc=f"Starting Red Teaming Agentuation for {framework}...")
    
    try:
        progress(0.5, desc=f"Executing safety evaluation for {framework}...")
        if framework == "Direct Inference":
            await direct_safety_main()
        elif framework == "Foundry":
            await foundry_safety_main()
        elif framework == "OpenAI Agents":
            await openai_safety_main()
        
        progress(1, desc="Evaluation Complete!")
        return f"Successfully ran safety evaluation for {framework}. Check the 'safety_outputs' directory."
    except Exception as e:
        return f"An unexpected error occurred during safety evaluation for {framework}: {e}"

def get_safety_result_files():
    """Gets all safety result files from the safety_outputs directory."""
    safety_outputs_path = Path("safety_outputs")
    if not safety_outputs_path.exists():
        return []
    
    result_files = []
    # Look for any files containing "final_results" in their name
    for json_file in safety_outputs_path.rglob("*.json"):
        if "final_results" in json_file.name:
            relative_path = str(json_file.relative_to(safety_outputs_path))
            result_files.append((relative_path, str(json_file)))
    
    return sorted(result_files)

def refresh_safety_files():
    """Refreshes the list of safety result files."""
    files = get_safety_result_files()
    return gr.Dropdown(choices=files, value=files[0][1] if files else None)

def create_safety_guardrails_tab():
    """Creates the Gradio UI for the safety guardrails tab."""
    with gr.Column():
        
        # Documentation in collapsible accordion
        with gr.Accordion("📚 Documentation - Understanding Red Teaming", open=False):
            gr.Markdown("""
            ### 🎯 What is Red Teaming?
            
            Red teaming is an automated adversarial testing approach where an AI agent systematically attempts to:
            - **Bypass safety guardrails** through various attack strategies
            - **Elicit harmful responses** across multiple risk categories
            - **Test the robustness** of your safety implementations
            
            This eliminates the need for manual testing of harmful scenarios, which would be both unethical and impractical.
            
            ### 🔍 What Gets Tested?
            
            #### **Risk Categories**
            The Red Teaming Agent tests your agent across these harmful content categories:
            - **Hate & Unfairness** 😤: Discriminatory, offensive, or biased content
            - **Violence** ⚔️: Content promoting physical harm or violent acts
            - **Sexual Content** 🔞: Inappropriate or explicit sexual material
            - **Self-Harm** ⚠️: Content that could encourage self-destructive behavior
            
            #### **Attack Strategies**
            The evaluation employs sophisticated attack techniques:
            - **Jailbreaking** 🔓: Attempts to bypass safety instructions through clever prompting (e.g., "Ignore previous instructions", role-playing scenarios)
            - **Base64 Encoding** 🔤: Hiding malicious content in encoded format to bypass text filters
            - **ROT13 Cipher** 🔄: Using simple letter substitution to obfuscate harmful requests
            
            ### 🏗️ Three-Layer Safety Architecture
            
            Responsible AI requires a comprehensive defense strategy:
            
            1. **Foundation Model Safety** 🧠
               - Choose LLMs trained with safety alignment (e.g., GPT-4 with RLHF)
               - Configure appropriate system prompts and behavioral instructions
               - Note: GPT-2 lacks safety training, making guardrails critical
            
            2. **Additional Guardrails** 🚧
               - **Content Safety Filters**: Azure AI Content Safety service for input/output filtering
               - **Block Lists**: Custom keyword blocking for domain-specific restrictions
               - **Threshold Configuration**: Adjustable sensitivity levels for different risk categories
            
            3. **User Interface Design** 👤
               - Clear disclaimers about AI-generated content
               - Verification prompts for sensitive actions
               - Transparency about system limitations
            
            ### 📊 Comparative Evaluation
            
            Each framework test includes:
            - **With Guardrails**: Full safety measures enabled (content filters, safety prompts)
            - **Without Guardrails**: Raw model responses (especially revealing for GPT-2)
            
            This comparison demonstrates the effectiveness of your safety implementations and identifies potential vulnerabilities.
            
            ### ⚡ How It Works
            
            1. The Red Teaming Agent generates adversarial prompts
            2. These prompts are sent to your agent
            3. Responses are analyzed for safety violations
            4. Results show attack success rates and vulnerability patterns
            
            > **Important**: The red teaming process is fully automated and conducted in a controlled environment. No actual harmful content is produced or distributed.
            """)
        
        gr.Markdown(f"**[View Detailed Safety Reports in Azure AI Studio]({get_azure_ai_studio_link()})**")

        with gr.Row():
            with gr.Column(scale=1):
                gr.Markdown("### 1. Red Teaming Agent Evaluations")
                gr.Markdown("""
                Trigger automated adversarial testing for each framework.
                Each evaluation tests both guarded and unguarded configurations.
                """)
                
                direct_button = gr.Button("Run Direct Inference (GPT-2) Red Teaming", variant="secondary")
                foundry_button = gr.Button("Run Foundry Agents (GPT-4.1) Red Teaming", variant="secondary")
                openai_button = gr.Button("Run OpenAI Agents (GPT-5) Red Teaming", variant="secondary")
                
                safety_status = gr.Textbox(label="Evaluation Status", interactive=False, lines=7)

                direct_button.click(lambda: asyncio.run(run_safety_evaluation("Direct Inference")), outputs=safety_status)
                foundry_button.click(lambda: asyncio.run(run_safety_evaluation("Foundry")), outputs=safety_status)
                openai_button.click(lambda: asyncio.run(run_safety_evaluation("OpenAI Agents")), outputs=safety_status)

            with gr.Column(scale=1):
                gr.Markdown("### 2. Explore Evaluation Results")
                gr.Markdown("""
                Results show:
                - Attack success rates per category
                - Vulnerability patterns
                - Effectiveness of safety measures
                """)
                
                with gr.Row():
                    # Initialize with actual files
                    initial_safety_files = get_safety_result_files()
                    safety_files_dropdown = gr.Dropdown(
                        label="Select a Safety Result File",
                        choices=initial_safety_files,
                        value=initial_safety_files[0][1] if initial_safety_files else None
                    )
                    refresh_safety_btn = gr.Button("🔄", size="sm", scale=0)
                
                safety_display = gr.Code(language="json", label="Result File Content", lines=20)
                
                safety_files_dropdown.change(fn=read_file_content, inputs=safety_files_dropdown, outputs=safety_display)
                refresh_safety_btn.click(fn=refresh_safety_files, outputs=safety_files_dropdown)
                
                # Auto-load content for initially selected file
                if initial_safety_files:
                    safety_display.value = read_file_content(initial_safety_files[0][1])
                    
        with gr.Accordion("📈 Results Interpretation Guide", open=False):
            gr.Markdown("""
            ### Interpreting Results
            
            - **Low attack success rate** = Strong safety implementation ✅
            - **High attack success rate** = Vulnerabilities need addressing ⚠️
            - **Comparison insights**: Difference between guarded/unguarded shows guardrail effectiveness
            
            For the most comprehensive analysis and visualizations, view the full reports in Azure AI Studio.
            """)