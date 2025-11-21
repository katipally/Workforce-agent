"""Backend package for Workforce Agent.

This module sets up import paths for the entire backend package to ensure
consistent module resolution across all scripts and API endpoints.
"""

import sys
from pathlib import Path

# Get backend root directory
BACKEND_ROOT = Path(__file__).parent
CORE_ROOT = BACKEND_ROOT / "core"
PROJECT_ROOT = BACKEND_ROOT.parent

# Add to sys.path if not already present (do this ONCE at package level)
for path in [BACKEND_ROOT, CORE_ROOT]:
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

__version__ = "1.0.0"
