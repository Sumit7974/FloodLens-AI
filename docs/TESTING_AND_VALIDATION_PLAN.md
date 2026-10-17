# Testing & Validation Plan

## Baselines and measurements
| System | Validation | Passing condition |
|---|---|---|
| Optical flood mapping | Real pre/post optical scenes with NDWI/MNDWI and cloud handling | Reproducible georeferenced mask and report |
| Map accuracy | Independent reference mask where available | Publish IoU, precision, recall and test limitations |
| Settlement exposure | Spatial intersection on test geometries | Correct inclusion and exclusion of test settlements |
| Forecast baseline | Historical forecasts + correctly timed outcomes | Demonstrable results without future-data leakage |
| Depth modelling | Suitable water-level and terrain reference | Never claim validated depth without evidence |
| Radar extension | Matched Sentinel-1 before/after observations | Document acquisition differences and map outputs |
| Web map | Real backend flood layers, zoom and selection | Visible map with timestamp and legend |
| Citizen Android | Risk display and test alerts | App works on test device; latest state fetched |
| WebSockets | Disconnect/reconnect, permissions, event update | Client resyncs missed data after reconnect |
| Alert workflow | Proposed → approved → test dispatched | Unauthorized users cannot broadcast |
| Assistance | Submit → dashboard → status update | Request persisted; updates visible only to authorized users |
| Routes | Known hazard polygon / blocked roads test | Demonstration correctly avoids test exclusions; limitations shown |
| Model updates | Baseline vs candidate on independent holdout | No unreviewed deployment; evidence retained |
| Report | Generated PDF/GeoJSON/CSV | Outputs open and show correct event, dates and sources |

## Failure tests
- Weather, river gauge, dam notice, or satellite source unavailable.
- Stale source timestamp, impossible coordinates, invalid GeoJSON, unsupported CRS.
- High optical cloud cover; no suitable post-flood scene.
- Failed processing job; job retries do not duplicate results.
- Multiple alert dispatch requests; deduplicate by alert identifier.
- User attempts to view someone else's assistance request.
- WebSocket disconnect; recover state through REST.
- Android in background and no notification permission.
- Shelter/hospital status unknown; don't silently claim available.
- Inaccessible road; route candidate labelled as unverified.
- Candidate retraining performs worse than baseline.

## Five-day gates
Day 1: test scene/data and app skeletons usable.
Day 2: actual optical flood map, affected settlement report.
Day 3: WebSocket alerts and Android/web request flow.
Day 4: complete historical replay.
Day 5: P0/P1 tests and release freeze.
Days 6–7: corrections only, validation, presentation rehearsal.

## Evidence requirements
Keep original input IDs and timestamps, run log, methodology, map validation metrics, model version, limitations, and screenshots or saved reproducible outputs.
