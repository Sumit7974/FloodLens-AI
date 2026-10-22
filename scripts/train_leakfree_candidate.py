"""Reproducible runner script for the Day 5 offline candidate retraining experiment."""
import sys
from pathlib import Path

# Ensure repository root is on sys.path
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from ml.src.train_experiment import run_offline_retraining_experiment

if __name__ == "__main__":
    print("[Day 5] Starting offline candidate retraining experiment (candidate-leakfree-v1)...")
    rep = run_offline_retraining_experiment()
    print(f"\nExperiment {rep.experiment_id} finished successfully.")
    print(f"Candidate Version: {rep.candidate_version}")
    print(f"Safety constraint: Sandboxed in ml/models/experiments/ (cannot replace production).")
