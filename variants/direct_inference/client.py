import urllib.request
import json
import time
import os
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv

class AzureMLError(Exception):
    """Custom exception for Azure ML related errors"""
    pass

class AzureMLClient:
    """Azure ML client for making requests to model endpoints"""
    
    def __init__(self, endpoint_url: str, api_key: Optional[str] = None):
        self.endpoint_url = endpoint_url
        self.api_key = api_key or os.getenv('AZURE_ML_API_KEY')
        if not self.api_key:
            raise ValueError("API key must be provided or set in AZURE_ML_API_KEY environment variable")
    
    def predict(self, prompt: str, max_retries: int = 3) -> str:
        """
        Make a prediction request to Azure ML endpoint.
        
        Args:
            prompt: Text input for the model
            max_retries: Maximum number of retry attempts
        
        Returns:
            Response text from the model
        """
        # Simple data format
        data = {
            "inputs": prompt,
            "parameters": {
                "max_length": 100,
                "temperature": 0.1,
                "do_sample": True
            }
        }
        
        headers = {
            'Content-Type': 'application/json', 
            'Accept': 'application/json', 
            'Authorization': f'Bearer {self.api_key}'
        }
        
        for attempt in range(max_retries):
            try:
                body = json.dumps(data).encode('utf-8')
                req = urllib.request.Request(self.endpoint_url, body, headers)
                
                response = urllib.request.urlopen(req, timeout=30)
                result = response.read().decode('utf-8')
                
                # Try to parse as JSON and extract text
                try:
                    result_json = json.loads(result)
                    if isinstance(result_json, list) and len(result_json) > 0:
                        # Handle list response - get first item
                        first_item = result_json[0]
                        if isinstance(first_item, dict) and 'generated_text' in first_item:
                            return first_item['generated_text']
                        return str(first_item)
                    elif isinstance(result_json, dict):
                        # Try common response field names
                        for field in ['generated_text', 'text', 'output', 'response']:
                            if field in result_json:
                                return str(result_json[field])
                        return str(result_json)
                    return str(result_json)
                except json.JSONDecodeError:
                    # If not JSON, return as-is
                    return result
                    
            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff
                    continue
                else:
                    raise AzureMLError(f"All retry attempts failed: {str(e)}")
        
        raise AzureMLError("All retry attempts failed")
