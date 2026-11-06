"""Starts the website. The project lives in voting_desk/."""
import subprocess
import sys
from pathlib import Path

sys.exit(subprocess.run([sys.executable, str(Path(__file__).parent / "voting_desk" / "app.py"), *sys.argv[1:]]).returncode)
