import os
import asyncio
from typing import Dict, Any, Callable
from dotenv import load_dotenv

from azure.identity import DefaultAzureCredential
from azure.ai.evaluation.red_team import RedTeam, RiskCategory, AttackStrategy
from .agent import ContosoCareAgent

load_dotenv()


class OpenAISafetyEvaluatorWithGuardrails:
    def __init__(self) -> None:
        self.credential = DefaultAzureCredential(exclude_interactive_browser_credential=False)
        self.project_endpoint = os.getenv("PROJECT_ENDPOINT")
    
    def create_agent_callback(self, model: str) -> Callable[[str], str]:
        agent = ContosoCareAgent(model)
        
        async def async_callback(query: str) -> str:
            result = await agent.process(query)
            
            for call in result.get("actual_tool_calls", []):
                if call["name"] == "message_to_user":
                    message = call["output"].get("message", "")
                    if message:
                        return str(message)
            
            return result.get("message", "I was unable to generate a response.")
        
        def sync_callback(query: str) -> str:
            return asyncio.run(async_callback(query))
        
        return sync_callback
    
    def create_guarded_callback(self) -> Callable[[str], str]:
        return self.create_agent_callback("gpt-5")
    
    async def run_evaluation(self, callback: Callable[[str], str], agent_name: str) -> Dict[str, Any]:
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
        
        return result
    
    async def run_safety_evaluation(self) -> Dict[str, Any]:
        return await self.run_evaluation(
            self.create_guarded_callback(),
            "openai-gpt5-with-guardrails"
        )


async def main() -> None:
    evaluator = OpenAISafetyEvaluatorWithGuardrails()
    await evaluator.run_safety_evaluation()


if __name__ == "__main__":
    asyncio.run(main())
       