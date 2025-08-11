#!/usr/bin/env python3
import sys
import os
from pathlib import Path

workspace_root = Path(__file__).parent.parent.absolute()
if str(workspace_root) not in sys.path:
    sys.path.insert(0, str(workspace_root))

from variants.direct_inference.agent import main

if __name__ == "__main__":
    sys.exit(main())
