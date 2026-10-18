# FloodLens AI — Day 3 Integration Contracts & Protocol Specifications

**Author:** Member 1 (Backend & Integration Lead)  
**Branch:** `feature/backend-day3`  
**Target Consumers:** Member 3 (Web Frontend Lead), Member 4 (Mobile/Edge Lead)  
**Status:** Verified via Integration Tests and Demonstration Script  

---

## 1. Authenticated WebSocket Protocol (`/ws/v1/events`)

The FloodLens AI real-time event bus operates over WebSocket with JWT authentication, active user validation in the database, role-based topic authorization, and client REST resynchronization.

### 1.1 Connection Handshake

- **URL:** `ws://<host>:<port>/ws/v1/events?token=<JWT_ACCESS_TOKEN>`
- **Authentication:** Decodes JWT token and actively verifies user status (`is_active == True`) and current role in the database.
- **Rejection:** Inactive users, deleted users, or invalid/expired tokens are immediately closed with WebSocket code `1008 Policy Violation`.
- **Credential Security & Logging Rule:**
  - Passing JWTs in query parameters is permitted **strictly for prototype / demo testing**.
  - Web servers, proxies, and ingress routers must be configured **never to log query strings containing credentials**.
  - For non-demo / production deployments, query-string authentication must be replaced with ticket-based authentication (initial handshake frame) or secure HttpOnly cookie session headers.
  - Raw JWT tokens are strictly scrubbed from application logs.

Upon successful connection, the server sends a `connection.established` greeting:

```json
{
  "type": "connection.established",
  "user_id": "2ce11afb-9af9-4c30-ade9-dbd8302e2095",
  "role": "citizen",
  "subscribed_channels": [
    "alerts",
    "public",
    "risk_updates",
    "user:2ce11afb-9af9-4c30-ade9-dbd8302e2095"
  ],
  "resync_endpoints": {
    "alerts": "/api/v1/alerts",
    "assistance": "/api/v1/assistance/mine",
    "predictions": "/api/v1/predictions/latest"
  },
  "message": "Connected to FloodLens AI real-time event bus"
}
```

*Note for Authorities:* Authority and Admin roles automatically join `authority_queue` on connect in addition to the default channels.

### 1.2 Topic Authorization Matrix

| Channel Pattern | Accessible Roles | Privacy & Safeguards |
| :--- | :--- | :--- |
| `public` | `citizen`, `authority`, `admin` | Public broadcast channel |
| `alerts` | `citizen`, `authority`, `admin` | Dispatched operational alerts only; draft/approved alerts excluded |
| `demo_alerts` | `authority`, `admin`, authorized demo participants | Isolated simulation channel for historical-demo and test alerts (restricted to authorities and explicitly authorized demo participants; arbitrary subscriptions rejected as forbidden) |
| `risk_updates` | `citizen`, `authority`, `admin` | Regional forecast and risk changes |
| `locations:{location_id}` | `citizen`, `authority`, `admin` | Location-specific forecasts and sensor updates |
| `user:{user_id}` | Matching `user_id` ONLY | Strictly isolated to the specific user. No other user or authority may subscribe |
| `authority_queue` | `authority`, `admin` | Confidential responder queue for emergency assistance and draft alert review |
| `authority_*` | `authority`, `admin` | Internal operational channels |

### 1.3 Client Actions & Subscription Messages

#### Subscribe to Topic
```json
{"action": "subscribe", "channel": "locations:loc_janakpur_01"}
```
**Server Response (Success):**
```json
{"type": "subscription.result", "channel": "locations:loc_janakpur_01", "status": "subscribed"}
```
**Server Response (Unauthorized):**
```json
{"type": "subscription.result", "channel": "authority_queue", "status": "forbidden"}
```

#### Unsubscribe from Topic
```json
{"action": "unsubscribe", "channel": "locations:loc_janakpur_01"}
```
**Server Response:**
```json
{"type": "subscription.result", "channel": "locations:loc_janakpur_01", "status": "unsubscribed"}
```

#### Heartbeat (Ping / Pong)
```json
{"action": "ping"}
```
**Server Response:**
```json
{"type": "pong"}
```

#### Client Reconnection & REST Resync
When a mobile or web client reconnects after network drop, send:
```json
{"action": "resync"}
```
**Server Response:**
```json
{
  "type": "resync.instructions",
  "user_id": "2ce11afb-9af9-4c30-ade9-dbd8302e2095",
  "role": "citizen",
  "endpoints": {
    "alerts": "/api/v1/alerts",
    "assistance": "/api/v1/assistance/mine",
    "predictions": "/api/v1/predictions/latest"
  },
  "server_time": "2026-10-18T07:37:47.705251Z",
  "message": "Fetch latest state via REST endpoints to reconcile any missed events."
}
```

