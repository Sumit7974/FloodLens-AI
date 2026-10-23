# FloodLens AI — Hackathon Judge Demonstration Script (5–7 Minutes)

**Demonstration Context:** Live Cloud Backend (`https://floodlens-backend-4pt5.onrender.com`)  
**Target Audience:** Hackathon Technical Judges, Disaster Management Stakeholders  
**Demonstration Mode:** `historical_demo` (Deterministic empirical evidence, replay, & simulated response)

---

## Provenance Legend (Judges Notice)
To maintain strict scientific integrity, all visual elements in FloodLens AI are color-coded and badged:
- 🟢 **EMPERICAL SATELLITE DETECTION**: Authentic pre/post Sentinel-2 NDWI optical processing (0.6429 km² newly detected water in Koshi, August 2017).
- 🟡 **HISTORICAL REPLAY**: Terai July 2024 flood simulation with MultiPolygon SAR fixtures and hydrological ML forecasts (+1h, +3h, +6h).
- 🔵 **SIMULATED RESPONSE [TEST ONLY]**: Authority alert drafting/dispatch, citizen assistance triage, and shelter routing. No real-world emergency dispatch is triggered.

---

## 5–7 Minute Step-by-Step Flow

### 00:00 – 01:00 | 1. Problem Statement & Architecture Overview
- **The Problem:** In monsoon-prone basins like Nepal's Koshi and Kamala rivers, emergency managers face critical blindspots between upstream cloudbursts and downstream settlement inundation. Traditional flood response relies on disconnected sensor networks or delayed manual assessments.
- **The Solution:** FloodLens AI provides end-to-end intelligence:
  1. Multi-horizon flood forecasting (+1h, +3h, +6h lead time).
  2. Earth Observation satellite extent processing (Sentinel-2 Optical NDWI and Sentinel-1 SAR).
  3. Spatial settlement and infrastructure exposure analysis via PostgreSQL/PostGIS.
  4. Real-time Authority-to-Citizen closed-loop coordination via REST & WebSockets.
- **Live Infrastructure:** Point out that the backend is live on Render backed by managed PostgreSQL 16 + PostGIS 3.6, operating in strict `historical_demo` mode.

---

### 01:00 – 02:15 | 2. Scientific Optical Processing: Nepal Koshi August 2017 Benchmark
- **Action:** Open event `Nepal Koshi Historical Flood 2017` (`event_nepal_koshi_2017`).
- **Showcase:**
  - Display the satellite observation layer (`GET /api/v1/flood-events/event_nepal_koshi_2017/extent`).
  - **Empirical Metrics:**
    - Newly detected surface water: **0.6429 km²** (6,429 pixels at 10m spatial resolution).
    - Valid cloud/shadow-free observation coverage: **30.85%** (derived from Sentinel-2 Scene Classification Layer SCL).
    - Unobserved / cloud-obscured area: **69.15%**.
  - **Scientific Honesty:** Highlight that uncalibrated model probabilities are kept strictly `null` (not fabricated), and cloud-obscured areas are explicitly demarcated rather than hallucinated.
- **PostGIS Impact:** Show the spatial intersection (`GET /api/v1/flood-events/event_nepal_koshi_2017/settlements`) showing that PostGIS calculated inundation across Biratnagar corridor and eastern Koshi plains.

---

