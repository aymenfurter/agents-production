import os
import json
import argparse
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

from dotenv import load_dotenv
from azure.ai.evaluation import evaluate
from azure.ai.evaluation import (
    AzureOpenAIModelConfiguration,
    AzureOpenAIPythonGrader,
    AzureAIProject,
    FluencyEvaluator,
    QAEvaluator,
    IntentResolutionEvaluator,
    TaskAdherenceEvaluator,
    ToolCallAccuracyEvaluator,
    RelevanceEvaluator,
    ContentSafetyEvaluator,
    ProtectedMaterialEvaluator,
)
from azure.identity import DefaultAzureCredential

# Handle both direct execution and module import
try:
    from .tool_utils import (
        extract_message_from_tool_calls,
        extract_tool_names_from_calls,
        build_tool_definitions,
        format_tool_calls,
    )
except ImportError:
    from tool_utils import (
        extract_message_from_tool_calls,
        extract_tool_names_from_calls,
        build_tool_definitions,
        format_tool_calls,
    )

load_dotenv()


def load_eval_data(file_path: str) -> List[Dict[str, Any]]:
    """Read JSONL input and return a list of dict rows."""
    with open(file_path, "r") as f:
        return [json.loads(line) for line in f if line.strip()]


def resolve_input_files(pattern: str) -> List[str]:
    """Resolve input files matching a pattern."""
    base = Path(__file__).parent
    
    matches = list(Path.cwd().glob(pattern))
    if not matches:
        matches = list(base.glob(pattern))
    if not matches:
        matches = list((base.parent).glob(pattern))

    return [str(p) for p in matches]


def prepare_evaluation_dataset(eval_data: List[Dict[str, Any]], output_file: str = "eval_data.jsonl") -> str:
    """Create a flattened JSONL dataset the Azure evaluators expect."""
    handbook_text = Path("contoso-handbook.md").read_text() if Path("contoso-handbook.md").exists() else ""
    with open(output_file, "w") as f:
        for item in eval_data:
            expected_msg = extract_message_from_tool_calls(item.get("expected_tool_calls", []))
            actual_msg = extract_message_from_tool_calls(item.get("actual_tool_calls", []))
            expected_tools = extract_tool_names_from_calls(item.get("expected_tool_calls", []))
            actual_tools = extract_tool_names_from_calls(item.get("actual_tool_calls", []))

            # last user message becomes the query
            query = ""
            conversation_history = []
            for m in item.get("conversation", []):
                if m.get("role") == "user":
                    query = m.get("content", "")
                conversation_history.append(f"{m.get('role', '')}: {m.get('content', '')}")

            tool_definitions = build_tool_definitions(item.get("actual_tool_calls", []))
            tool_calls_formatted = format_tool_calls(item.get("actual_tool_calls", []))

            row = {
                "id": item.get("id", "unknown"),
                "description": item.get("description", ""),
                "query": query,
                "ground_truth": expected_msg or "",
                "response": actual_msg or item.get("response", ""),
                "expected_tools": expected_tools,
                "actual_tools": actual_tools,
                "conversation": json.dumps(item.get("conversation", [])),
                "conversation_text": "\n".join(conversation_history),
                "context": handbook_text,
                "tool_definitions": tool_definitions,
                "tool_calls": tool_calls_formatted,
            }
            f.write(json.dumps(row) + "\n")
    return output_file