---

## 2. Emergency Alert State Machine & Test Dispatch Safeguards

```
[DRAFT] ──────(Authority Approval)─────> [APPROVED] ──────(Test Dispatch)─────> [DISPATCHED]
   │                                         │
   └─────────────(Cancellation)──────────────┴───────────────────────────────> [CANCELLED]
```

### 2.1 State Transition Rules

1. `DRAFT -> APPROVED`:
   - Allowed only for `authority` or `admin`.
   - Emits `alert.approved` to `authority_queue` ONLY.
   - Unpublished drafts are completely hidden from non-authorities in REST and WebSockets.
2. `APPROVED -> DISPATCHED`:
   - Allowed only for `authority` or `admin`.
   - Emits `alert.published` to channel `demo_alerts` for simulation alerts (`historical_demo` or `test`) or `alerts` for operational alerts, plus `authority_queue` AFTER database commit.
3. Invalid Transitions (strictly rejected with HTTP 400):
   - `DRAFT -> DISPATCHED` directly (`code: NOT_APPROVED`).
   - `APPROVED -> APPROVED` duplicate approval (`code: INVALID_STATE`).
   - `DISPATCHED -> APPROVED` re-approval (`code: INVALID_STATE`).
   - `DISPATCHED -> DISPATCHED` duplicate dispatch (`code: INVALID_STATE`).

### 2.2 Safety & Test-Only Safeguards

- **Simulation Enforcement:** `simulated=True` is strictly mandatory for all test dispatches. Attempting to submit `simulated=False` is rejected (`HTTP 400 OPERATIONAL_DISPATCH_PROHIBITED`). Operational emergency warnings cannot be issued.
- **Operational Mode Restriction:** All dispatches are strictly restricted to `historical_demo` or `test` mode. Attempting to dispatch alerts in `live_observation` or `model_estimate` mode is rejected (`HTTP 400 DISPATCH_RESTRICTED_TO_TEST`).
- **Authenticated User ID Demo Authorization:** Demo participant authorization strictly requires explicitly configured or registered database User IDs (`user.id` in `settings.demo_participant_ids` or dynamically registered via `demo_participant_registry.register_participant(user_id)`). Email-only authorization is strictly removed because email ownership is unverified during public account registration; self-registering with an allowlisted email does not grant demo access.
- **Dual-Check Demo Alert Protection (`is_demo_alert`):** Alerts are protected as demonstration/simulation alerts based on both:
  1. `OperationalMode.HISTORICAL_DEMO` or `OperationalMode.TEST`
  2. Title prefix starting with `[DEMO` or `[TEST`
  Even if an alert's title prefix is omitted, its mode guarantees it remains protected from public feeds, anonymous callers, and unauthorized citizen inspection.
- **Feed, Channel, and Endpoint Access Control:** Demo simulation alerts (`is_demo_alert(alert)`) are accessible **ONLY** to Authority/Admin users and explicitly authorized demonstration participants by user ID. Arbitrary citizen subscriptions to WebSocket channel `demo_alerts` are rejected (`status: forbidden`). Requests by unrelated citizens or anonymous callers to `GET /api/v1/alerts?include_demo=true` or direct lookup `GET /api/v1/alerts/{alert_id}` for demo alerts are strictly denied with `HTTP 403 Forbidden` (`DEMO_ALERTS_RESTRICTED`, `DEMO_ALERT_RESTRICTED`).
- **Visible Labelling:** Dispatched alerts are visibly labelled with `[DEMO ONLY]` or `[DEMO / TEST ONLY]` prefix in titles and `[HISTORICAL DEMO / TEST SIMULATION]` in body messages.
- **Test Metadata:** Dispatched event payloads include `"is_test": true, "simulation": true, "simulated_only": true`.

### 2.3 Dispatch Event Payload (`alert.published`)
```json
{
  "event_id": "evt_dispatch_7300cbd6-a546-4353-862a-597258fba91d",
  "type": "alert.published",
  "timestamp": "2026-10-18T07:37:47.705251Z",
  "location_id": "loc_janakpur_01",
  "resource_id": "7300cbd6-a546-4353-862a-597258fba91d",
  "version": 1,
  "metadata": {
    "title": "[DEMO ONLY] Jaladh River Rapid Inundation",
    "mode": "historical_demo",
    "is_test": true,
    "simulation": true
  }
}
```

---

## 3. Citizen Assistance Lifecycle & Privacy Guarantees

### 3.1 REST API Contracts

