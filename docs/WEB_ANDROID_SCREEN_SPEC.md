# Authority Web & Citizen Android — Screen Specification

## Design principle
One shared backend. Authority users analyze and decide; citizen users see understandable local information and may submit assistance requests. Show observation time and data-quality status on both apps.

## Authority web navigation
| Screen | Main content | Main actions |
|---|---|---|
| Command Centre | Event status, risk summary, active requests, source health | Choose event or location |
| Prediction Centre | +1/+3/+6 hour risk layers, relevant inputs, uncertainty | Change horizon; inspect area |
| Environmental Monitoring | Rainfall, gauges, verified dam bulletins | Inspect recent readings and freshness |
| Terrain Map | 2D/3D terrain, rivers, elevation, assets | Toggle layers; view altitude/elevation |
| Satellite Intelligence | Before/after optical scenes, NDWI/MNDWI, SAR if available | Compare scenes; inspect detected extent |
| Impact Assessment | Flood extent and settlement/asset exposure | Filter settlements; export summary |
| Alerts | Draft, approved, dispatched test alerts | Review, approve, dispatch, audit |
| Assistance | Citizen request queue and authorized locations | Verify, assign, update status |
| Facilities & Routes | Verified shelters/hospitals, road hazard layers | Assess candidate routes; inspect data age |
| Accuracy & Models | Flood mask accuracy, prediction errors, model versions | Inspect metrics; review candidate comparison |
| Reports | Historical event records, map/PDF/CSV exports | Generate/download report |

## Citizen Android navigation
| Screen | Main content | Main actions |
|---|---|---|
| My Area | Latest forecast risk and last-update timestamp | Select/share location with consent |
| Forecast | +1/+3/+6 hour risk estimates, uncertainty | View horizon explanations |
| Risk Map | Clear 2D map; optional 3D terrain | View locally relevant layers |
| Alerts | Approved warnings and issue time | Open full alert details |
| Safe Places | Verified designated shelters | See details, status and map position |
| Hospitals | Verified/known hospital information | View location and known access limitations |
| Routes | Candidate routes, known flood/road restrictions | Inspect why route was suggested |
| Request Help | Minimum required information, location | Submit request |
| My Requests | User's own request status | Track changes |
| Safety & Help | Verified preparedness info and emergency contacts | Open guidance |

## Primary user flows
1. **Prediction → warning**: forecast saved → backend event → authority review → test dispatch → Android alert → REST fetches verified alert.
2. **Flood mapping**: upload/select imagery → processing job → observed flood extent → settlement intersection → report and map-layer update.
3. **Citizen request**: Android submit → durable request record → authorized authority notification → officer reviews/updates → citizen sees status.
4. **Forecast evaluation**: retrieve issue-time forecast → align subsequent observation → calculate relevant metrics → display limitations.

## UI states required on every data screen
Loading; empty; stale data; insufficient evidence; failed API; permission denied; disconnected WebSocket; historical replay/demo label.

## 3D guidance
3D terrain is for visualization, **not** automatically a depth model. Android uses lightweight 2D first to ensure accessibility and performance; optional 3D follows device capability.
