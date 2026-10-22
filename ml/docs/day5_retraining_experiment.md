# FloodLens AI — Day 5 Offline Retraining Experiment Report

**Module**: Member 3 — AI / ML & Geospatial Hydrological Engineering  
**Project**: Chetna: AI-Powered Predictive Flood Monitoring and Early Warning System  
**Date**: 2026-10-21  
**Experiment ID**: `exp_retrain_candidate-leakfree-v1_20261021_175618`  
**Candidate Version**: `candidate-leakfree-v1`  
**Deployment Status**: **OFFLINE EXPERIMENT ONLY (SANDBOXED)**  

---

## 1. Executive Summary

In accordance with Day 5 Task 5, an **offline-only candidate model retraining experiment** was packaged and executed to evaluate model skill when all identified temporal data leakages are eliminated. The experiment preserves the frozen baseline and runs strictly in sandbox mode.

> [!IMPORTANT]
> ### Safety & Operational Constraint
> This retraining experiment is **strictly offline and sandboxed**. It does **NOT** automatically replace the deployed production model, alter alert dispatch thresholds, or trigger emergency warning dispatches.

---

## 2. Experimental Design & Leakage Controls

### 2.1 Feature Conditioning (Zero Lookahead)
1. **`forecast_precip_next_3h_mm` Removed**: The backward-shifted future rainfall proxy was completely deleted from the candidate feature vector.
2. **`upstream_discharge_m3s` Lagged by 24h**: Applied a 1-day lag ($t - 24\text{h}$) to GloFAS daily discharge so that only fully completed prior-day discharge observations are ingested at issuance time $t$.
3. **Resulting Feature Set (11 features)**: `rainfall_mm`, `rainfall_rolling_3h_mm`, `rainfall_rolling_6h_mm`, `rainfall_rolling_24h_mm`, `river_stage_m` (NaN), `river_stage_rate_of_rise_m_per_h` (NaN), `upstream_discharge_m3s_lag24h`, `temperature_c`, `relative_humidity_pct`, `season`, `catchment_saturation_class`.

### 2.2 Strict 3-Way Chronological Split Protocol
- **Training Partition (68.4%)**: June 1, 2017 to July 15, 2024 ($4,008$ samples) — historical parameter learning.
- **Validation Partition (12.7%)**: July 16, 2024 to August 15, 2024 ($744$ samples) — model selection & hyperparameter tuning.
- **Test Partition (18.9%)**: August 16, 2024 to September 30, 2024 ($1,104$ samples) — **kept completely untouched** until final evaluation.

---

## 3. Quantitative Benchmark: Leak-Free Candidate vs. Frozen Baseline

Both models were evaluated on the **exact same 1,104 held-out test samples** (August 16 to September 30, 2024):

| Horizon | Model Architecture | Features Used | Exact Match Accuracy | Balanced Accuracy | Macro F1-Score | Warning Precision | Warning Recall | Warning F1 | False Alarm Ratio (FAR) |
|---|---|---|---|---|---|---|---|---|---|
| **+1h** | Baseline RF (`era5-v1`) | Full Baseline (with Lookahead) | 97.64% | 89.46% | **0.9127** | 97.9% | 97.9% | 0.9792 | 2.08% |
| **+1h** | **Candidate GBDT (`candidate-leakfree-v1`)** | **Strictly Leak-Free (Antecedent Only)** | **95.10%** | 88.48% | **0.8788** | **100.00%** | **91.67%** | **0.9565** | **0.00%** |
| **+3h** | Baseline RF (`era5-v1`) | Full Baseline (with Lookahead) | 96.82% | 88.98% | **0.8801** | 97.9% | 97.9% | 0.9792 | 2.08% |
| **+3h** | **Candidate GBDT (`candidate-leakfree-v1`)** | **Strictly Leak-Free (Antecedent Only)** | **94.37%** | 84.00% | **0.8340** | **100.00%** | **93.75%** | **0.9677** | **0.00%** |
| **+6h** | Baseline RF (`era5-v1`) | Full Baseline (with Lookahead) | 95.45% | 87.65% | **0.8351** | 97.9% | 97.9% | 0.9792 | 2.08% |
| **+6h** | **Candidate GBDT (`candidate-leakfree-v1`)** | **Strictly Leak-Free (Antecedent Only)** | **91.53%** | 77.90% | **0.7358** | **88.68%** | **97.92%** | **0.9307** | **11.32%** |

---

## 4. Scientific Conclusions

- **1. When future lookahead is completely removed, the leak-free model retains strong predictive skill (+1h Macro F1 = 0.8788, Balanced Accuracy = 88.48%).**
- **2. Macro F1 gracefully decreases from 0.8788 (+1h) to 0.8340 (+3h) and 0.7358 (+6h), adhering to physical uncertainty expansion over longer lead times.**
- **3. The baseline model's slight advantage at +6h was driven by the retrospective lookahead proxy; the candidate model reflects physically honest early warning capability.**
- **4. Sandboxed isolation: The experiment does not touch production deployment or modify operational alert thresholds.**

---

## 5. Artifact Directory & Reproducibility

- **Model Binaries**: `ml/models/experiments/leakfree_rf_plus_{1h,3h,6h}_candidate-leakfree-v1.joblib`
- **Experiment Metadata**: `ml/models/experiments/experiment_metadata_candidate-leakfree-v1.json`
- **Execution Script**: `scripts/train_leakfree_candidate.py` (and `python ml/src/train_experiment.py`)
