# FloodLens AI — Documentation Index

This folder is the project's central reference for development of the **authority web dashboard**, **citizen Android app**, and **shared AI/GIS backend**.

## Existing planning documents (searchable Markdown)
| Document | File |
| --- | --- |
| Complete Project Framework v1.0 | [Framework](FloodLens_AI_Complete_Project_Framework_v1.md) |
| Software Requirements Specification v1.0 | [SRS](FloodLens_AI_SRS_v1.md) |
| Technical Architecture & API Design v1.0 | [Architecture](FloodLens_AI_Technical_Architecture_API_Design_v1.md) |
| Master Pre-development Blueprint v1.0 | [Master Blueprint](FloodLens_AI_Master_Predevelopment_Blueprint_v1.md) |
| Day-wise Team Work Plan | [Work Plan](FloodLens_AI_Day_Wise_Team_Work_Plan.md) |

These five text companions were extracted from the original PDFs; some table layouts may differ from the originals.

## Additional implementation-ready documents
| Area | File |
| --- | --- |
| Data acquisition, feasibility and model readiness | [Dataset & Model Readiness](DATASET_AND_MODEL_READINESS.md) |
| Authority web and citizen Android screen requirements | [Web/Android Screen Specification](WEB_ANDROID_SCREEN_SPEC.md) |
| Database records, REST APIs and WebSocket contracts | [Database/API/Event Contracts](DATABASE_API_EVENT_CONTRACTS.md) |
| Functional and model validation tests | [Testing & Validation Plan](TESTING_AND_VALIDATION_PLAN.md) |
| Data privacy and emergency-safety safeguards | [Security & Emergency Safety](SECURITY_AND_EMERGENCY_SAFETY.md) |
| Deployment, historical replay and hackathon demonstration | [Deployment & Demo Runbook](DEPLOYMENT_AND_DEMO_RUNBOOK.md) |

## Original PDF status
**The five original PDFs are not yet stored in GitHub.** These Markdown copies and additional plans are available immediately for collaborative editing and searching. To preserve the exact PDF design and layout, upload the existing original PDFs into this folder through GitHub's **Add file → Upload files** feature or a local Git client.

Original PDF filenames:
- `FloodLens_AI_Complete_Project_Framework_v1.pdf`
- `FloodLens_AI_SRS_v1.pdf`
- `FloodLens_AI_Technical_Architecture_API_Design_v1.pdf`
- `FloodLens_AI_Master_Predevelopment_Blueprint_v1.pdf`
- `FloodLens_AI_Day_Wise_Team_Work_Plan.pdf`

## Development rules
- **P0:** Optical satellite pre/post processing, water-index flood detection, affected settlements, maps and a reference-based accuracy test where available.
- **P1:** Reproducible three-horizon risk prototype, connected apps, authority-reviewed test alerts, assistance requests, and forecast evaluation.
- **P2:** 3D terrain, radar extension, shelters/hospitals and route assessment, depth-model experiment.
- **P3:** Extra channels and candidate retraining if validated and time permits.
- Do not confuse predicted risk, observed extent, modelled depth, or field-confirmed damage.
- Do not present hackathon alerts or route suggestions as authorized operational emergency services.

Four-person team. Days 1–5 are for building and integration; Days 6–7 are for validation, fixes and demo rehearsal.
