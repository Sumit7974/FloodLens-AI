"""Wrapper invoking the root scripts/rehearse_live_hackathon_demo.py."""
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))

from scripts.rehearse_live_hackathon_demo import run_demo_rehearsal

if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "https://floodlens-backend-4pt5.onrender.com"
    ok, _, _ = run_demo_rehearsal(url)
    sys.exit(0 if ok else 1)
