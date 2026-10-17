# Dataset & Model Readiness — FloodLens AI

## Pilot and minimum required assets
- [ ] Select one documented flood event in a Nepal Terai river sector (Koshi, Bagmati, or Gandaki).
- [ ] Record area of interest, bounding box, dates, coordinate system, and event sources.
- [ ] Verify usable **before and after optical imagery** with cloud masking: Sentinel-2 or Landsat 8/9. This is mandatory for the assigned problem statement.
- [ ] Identify settlement polygons or reliable settlement point data and administrative boundaries.
- [ ] Obtain a reference flood mask if possible; note its time, resolution, provenance, and limitations.

## Dataset register
| Input | Proposed source | How used | Validation gate |
|---|---|---|---|
| Before/after optical scenes | Sentinel-2/Landsat via Earth Engine | NDWI/MNDWI and change detection | Dates, coverage, clouds, alignment verified |
| Radar observations | Sentinel-1 SAR | Additional water detection | Polarization, orbit and acquisition timing matched |
| DEM/elevation | Copernicus DEM/SRTM | 3D terrain and possible hydraulic inputs | Vertical reference, resolution and coverage recorded |
| Forecast weather | Archived weather forecast runs | +1/+3/+6 hour estimates | Was actually available at issue time |
| River level/discharge | Nepal DHM / verified source | Flood precursors | Units, location, timestamp, completeness |
| Dam release | Responsible operators' notices | Upstream flow context | Provenance and availability confirmed |
| Buildings, roads, settlements | OSM / authoritative local GIS | Exposure and asset intersection | Spatial completeness assessed |
| Shelters/hospitals | Verified authority data when available | Citizen destination lookup | Operational/verification status known |

## Technical checks
1. All times are recorded in UTC internally; preserve source time zone.
2. Raster pixel alignment, projection, and acquisition dates must be retained.
3. Prefer an independent event for validation; never leak post-event facts into earlier predictions.
4. Report missing feeds, stale observations, and resolution limitations.
5. Keep **forecast risk**, **predicted inundation extent**, **modelled flood depth**, and **satellite-observed extent** as distinct data products.
6. Do not infer destroyed buildings from an inundation overlay alone.

## Initial modelling choices
- Baseline first: explainable rainfall/river/terrain risk estimate.
- Only train a machine-learning predictor if adequate labeled historical events exist.
- Where suitable hydraulic inputs are absent, depth modelling remains experimental with explicit limitations.
- Candidate retraining remains offline and separate from operational model activation.

## Day-1 go/no-go
**Go:** a documented flood event, usable optical before/after scenes, settlement data, first flood-mask processing test, and understood forecast-label availability.
**No-go:** only simulated maps with no real optical case; select a different test event immediately.
