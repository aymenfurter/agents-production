import sys
import os
from pathlib import Path

workspace_root = Path(__file__).parent.parent.absolute()
if str(workspace_root) not in sys.path:
    sys.path.insert(0, str(workspace_root))

from variants.foundry_agents.brand_integrity_evals import run_brand_integrity_evaluation

if __name__ == "__main__":
    run_brand_integrity_evaluation()