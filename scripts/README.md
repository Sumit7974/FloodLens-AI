# FloodLens AI — Scripts Directory

This directory contains standalone execution and verification scripts for the FloodLens AI subsystem.

## Available Scripts

### 1. Offline Candidate Model Retraining Experiment (Day 5)
Executes the sandboxed offline retraining experiment (`candidate-leakfree-v1`) with all lookahead leakage removed and strict 3-way chronological partitioning:
```bash
python scripts/train_leakfree_candidate.py
```
- **Output Artifacts**: `ml/models/experiments/`
- **Output Report**: `reports/day5_retraining_experiment.md` and `ml/reports/retraining_experiment_summary.json`
- **Safety**: Sandboxed offline only. Does not overwrite deployed models.

### 2. Temporal Data-Leakage Audit
Performs a programmatic temporal leakage audit across every feature in the forecasting pipeline:
```bash
python ml/src/leakage_audit.py
```
- **Output Report**: `reports/day5_temporal_leakage_audit.md`

### 3. Baseline Freeze & Tamper-Detection Verification
Generates cryptographic SHA-256 baseline manifests and verifies file integrity:
```bash
python ml/src/baseline_freeze.py
```
- **Output Report**: `reports/day5_baseline_freeze.md`

### 4. Day 3 Demonstration Verification
Executes backend API verification and safety authorization flows:
```bash
python scripts/demo_day3_flows.py
```