### 02:15 – 03:30 | 3. Multi-Horizon Risk Intelligence: Nepal Terai July 2024 Episode
- **Action:** Switch to `Historical Nepal Terai Monsoon Inundation (July 2024)` (`evt_2024_terai_monsoon`).
- **Showcase:**
  - **Multi-Horizon Forecasts:** View Janakpurdham Sub-Metropolitan (`/api/v1/predictions/latest?location_id=settlement_janakpurdham`):
    - **+1h Horizon:** Moderate Risk (Early surface runoff along secondary streams).
    - **+3h Horizon:** High Risk (Riverbank overtopping anticipated).
    - **+6h Horizon:** Critical Risk (Severe low-lying urban inundation).
  - **Risk Map:** Toggle the interactive GeoJSON prediction layer (`/api/v1/predictions/map`) showing dynamic spatial hazard polygons.
  - **Shelter & Route Hazard Screening:** Demonstrate the route query (`POST /api/v1/routes/assess`):
    - LineString evaluation against active 25m buffer around flood polygons.
    - Status returns `hazards_detected` with safe shelter redirection to `Janakpur Community Higher Secondary School Shelter` (visibly labeled with `demo_labeled` fixture badge).

---

### 03:30 – 05:00 | 4. Authority & Citizen Closed-Loop Coordination
- **Authority Console Workflow:**
  1. **Draft Alert:** Authority creates a localized alert for Janakpurdham Ward 4. The backend automatically injects the `[DEMO / TEST ONLY]` prefix.
  2. **Review & Approve:** Authority two-tier sign-off moves alert from `draft` to `approved`.
  3. **Simulated Dispatch:** Dispatch is executed with `simulated=True`. Backend safety guardrails guarantee no operational gateway is called, and emits a real-time WebSocket event (`evt_dispatch_...`) to the `demo_alerts` and `authority_queue` channels.
- **Citizen App Workflow:**
  1. **Citizen Inundation Alert:** Resident `citizen_janakpur@example.com` receives the official advisory.
  2. **Assistance Request:** Citizen submits an emergency assistance request for 3 elderly individuals requiring boat evacuation (`POST /api/v1/assistance`).
  3. **Authority Triage:** The request appears instantly in the Authority Responder Queue (`GET /api/v1/assistance`).
  4. **Status Update:** Authority assigns Rescue Boat Unit 02 and updates status to `in_progress` (`PATCH /api/v1/assistance/{id}`).
  5. **State Consistency:** Show that refreshing the browser or re-opening the citizen app preserves the updated `in_progress` status.

---

### 05:00 – 06:00 | 5. Decision Support Reports & Downloadable Artifacts
- **Action:** Open Situation Report (`GET /api/v1/flood-events/evt_2024_terai_monsoon/report`).
- **Showcase:**
  - Aggregated damage synthesis: total settlements evaluated (3), settlements affected (2), roads exposed, cropland impacted.
  - Transparent data limitations banner explaining spatial intersection methodology.
  - **Download Artifacts:**
    - Click **Export JSON**: Demonstrates programmatic data interchange for disaster coordination agencies.
    - Click **Export CSV**: Demonstrates spreadsheet compatibility for logistics teams and local district offices.

---

### 06:00 – 07:00 | 6. Conclusion & Hackathon Takeaway
- **Key Takeaways:**
  1. **End-to-End Working System:** Live cloud PostgreSQL 16 / PostGIS 3.6 backend with zero localhost mocks.
  2. **Scientific Provenance:** Real 10m Sentinel-2 satellite optical processing with honest observation coverage limits.
  3. **Human-in-the-Loop Safety:** Clear separation of empirical evidence, historical replay, and simulated emergency response.
  4. **Practical Readiness:** Ready for real-world authority operations and community resilience.

---

## Fallback Contingency Plan (Judge Rehearsal Safeguard)

If live internet connectivity drops or cloud latency spikes during the presentation:
1. **Fallback Data Source:** The repository contains self-contained verified GeoJSON and manifest artifacts:
   - `data/historical_koshi_optical/outputs/historical_koshi_ndwi_flood_extent.geojson`
   - `data/historical_koshi_optical/outputs/historical_koshi_ndwi_manifest.json`
   - `data/historical_koshi_optical/outputs/historical_koshi_ndwi_flood_comparison.png`
2. **Local Rehearsal Runner:** Execute `python scripts/rehearse_live_hackathon_demo.py` directly from the terminal to demonstrate automated live passing checks in 15 seconds.
