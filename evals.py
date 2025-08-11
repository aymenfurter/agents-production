import gradio as gr
import json
from pathlib import Path
import subprocess
import sys
import os
import asyncio

from utils import find_files, read_jsonl_file, read_file_content, get_azure_evaluation_link

# Adjust path to import from parent directories
sys.path.append(str(Path(__file__).resolve().parents[1]))

# Import evaluation runners
from variants.direct_inference.agent import run_evaluation_mode as run_direct_eval
from variants.foundry_agents.agent import run_evaluation_mode as run_foundry_eval
from variants.openai_agents.agent import run_evaluation_mode as run_openai_eval
from quality_evals.evals import run_cloud_evaluation

def generate_answers(agent_framework, progress=gr.Progress()):
    """Triggers the answer generation scripts for the selected framework."""
    progress(0, desc=f"Starting {agent_framework} Answer Generation...")
    
    endpoint = os.getenv("PROJECT_ENDPOINT")
    output_pattern = "eval_results"
    
    try:
        if agent_framework == "Direct Inference (GPT-2)":
            progress(0.5, desc="Running Direct Inference evaluation...")
            run_direct_eval(os.getenv("AZURE_ML_ENDPOINT"), "eval_results_gpt-2.jsonl")
        
        elif agent_framework == "Foundry Agents":
            models = [
                os.getenv("MODEL_DEPLOYMENT_NAME", "gpt-4.1"),
                os.getenv("MODEL_DEPLOYMENT_NAME_ALT", "gpt-35-turbo")
            ]
            progress(0.5, desc="Running Foundry evaluation for multiple models...")
            run_foundry_eval(endpoint, models, output_pattern)

        elif agent_framework == "OpenAI Agents (GPT-5)":
            progress(0.5, desc="Running OpenAI Agents evaluation...")
            asyncio.run(run_openai_eval(["gpt-5"], output_pattern))

        progress(1, desc="Answer generation complete!")
        return f"Successfully generated answers for {agent_framework}. Check the file list below."
    except Exception as e:
        return f"Error during answer generation for {agent_framework}: {e}"

def run_evals(progress=gr.Progress()):
    """Triggers the cloud evaluation script."""
    progress(0, desc="Starting Evaluation...")
    try:
        input_files = find_files(".", "eval_results_*.jsonl")
        if not input_files:
            return "No 'eval_results_*.jsonl' files found to evaluate. Please generate answers first."
            
        run_cloud_evaluation(input_files, "evaluation_results")
        
        progress(1, desc="Evaluation Complete!")
        return f"Evaluation finished successfully. Check for 'evaluation_results_*.json' files."
    except Exception as e:
        return f"An unexpected error occurred: {e}"

def find_scenario_files():
    """Find all JSON scenario files in any 'scenarios' subdirectory."""
    scenario_files = []
    for scenarios_dir in Path(".").rglob("scenarios"):
        if scenarios_dir.is_dir():
            scenario_files.extend(scenarios_dir.glob("*.json"))
    return [str(f) for f in scenario_files]

def refresh_answer_files():
    """Refreshes the list of answer files."""
    answer_files = find_files(".", "eval_results_*.jsonl")
    choices = [(Path(f).name, f) for f in answer_files] if answer_files else []
    return gr.Dropdown(choices=choices, value=choices[0][1] if choices else None)

def refresh_result_files():
    """Refreshes the list of result files."""
    result_files = find_files(".", "evaluation_results_*.json")
    choices = [(Path(f).name, f) for f in result_files] if result_files else []
    return gr.Dropdown(choices=choices, value=choices[0][1] if choices else None)

def refresh_scenario_files():
    """Refreshes the list of scenario files."""
    scenario_files = find_scenario_files()
    choices = [(Path(f).name, f) for f in scenario_files] if scenario_files else []
    return gr.Dropdown(choices=choices, value=choices[0][1] if choices else None)