def run_cloud_evaluation(input_files: List[str], output_pattern: str) -> int:
    """Run cloud evaluation for multiple model result files."""
    for input_file in input_files:
        model_name = ""
        filename = Path(input_file).stem
        if "_gpt-4_1" in filename or "_gpt-4.1" in filename:
            model_name = "gpt-4.1"
        elif "_gpt-35-turbo" in filename or "_gpt_35_turbo" in filename:
            model_name = "gpt-35-turbo"
        elif "_gpt-2" in filename or "_gpt_2" in filename:
            model_name = "gpt-2"
        elif "_gpt-5" in filename or "_gpt_5" in filename:
            model_name = "gpt-5"

        print(f"Evaluating results from model: {model_name}")
        
        # Create model-specific output file
        base_name = Path(output_pattern).stem
        output_file = f"{base_name}_{model_name.replace('.', '_')}.json"
        
        # Prepare and run evaluation
        data_file = prepare_evaluation_dataset(
            load_eval_data(input_file), 
            f"eval_data_{model_name.replace('.', '_')}.jsonl"
        )
        
        openai_model_config = AzureOpenAIModelConfiguration(
            azure_endpoint=os.getenv("EVAL_MODEL_ENDPOINT"),
            api_key=os.getenv("EVAL_MODEL_API_KEY"),
            azure_deployment=os.getenv("EVAL_MODEL_DEPLOYMENT", "gpt-4.1"),
            api_version=os.getenv("AZURE_API_VERSION", "2024-02-15-preview"),
        )
        
        azure_ai_project = AzureAIProject(
            subscription_id=os.getenv("AZURE_SUBSCRIPTION_ID"),
            resource_group_name=os.getenv("AZURE_RESOURCE_GROUP"),
            project_name=os.getenv("AZURE_PROJECT_NAME"),
        )
        
        credential = DefaultAzureCredential(exclude_interactive_browser_credential=True)
        
        evaluators = {
            "intent_resolution": IntentResolutionEvaluator(model_config=openai_model_config, threshold=3),
            "task_adherence": TaskAdherenceEvaluator(model_config=openai_model_config, threshold=3),
            "tool_call_accuracy": ToolCallAccuracyEvaluator(model_config=openai_model_config, threshold=3),
            "fluency": FluencyEvaluator(model_config=openai_model_config, threshold=3),
            "qa": QAEvaluator(model_config=openai_model_config, threshold=3),
            "relevance": RelevanceEvaluator(model_config=openai_model_config, threshold=3),
            "tool_validation": AzureOpenAIPythonGrader(
                model_config=openai_model_config,
                name="tool_validation",
                image_tag="2025-05-08",
                pass_threshold=0.8,
                source="""
def grade(sample: dict, item: dict) -> float:
    expected_str = str(item.get('expected_tools', ''))
    actual_str = str(item.get('actual_tools', ''))
    
    # Handle empty cases
    if not expected_str.strip() and not actual_str.strip():
        return 1.0
    
    if not expected_str.strip() or not actual_str.strip():
        return 0.0
    
    # Parse tool names
    expected_tools = [tool.strip() for tool in expected_str.split(',') if tool.strip()]
    actual_tools = [tool.strip() for tool in actual_str.split(',') if tool.strip()]
    
    # Convert to sets for exact comparison
    expected_set = set(expected_tools)
    actual_set = set(actual_tools)
    
    # Exact match gets perfect score
    if expected_set == actual_set:
        return 1.0
    
    # No overlap gets zero
    intersection = expected_set & actual_set
    if not intersection:
        return 0.0
    
    # Partial score based on intersection over union (Jaccard similarity)
    union = expected_set | actual_set
    score = len(intersection) / len(union)
    
    return score
""",
            ),
            "content_safety": ContentSafetyEvaluator(
                azure_ai_project=azure_ai_project,
                credential=credential,
                parallel=True
            ),
            "protected_material": ProtectedMaterialEvaluator(
                azure_ai_project=azure_ai_project,
                credential=credential
            ),
        }
        
        evaluator_config = {
            "intent_resolution": {
                "column_mapping": {"query": "${data.query}", "response": "${data.response}", "tool_definitions": "${data.tool_definitions}"}
            },
            "task_adherence": {
                "column_mapping": {"query": "${data.query}", "response": "${data.response}", "tool_definitions": "${data.tool_definitions}"}
            },
            "tool_call_accuracy": {
                "column_mapping": {"query": "${data.query}", "tool_definitions": "${data.tool_definitions}", "tool_calls": "${data.tool_calls}"}
            },
            "fluency": {"column_mapping": {"response": "${data.response}"}},
            "qa": {
                "column_mapping": {
                    "query": "${data.query}",
                    "context": "${data.context}",
                    "response": "${data.response}",
                    "ground_truth": "${data.ground_truth}",
                }
            },
            "relevance": {"column_mapping": {"query": "${data.query}", "response": "${data.response}"}},
            "tool_validation": {"column_mapping": {"expected_tools": "${data.expected_tools}", "actual_tools": "${data.actual_tools}"}},
            "content_safety": {
                "column_mapping": {
                    "query": "${data.query}",
                    "response": "${data.response}"
                }
            },
            "protected_material": {
                "column_mapping": {
                    "query": "${data.query}",
                    "response": "${data.response}"
                }
            },
        }
        
        # Run evaluation
        evaluate(
            data=data_file,
            evaluation_name=f"ContosoCare Agent Evaluation - {model_name} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            evaluators=evaluators,
            evaluator_config=evaluator_config,
            output_path=output_file,
            azure_ai_project=azure_ai_project,
        )
        
        # Clean up temporary file
        Path(data_file).unlink(missing_ok=True)
        
        print(f"Completed evaluation for {model_name}, results saved to {output_file}")
    
    return 0


def main():
    parser = argparse.ArgumentParser(description="Run ContosoCare Agent evaluation (quality and safety)")
    parser.add_argument("--file", "-f", default="eval_results_*.jsonl", 
                       help="Input JSONL file pattern (supports wildcards)")
    parser.add_argument("--output", "-o", default="evaluation_results", 
                       help="Output file pattern (model name will be appended)")
    args = parser.parse_args()
    
    # Find all matching input files
    input_files = resolve_input_files(args.file)
    
    if not input_files:
        print(f"No input files found matching pattern: {args.file}")
        return 1
    
    print(f"Found {len(input_files)} input file(s) to evaluate:")
    for f in input_files:
        print(f"  - {f}")
    
    return run_cloud_evaluation(input_files, args.output)
    
    return run_cloud_evaluation(input_files, args.output)
        