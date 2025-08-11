import os
import asyncio
from typing import Dict, Any, Callable
from dotenv import load_dotenv

from azure.identity import DefaultAzureCredential
from azure.ai.evaluation.red_team import RedTeam, RiskCategory, AttackStrategy
from .agent import ContosoCareAgent

load_dotenv()


class FoundrySafetyEvaluatorWithGuardrails:
    """Safety evaluator comparing guarded vs unguarded foundry agent configurations."""
    
    def __init__(self) -> None:
        self.credential = DefaultAzureCredential(exclude_interactive_browser_credential=False)
        self.project_endpoint = os.getenv("PROJECT_ENDPOINT")
        
        if not self.project_endpoint:
            raise ValueError("PROJECT_ENDPOINT environment variable is required")
    
    def create_agent_callback(self, model: str) -> Callable[[str], str]:
        agent = ContosoCareAgent(self.project_endpoint, model)
        
        def callback(query: str) -> str:
            if not query or not query.strip():
                return "I cannot process empty requests."
                
            try:
                result = agent.process(query)
                
                for call in result.get("actual_tool_calls", []):
                    if call["name"] == "message_to_user":
                        message = call["output"].get("message", "")
                        if message:
                            return str(message)
                
                return "I was unable to generate a response."
                
            except Exception:
                return "I encountered an error processing your request."
        
        return callback
    
    def create_guarded_callback(self) -> Callable[[str], str]:
        return self.create_agent_callback("gpt-4.1")
    
    def create_unguarded_callback(self) -> Callable[[str], str]:
        return self.create_agent_callback("gpt-4.1-no-shields")
    
    async def run_evaluation(self, callback: Callable[[str], str], agent_name: str) -> Dict[str, Any]:
        print(f"Starting evaluation for: {agent_name}")
        
        risk_categories = [
            RiskCategory.HateUnfairness,
            RiskCategory.Violence,
            RiskCategory.Sexual,
            RiskCategory.SelfHarm
        ]
        
        attack_strategies = [
            AttackStrategy.Jailbreak,
            AttackStrategy.Base64,
            AttackStrategy.ROT13
        ]
        
        red_team = RedTeam(
            azure_ai_project=self.project_endpoint,
            credential=self.credential,
            risk_categories=risk_categories,
            num_objectives=3,
            output_dir=f"safety_outputs/{agent_name}/"
        )
        
        result = await red_team.scan(
            target=callback,
            scan_name=f"Safety-Scan-{agent_name}",
            attack_strategies=attack_strategies
        )
        
        output_path = os.path.abspath(f"safety_outputs/{agent_name}/")
        print(f"Evaluation complete for {agent_name}")
        print(f"Results saved to: {output_path}")
        
        return result
    
    async def run_comparative_evaluation(self) -> Dict[str, Any]:
        print("Starting comparative safety evaluation...")
        
        results = {}
        
        results['with_guardrails'] = await self.run_evaluation(
            self.create_guarded_callback(),
            "foundry-gpt4_1-with-guardrails"
        )
        
        results['without_guardrails'] = await self.run_evaluation(
            self.create_unguarded_callback(),
            "foundry-gpt4_1-no-shields"
        )
        
        print("Comparative evaluation complete!")
        return results


async def main() -> None:
    try:
        evaluator = FoundrySafetyEvaluatorWithGuardrails()
        await evaluator.run_comparative_evaluation()
    except Exception as e:
        print(f"Error during evaluation: {e}")
        raise