| Method | Endpoint | Authorization | Description |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/assistance` | `citizen`, `authority`, `admin` | Create emergency help request |
| `GET` | `/api/v1/assistance/mine` | `citizen` | Retrieve citizen's own requests |
| `GET` | `/api/v1/assistance/{id}` | Owner or Authority | Retrieve specific request (non-owners receive 403) |
| `GET` | `/api/v1/assistance` | `authority`, `admin` | View responder triage queue |
| `PATCH` | `/api/v1/assistance/{id}` | `authority`, `admin` | Update status, assigned responder, and notes |

### 3.2 Privacy & Coordinate Protection Rules

- **Zero Coordinate Leakage on Public WS:** Latitude, longitude, phone, full name, and sensitive personal details are **never** included in broadcast WebSocket events.
- **Triage Queue Notification (`assistance.created`):** Broadcast exclusively to `authority_queue` containing only resource ID and triage category:
  ```json
  {
    "event_id": "evt_req_af41b66e-0689-4de1-bd08-97f011d4a939",
    "type": "assistance.created",
    "timestamp": "2026-10-18T07:37:47.614Z",
    "resource_id": "af41b66e-0689-4de1-bd08-97f011d4a939",
    "metadata": {
      "category": "evacuation",
      "people_count": 4
    }
  }
  ```
- **User-Specific Private Status Update (`assistance.updated`):** Emitted directly to `user:{citizen_id}`:
  ```json
  {
    "event_id": "evt_update_user_af41b66e_1729237067",
    "type": "assistance.updated",
    "timestamp": "2026-10-18T07:37:47.632Z",
    "resource_id": "af41b66e-0689-4de1-bd08-97f011d4a939",
    "metadata": {
      "status": "in_progress",
      "status_notes": "Rescue Boat Unit 3 dispatched to location.",
      "assigned_to": "6a170cc7-63e2-4031-a5aa-46ce0fa8f758"
    }
  }
  ```

---

## 4. Push Notification Adapter (Expo / FCM Sandbox)

Located at `backend/app/services/push_notifications.py`.

### 4.1 Token Validation & Masking

- **Expo Token Format:** `ExponentPushToken[...]` or alphanumeric string length >= 20.
- **FCM Token Format:** Alphanumeric / colon string length >= 30.
- **Credential Masking:** Tokens are masked in all logs, demonstration scripts, and delivery receipts: `ExponentPushToken[***7890]`. Full device secrets and raw tokens are never logged.

### 4.2 Simulated Delivery States & Test-Device Verification

- **Unambiguous Simulation:** Receipts strictly output `status="simulated_only"` with `simulated_only: true` and an explicit delivery note confirming that no external network call was made to Expo or FCM.
- **Verified Test-Device Registrations & Explicit Dummy Tokens:** The prototype strictly accepts only explicitly configured dummy tokens (e.g. `DEFAULT_CONFIGURED_DUMMY_TOKENS`) or genuinely registered opted-in test devices via `adapter.register_test_device(token)`.
- **Zero Consent Inference:** Consent is **NEVER** inferred from token text (e.g. presence of `test`, `demo`, or `sandbox` substrings). Any token not explicitly configured or genuinely registered is rejected (`unregistered_device`).
- **Opt-in Rule:** Opt-in is **not** assumed simply because an authority submitted a token; device opt-in is actively verified. Arbitrary device dispatch is prohibited.

| Status | Code | Description |
| :--- | :--- | :--- |
| `SIMULATED_ONLY` | `simulated_only` | Recorded in test sandbox simulation; no real external delivery occurred |
| `UNREGISTERED_DEVICE` | `unregistered_device` | Token is not in the verified test device registry; arbitrary dispatch prohibited |
| `INVALID_TOKEN` | `invalid_token` | Token failed syntactic validation pattern |
| `OPT_OUT_SKIPPED` | `opt_out_skipped` | Device recipient has not explicitly opted into test alerts |
| `FAILED` | `failed` | Downstream simulation handler error |

### 4.3 Mobile Integration Guide for Member 4

When testing on physical devices or Expo Go / FCM emulators:
1. Register push token in mobile app:
   ```typescript
   const token = (await Notifications.getExpoPushTokenAsync()).data;
   ```
2. During test dispatch, include verified token in dispatch request:
   ```json
   POST /api/v1/alerts/{alert_id}/dispatch
   {
     "notes": "Testing on field device",
     "target_device_tokens": ["ExponentPushToken[demo_test_device_sandbox_01]"],
     "simulated": true
   }
   ```
3. Backend validates that token is a verified test registration and returns a `SIMULATED_ONLY` delivery receipt. Real emergency warnings are never issued.

---

## 5. Summary of Member 4 Dependencies

1. **Token Storage:** Connect push token registration from mobile device to authenticated citizen profile.
2. **WebSocket Reconnect:** Ensure mobile client calls `{"action": "resync"}` after network interruption.
3. **Assistance Channel:** On login, mobile app should listen for `assistance.updated` events on default subscribed channel `user:{citizen_id}`.