def create_quality_evals_tab():
    """Creates the Gradio UI for the quality evaluations tab."""
    with gr.Column():
        
        # Documentation in collapsible accordion
        with gr.Accordion("📚 Documentation - How Evaluations Work", open=False):
            gr.Markdown("""
            ### 📋 Evaluation Process
            1. **Test Scenarios**: Pre-defined test cases that simulate real user interactions
            2. **Answer Generation**: The agent processes scenarios and generates responses
            3. **Multi-Metric Evaluation**: Responses are evaluated using various quality and safety metrics
            
            ### 🎯 Evaluators Explained
            
            #### **Intent & Task Understanding**
            - **Intent Resolution** 🎯: Evaluates if the model accurately understands what the user wants to achieve. Can be run in both pre-deployment tests and production (no ground truth required).
            - **Task Adherence** ✅: Checks if the agent stays on track with the assigned task and follows instructions properly.
            
            #### **Tool Usage**
            - **Tool Call Accuracy** 🔧: Uses LLM-as-judge to assess if the agent calls the right tools with appropriate parameters.
            - **Tool Validation** 🛠️: Custom Python grader that validates tool usage by comparing expected vs actual tool calls. This is implemented using Azure OpenAI Python Grader and checks if the right tools are being invoked (though not necessarily with correct parameters in this demo).
            
            #### **Response Quality**
            - **Fluency** 💬: Evaluates the linguistic quality and readability of responses.
            - **QA Evaluator** 📊: Comprehensive check including:
              - Hallucination detection
              - Groundedness assessment
              - Answer accuracy compared to ground truth (using F1 score and embedding similarity)
            - **Relevance** 🎪: Ensures responses directly address the user's query (beyond just correctness).
            
            #### **Safety & Compliance**
            - **Content Safety** 🛡️: Validates responses for harmful, inappropriate, or offensive content.
            - **Protected Material** ©️: Checks for potential copyright violations or use of protected content.
            
            > **Note**: All evaluators use LLM-as-judge techniques except for the custom Python grader. The safety evaluators are included for completeness but are more relevant when using red-teaming agents.
            """)
        
        gr.Markdown(f"**[View Detailed Reports in Azure AI Studio]({get_azure_evaluation_link()})**")

        # Add scenario explorer section
        with gr.Accordion("📁 Explore Test Scenarios", open=False):
            gr.Markdown("Review the test scenarios that will be used for evaluation:")
            with gr.Row():
                initial_scenario_files = find_scenario_files()
                initial_scenario_choices = [(Path(f).name, f) for f in initial_scenario_files] if initial_scenario_files else []
                scenario_files_dropdown = gr.Dropdown(
                    label="Available Scenario Files",
                    choices=initial_scenario_choices,
                    value=initial_scenario_choices[0][1] if initial_scenario_choices else None
                )
                refresh_scenarios_btn = gr.Button("🔄", size="sm", scale=0)
            scenario_display = gr.Code(language="json", label="Scenario Content", lines=15)
            
            scenario_files_dropdown.change(fn=read_file_content, inputs=scenario_files_dropdown, outputs=scenario_display)
            refresh_scenarios_btn.click(fn=refresh_scenario_files, outputs=scenario_files_dropdown)
            
            # Auto-load content for initially selected scenario
            if initial_scenario_choices:
                scenario_display.value = read_file_content(initial_scenario_choices[0][1])

        with gr.Row():
            with gr.Column(scale=1):
                gr.Markdown("### 1. Generate Evaluation Answers")
                agent_framework_dropdown = gr.Dropdown(
                    label="Select Agent Framework to Generate Answers",
                    choices=["Direct Inference (GPT-2)", "Foundry Agents", "OpenAI Agents (GPT-5)"],
                    value="Foundry Agents"
                )
                generate_button = gr.Button("Generate Answers", variant="secondary")
                generate_status = gr.Textbox(label="Generation Status", interactive=False)
                generate_button.click(
                    fn=generate_answers, 
                    inputs=agent_framework_dropdown, 
                    outputs=generate_status
                )

            with gr.Column(scale=1):
                gr.Markdown("### 2. Run Evaluations")
                run_eval_button = gr.Button("Run Evaluations on Generated Answers", variant="primary")
                eval_status = gr.Textbox(label="Evaluation Status", interactive=False, lines=5)
                run_eval_button.click(fn=run_evals, outputs=eval_status)

        with gr.Row():
            with gr.Column():
                gr.Markdown("### 3. View Generated Answer Files")
                with gr.Row():
                    # Initialize with actual files
                    initial_answer_files = find_files(".", "eval_results_*.jsonl")
                    initial_answer_choices = [(Path(f).name, f) for f in initial_answer_files] if initial_answer_files else []
                    answer_files_dropdown = gr.Dropdown(
                        label="Select an Answer File (.jsonl)",
                        choices=initial_answer_choices,
                        value=initial_answer_choices[0][1] if initial_answer_choices else None
                    )
                    refresh_answers_btn = gr.Button("🔄", size="sm", scale=0)
                answer_display = gr.Code(language="json", label="Answer File Content")
                
                answer_files_dropdown.change(fn=read_jsonl_file, inputs=answer_files_dropdown, outputs=answer_display)
                refresh_answers_btn.click(fn=refresh_answer_files, outputs=answer_files_dropdown)

            with gr.Column():
                gr.Markdown("### 4. View Final Evaluation Results")
                with gr.Row():
                    # Initialize with actual files
                    initial_result_files = find_files(".", "evaluation_results_*.json")
                    initial_result_choices = [(Path(f).name, f) for f in initial_result_files] if initial_result_files else []
                    cloud_results_dropdown = gr.Dropdown(
                        label="Select a Cloud Result File (.json)",
                        choices=initial_result_choices,
                        value=initial_result_choices[0][1] if initial_result_choices else None
                    )
                    refresh_results_btn = gr.Button("🔄", size="sm", scale=0)
                cloud_results_display = gr.Code(language="json", label="Cloud Result Content")
                
                cloud_results_dropdown.change(fn=read_file_content, inputs=cloud_results_dropdown, outputs=cloud_results_display)
                refresh_results_btn.click(fn=refresh_result_files, outputs=cloud_results_dropdown)

        # Auto-load content for initially selected files
        if initial_answer_choices:
            answer_display.value = read_jsonl_file(initial_answer_choices[0][1])
        if initial_result_choices:
            cloud_results_display.value = read_file_content(initial_result_choices[0][1])