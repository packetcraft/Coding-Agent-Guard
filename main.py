#!/usr/bin/env python3
import sys
from pathlib import Path

# Add the project root to sys.path so we can import coding_agent_guard
root = Path(__file__).parent
sys.path.append(str(root))

from coding_agent_guard.core.guard import main

if __name__ == "__main__":
    main()
