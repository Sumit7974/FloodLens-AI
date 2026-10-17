# Security, Privacy & Emergency Safety Plan

FloodLens AI is a **hackathon prototype**, not a certified public emergency-warning service.

## Access control
- Users: citizen, authority, administrator.
- Citizens can access their own requests, not others' precise locations.
- Authorized authorities can review geographically relevant assistance cases.
- Only authorized officers may approve and dispatch alerts.
- Candidate model training and activation have separate permissions.

## Privacy
- Collect only the location/identifying data needed for the feature.
- Obtain permission before using device location.
- Restrict precise citizen coordinates, attachment URLs and contact details.
- Never expose personal details in general WebSocket broadcasts.
- Protect backend credentials; keep tokens out of GitHub and public logs.
- Define retention/deletion rules before any live-user data collection.

## Forecasting and flood-map integrity
- Every map indicates **predicted risk**, **predicted extent**, **modelled depth**, or **satellite-observed extent** distinctly.
- Every observation has an acquisition/issue timestamp and source information.
- Satellite-detected inundation does not confirm destroyed buildings or precise depth.
- Incomplete evidence must be displayed as missing or uncertain.

## Alerts and routing
- Prototype warnings go only to approved test recipients and clearly state they are test messages.
- The AI can propose alerts, but public broadcasting requires validated criteria and authorized review.
- A high-elevation site is not automatically a safe evacuation destination.
- Hospitals and shelters require verification; operating capacity cannot be assumed.
- Routes can avoid known hazards but must never be described as guaranteed safe or current when data is stale.
- Avoid automatic rescue prioritization solely from a model score.

## Resilience
REST always provides current persisted data after WebSocket reconnect; GPS and alert delivery can fail; offline caches can become stale.
