from pathlib import Path
import json, os
from urllib.parse import urlparse

DEFAULT_URL = "https://ai.azure.com"

def find_files(start_dir, pattern):
    base = Path(__file__).resolve().parents[1] / start_dir
    return [] if not base.exists() else sorted(map(str, base.rglob(pattern)))

def read_file_content(filepath):
    p = Path(filepath) if filepath else None
    if not p or not p.exists(): return "File not found or no file selected."
    try:
        if p.suffix == ".json":
            with p.open(encoding="utf-8") as f: return json.dumps(json.load(f), indent=2)
        return p.read_text(encoding="utf-8")
    except Exception as e:
        return f"Error reading file: {e}"

def read_jsonl_file(filepath):
    p = Path(filepath) if filepath else None
    if not p or not p.exists(): return "File not found or no file selected."
    try:
        with p.open(encoding="utf-8") as f:
            return json.dumps([json.loads(l) for l in f if l.strip()], indent=2)
    except Exception as e:
        return f"Error reading JSONL file: {e}"

def _parse_resource_project(endpoint):
    try:
        u = urlparse(endpoint); h, path = u.hostname, u.path
        if h and ".services.ai.azure.com" in h and path and path.startswith("/api/projects/"):
            return h.split(".services.ai.azure.com")[0], path.split("/api/projects/")[1]
    except Exception:
        pass
    return None, None

def _wsid_account(sub, rg, resource, project):
    return f"/subscriptions/{sub}/resourceGroups/{rg}/providers/Microsoft.CognitiveServices/accounts/{resource}/projects/{project}"

def _wsid_ml(sub, rg, ws):
    return f"/subscriptions/{sub}/resourceGroups/{rg}/providers/Microsoft.MachineLearningServices/workspaces/{ws}"

def get_azure_ai_studio_link():
    sub, rg, tid, endpoint = os.getenv("AZURE_SUBSCRIPTION_ID"), os.getenv("AZURE_RESOURCE_GROUP"), os.getenv("AZURE_TENANT_ID"), os.getenv("PROJECT_ENDPOINT")
    if not all([sub, rg, tid, endpoint]): return DEFAULT_URL
    resource, project = _parse_resource_project(endpoint)
    if not resource or not project: return DEFAULT_URL
    return f"{DEFAULT_URL}/resource/build/redteaming?wsid={_wsid_account(sub, rg, resource, project)}&tid={tid}"

def get_azure_monitoring_link():
    sub, rg, tid, endpoint = os.getenv("AZURE_SUBSCRIPTION_ID"), os.getenv("AZURE_RESOURCE_GROUP"), os.getenv("AZURE_TENANT_ID"), os.getenv("PROJECT_ENDPOINT")
    if not all([sub, rg, tid, endpoint]): return DEFAULT_URL
    resource, project = _parse_resource_project(endpoint)
    if not resource or not project: return DEFAULT_URL
    return f"{DEFAULT_URL}/observability/applicationAnalytics?wsid={_wsid_account(sub, rg, resource, project)}&tid={tid}"

def get_azure_evaluation_link():
    sub, rg, ws, tid = os.getenv("AZURE_SUBSCRIPTION_ID"), os.getenv("AZURE_RESOURCE_GROUP"), os.getenv("AZURE_PROJECT_NAME"), os.getenv("AZURE_TENANT_ID")
    if not all([sub, rg, ws, tid]): return DEFAULT_URL
    return f"{DEFAULT_URL}/build/evaluation?wsid={_wsid_ml(sub, rg, ws)}&tid={tid}"