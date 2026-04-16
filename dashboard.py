#!/usr/bin/env python3
import sys
import subprocess
from pathlib import Path

# Add the project root to sys.path
root = Path(__file__).parent
sys.path.append(str(root))

def main():
    dashboard_path = root / "coding_agent_guard" / "ui" / "dashboard.py"
    try:
        # Using sys.executable -m streamlit is more robust across platforms
        subprocess.run([sys.executable, "-m", "streamlit", "run", str(dashboard_path)], check=True)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Error starting dashboard: {e}")

if __name__ == "__main__":
    main()
