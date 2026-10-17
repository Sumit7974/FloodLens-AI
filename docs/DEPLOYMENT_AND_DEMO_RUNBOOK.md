# Deployment & Hackathon Demo Runbook

## Development environment
- Single GitHub monorepo: `backend/`, `web/`, `android/`, `ml/`, `gis/`, `docs/`.
- Backend: FastAPI with PostgreSQL/PostGIS; background worker for satellite and ML jobs.
- Authority web: React + TypeScript.
- Android: React Native/Expo.
- WebSockets for active sessions; push notifications for Android background delivery.

## Environment template (example variable names)
```ini
DATABASE_URL=<postgresql-with-postgis-connection>
JWT_SECRET=<locally-generated-secret>
CORS_ORIGINS=<authorized-web-origin>
MAP_TILE_URL=<approved-map-provider>
WEATHER_API_KEY=<if-required>
EARTH_ENGINE_PROJECT=<configured-project>
FIREBASE_PROJECT_ID=<configured-project>
DEMO_MODE=true
```
Never commit real secrets or production contact lists. Add `.env*` to `.gitignore` except safe templates.

## Deployment prerequisites
1. HTTPS/WSS endpoint verified.
2. PostGIS migrations applied and seeded historical demo region.
3. Satellite/map assets accessible from deployed backend/storage.
4. Web application talks to deployed API.
5. Android build installed on actual device; notifications tested.
6. API and WebSocket authorization validated.
7. External source failure fallback enabled without fabricating live data.

## Historical replay (recommended judges' scenario)
1. Select the Nepal Terai historical flood event and the *forecast issue time*.
2. Display archived inputs and the +1h/+3h/+6h baseline results.
3. Show an authority-reviewed **test** warning reaching demo Android app.
4. Show verified shelter information and any clearly labelled route assessments.
5. Load optical pre/post flood imagery and generated observed flood mask.
6. Show affected-settlement/asset exposure and sample assistance request.
7. Display independent map accuracy and valid forecast comparison.
8. Explain candidate-model training limitations and model version controls.

## Recovery
- Cache a known-good event with stored map layers and results.
- Maintain a reproducible offline demo mode.
- If an external API fails, state the source is unavailable and continue with archived evidence.
- If push or SMS service fails, show the persisted approved alert and honest delivery status.
- Have a recording of the working demo and a one-page troubleshooting checklist.

## Release gate
By end of Day 5: required optical flood map, settlement report, connected apps and end-to-end demonstration working.
Days 6–7: only fixes, validation, deployment verification and presentation.
