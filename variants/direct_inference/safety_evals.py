import os
import asyncio
from typing import Dict, Any, Callable
from dotenv import load_dotenv

from azure.identity import DefaultAzureCredential
from azure.ai.evaluation.red_team import RedTeam, RiskCategory, AttackStrategy
from azure.ai.contentsafety import ContentSafetyClient
from azure.ai.contentsafety.models import AnalyzeTextOptions
from azure.core.credentials import AzureKeyCredential

from .agent import DirectInferenceAgent

load_dotenv()


class SafetyThresholds:
    """Define safety thresholds for content analysis."""
    THRESHOLD = 2


class DirectInferenceSafetyEvaluatorWithGuardrails:
    """Safety evaluator with content safety guardrails for DirectInferenceAgent."""
    
    def __init__(self) -> None:
        self.credential = DefaultAzureCredential(exclude_interactive_browser_credential=False)
        self.project_endpoint = os.getenv("PROJECT_ENDPOINT")
        self.azure_ml_endpoint = os.getenv("AZURE_ML_ENDPOINT")
        
        if not self.project_endpoint:
            raise ValueError("PROJECT_ENDPOINT environment variable is required")
        if not self.azure_ml_endpoint:
            raise ValueError("AZURE_ML_ENDPOINT environment variable is required")
        
        content_safety_endpoint = os.getenv("CONTENT_SAFETY_ENDPOINT")
        content_safety_key = os.getenv("CONTENT_SAFETY_KEY")
        
        if not content_safety_endpoint or not content_safety_key:
            raise ValueError("CONTENT_SAFETY_ENDPOINT and CONTENT_SAFETY_KEY are required")
        
        self.content_safety_client = ContentSafetyClient(
            endpoint=content_safety_endpoint,
            credential=AzureKeyCredential(content_safety_key)
        )
    
    def analyze_content_safety(self, text: str) -> Dict[str, Any]:
        try:
            response = self.content_safety_client.analyze_text(
                AnalyzeTextOptions(text=text)
            )
            
            categories = {
                item.category.lower(): item.severity 
                for item in response.categories_analysis
            }
            
            violations = []
            safe = True
            
            for cat, sev in categories.items():
                if sev >= SafetyThresholds.THRESHOLD:
                    safe = False
                    violations.append(f"{cat}: {sev}")
            
            return {'safe': safe, 'violations': violations}
            
        except Exception as e:
            print(f"Content safety analysis failed: {e}")
            return {'safe': False, 'violations': ['Analysis failed']}
    
    def create_agent_callback_with_guardrails(self) -> Callable[[str], str]:
        agent = DirectInferenceAgent(self.azure_ml_endpoint)
        
        def callback(query: str) -> str:
            if not query or not query.strip():
                return "I cannot process empty requests."
            
            # Input safety check
            input_safety = self.analyze_content_safety(query)
            if not input_safety['safe']:
                return "I cannot process this request due to safety concerns."
            
            try:
                result = agent.process(query)
                response = result.get("message", "") if result else ""
                
                if not response:
                    return "I was unable to generate a response."
                
                # Output safety check
                output_safety = self.analyze_content_safety(str(response))
                if not output_safety['safe']:
                    return "I cannot provide this response due to safety concerns."
                
                return str(response)
                
            except Exception:
                return "I encountered an error processing your request."
        
        return callback
    
    def create_unguarded_callback(self) -> Callable[[str], str]:
        agent = DirectInferenceAgent(self.azure_ml_endpoint)
        
        def callback(query: str) -> str:
            if not query or not query.strip():
                return "I cannot process empty requests."
            
            try:
                result = agent.process(query)
                response = result.get("message", "") if result else ""
                return str(response) if response else "I was unable to generate a response."
            except Exception:
                return "I encountered an error processing your request."
        
        return callback
    
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
            self.create_agent_callback_with_guardrails(),
            "direct-gpt2-with-guardrails"
        )
        
        results['without_guardrails'] = await self.run_evaluation(
            self.create_unguarded_callback(),
            "direct-gpt2-unguarded"
        )
        
        print("Comparative evaluation complete!")
        return results


async def main() -> None:
    try:
        evaluator = DirectInferenceSafetyEvaluatorWithGuardrails()
        await evaluator.run_comparative_evaluation()
    except Exception as e:
        print(f"Error during evaluation: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())