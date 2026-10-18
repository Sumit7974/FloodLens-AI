# Flood-Risk Labeling and Multi-Horizon Strategy — FloodLens AI

**Module**: Member 3: AI/ML  
**Study Case Area**: Sapta Koshi River Basin — Barahachhetra / Chatara, Sunsari District, Nepal Terai  
**Horizons**: +1 Hour, +3 Hours, +6 Hours  
**Status**: Day 1 Complete & Verified  

---

## 1. Flood-Risk Classification Hierarchy

To provide actionable, tiered early warnings that align with local disaster management protocols, FloodLens AI implements a 4-tier risk classification system.

### Label-to-Numeric Mapping

| Class Identifier | Risk Label | Severity Level | Operational Meaning | Recommended Community Action |
|---|---|---|---|---|
| **0** | `low` | Baseline | Normal dry/monsoon river stage below threshold levels. | Normal daily activity; routine automated telemetry check. |
| **1** | `moderate` | Alert | Water rising rapidly or heavy catchment rainfall detected ($>50\text{ mm}/24\text{h}$). | Heightened monitoring; riverside farmers advised to secure livestock and gear. |
| **2** | `high` | Warning | River crosses official DHM Warning stage ($6.0\text{ m}$) or extreme rain ($>100\text{ mm}/24\text{h}$). | Official warning; prepare flood-vulnerable households for evacuation; alert emergency teams. |
| **3** | `critical` | Danger | River crosses official DHM Danger stage ($7.0\text{ m}$) or extreme discharge ($>9,000\text{ m}^3/\text{s}$). | Imminent inundation; mandatory evacuation of low-lying settlements; Koshi Barrage gate opening directives. |

---

## 2. Official DHM Warning Thresholds vs. Provisional Thresholds

### 2.1 Official DHM Chatara Benchmark Thresholds (Authoritative)
The Department of Hydrology and Meteorology (DHM), Government of Nepal, establishes official operational benchmarks at the **Sapta Koshi at Chatara (Station 695)**:

* **Normal / Baseline Flow**: $< 4.5\text{ m}$ (discharge $< 4,500\text{ m}^3/\text{s}$)
* **Warning Benchmark (Alert)**: $\mathbf{6.0\text{ m}}$ (discharge $\approx 6,500\text{ m}^3/\text{s}$)  
  *Triggers automated DHM early-warning SMS to registered residents in Sunsari and Saptari districts.*
* **Danger Benchmark**: $\mathbf{7.0\text{ m}}$ (discharge $\approx 9,000\text{ m}^3/\text{s}$)  
  *Triggers sirens, community evacuation coordination, and emergency notification to the Koshi Barrage joint liaison.*
* **Historical Extreme Benchmark**: $> 8.0\text{ m}$ (discharge exceeding $10,500\text{ m}^3/\text{s}$)

### 2.2 Multi-Factor Provisional Thresholds (Experimental Design)
Because upstream cloudburst rainfall leads river stage response by several hours, the ML pipeline defines provisional multi-factor threshold rules when river stage has not yet peaked:

$$\text{Instantaneous Label}(t) = \begin{cases}
\text{critical} & \text{if } W_t \ge 7.0\text{ m} \lor Q_t \ge 9000\text{ m}^3/\text{s} \lor (R_{24h, t} \ge 150\text{ mm} \land W_t \ge 5.5\text{ m}) \\
\text{high} & \text{if } W_t \ge 6.0\text{ m} \lor Q_t \ge 6500\text{ m}^3/\text{s} \lor (R_{24h, t} \ge 100\text{ mm} \land W_t \ge 5.0\text{ m}) \\
\text{moderate} & \text{if } W_t \ge 4.5\text{ m} \lor (W_t \ge 3.5\text{ m} \land \Delta W_{1h, t} \ge 0.5\text{ m/h}) \lor R_{24h, t} \ge 50\text{ mm} \\
\text{low} & \text{otherwise}
\end{cases}$$

> [!WARNING]
> **Explicit Status Note**: The multi-factor rules combining rolling rainfall and rate-of-rise are an **experimental provisional design** implemented for research prototype validation. They are **not yet calibrated or endorsed by the Nepal DHM** as official public warning levels. The system records this caveat in the `limitations` payload array.

---

## 3. Multi-Horizon Forecasting Formulation

FloodLens AI predicts flood risk at three operational horizons:
* $\mathbf{+1\text{ Hour}}$ ($h=1$): Near-immediate flash wave warning for riverside assets.
* $\mathbf{+3\text{ Hours}}$ ($h=3$): Tactical lead-time for local ward evacuations and asset relocation.
* $\mathbf{+6\text{ Hours}}$ ($h=6$): Strategic lead-time for district emergency coordination and shelter activation.

### Mathematical Formulation and Temporal Alignment

At time step $t$, the input feature vector $\mathbf{X}_t$ contains strictly observations recorded at or before timestamp $t$:

$$\mathbf{X}_t = \Big[ R_t, R_{3h, t}, R_{6h, t}, R_{24h, t}, W_t, \Delta W_{1h, t}, Q_t, \hat{R}_{next3h, t}, T_t, H_t, \mathbf{c}_t \Big]$$

Where:
* $R_t$: hourly rainfall at $t$ ($\text{mm}$)
* $R_{kh, t} = \sum_{i=0}^{k-1} R_{t-i}$: backward rolling rainfall accumulation over prior $k$ hours
* $W_t$: river stage observed at $t$ ($\text{m}$)
* $\Delta W_{1h, t} = W_t - W_{t-1}$: rate of stage rise over prior hour ($\text{m/h}$)
* $Q_t$: upstream discharge at $t$ ($\text{m}^3/\text{s}$)
* $\hat{R}_{next3h, t}$: numerical weather prediction (NWP) precipitation forecast issued for $[t, t+3h]$
* $T_t, H_t$: surface temperature and relative humidity at $t$
* $\mathbf{c}_t$: categorical catchment features (season, soil saturation proxy)

The target variable for horizon $+h$ is the ground-truth flood risk state realized at time $t + h$:

$$y_t^{(+h)} = \text{Instantaneous Label}(t + h)$$

### Preventing Temporal Leakage

Temporal leakage is strictly prevented through three design rules:
1. **No Future Observations in Features**: No observed rainfall $R_{t+1}, \dots$, river levels $W_{t+1}, \dots$, or satellite flood extents occurring after time $t$ are included in $\mathbf{X}_t$.
2. **Chronological Data Splitting**: The dataset is partitioned chronologically (75% earlier timestamps for training, 25% later timestamps for evaluation). Random k-fold shuffling is strictly banned.
3. **Leakage-Free Preprocessing**: All scaling statistics (mean, variance) and imputation medians are computed **strictly on the training split** and then applied to the test split.

---

## 4. Handling Missing Labels and End-of-Series Conditions

1. **Trailing Horizon Edge**: For the last $h$ rows of a continuous time-series, future ground-truth observations $t+h$ do not exist. In `ml/src/label_builder.py`, these targets are assigned `NaN` and filtered out during supervised training.
2. **Sensor Telemetry Gaps**: If the target river stage $W_{t+h}$ is missing due to telemetry dropout, the label is marked `unknown` (numeric ID: `-1`) and omitted from training loss calculations.
3. **Class Imbalance Mitigation**: Monsoon flood events are heavily dominated by normal low-risk periods. The training pipeline applies `class_weight="balanced"` to penalize false negatives on rare `high` and `critical` risk events.
