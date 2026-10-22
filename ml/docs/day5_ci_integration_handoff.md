# FloodLens ML Day 5 — CI Repair and Historical-Demo Backend Handoff

## Scope and verified controls

This work builds on Member 3's `feature/ml-day5` branch **without overwriting it**.
The review branch `fix/ml-day5-ci-and-integration` repairs the automated ML test suite
and adds an explicit, **historical-demo-only** bridge to the current FastAPI forecast contract.

ML CI tests synthetic inference, Pydantic schema validation, an isolated HTTP roundtrip
simulation and the checksum integrity of all three frozen ERA5 model binaries and
their metadata. Python 3.11 and Python 3.12 are supported.

### Three intentional skips

The original frozen reanalysis dataset
`ml/data/processed/era5_glofas_labeled.csv` is **excluded from Git**. The frozen
manifest demands a specific SHA-256 checksum; tests cannot recreate or change
these bytes without invalidating the audit. When the original verified data is missing,
three tests explicitly skip:

1. Full dataset-and-model integrity check (the model and metadata hashes are *still tested independently*).
2. Leakage-audit recomputation against the original dataset (stored audit metadata is still checked).
3. Original dataset chronological-split test.

The source dataset must be restored **from the audited original artifact** before
claiming full historical evaluation and reproducing every frozen hash. Do not
fabricate it, quietly regenerate a different dataset under the same name, or
rewrite the manifest to make a failing checksum pass.

The previously failing metadata checksum was caused by Git changing CRLF line
endings to LF. The original **1085-byte CRLF representation** hashes exactly to
the manifest's `18d527b7f29b...`; the scientific metadata content was not changed.

### Evaluation honesty

- Local end-to-end evaluation tests use the versioned, explicitly synthetic
  `ml/data/synthetic/synthetic_koshi_event.csv` **by name and with `baseline-v1`**.
- Reports computed on synthetic rows are marked `PASS_ON_SYNTHETIC_TEST_DATA`;
  they are not empirical real-world validations.
- Evaluation aborts if model loading/inference fails; it **never sets predicted labels
  equal to the ground truth** to manufacture high accuracy.
- The frozen `era5-v1` baseline has two documented lookahead features. Do not
  deploy it as an operational warning engine.
- The leak-free candidate is a retrospective research prototype: labels were
  constructed from ERA5/GloFAS rainfall/discharge proxies rather than independent
  confirmed flood observations. Leakage audits do not prove independent validation.
- Raw classifier `predict_proba` scores are not independently calibrated.
  The bridge intentionally leaves `calibrated_probability: null`.
- There are no verified continuous inundation-depth labels, official rescue
  workflows, or public-safety readiness claims.

## Reproduce offline model -> FastAPI schema check

From the repository root, install `ml/requirements.txt` in a Python 3.11/3.12 environment.

```powershell
python -m pip install -r ml/requirements.txt
python -m pytest ml/tests -q
python -m ml.scripts.submit_demo_forecast --features-file ml/examples/historical_demo_inputs.json --location-id loc_barahachhetra_w2
```

The command prints a schema-validated payload and **does not send any HTTP request**.
Values in the example are fictional test inputs, not live telemetry.

## Optional authenticated test database roundtrip

Only in an isolated historical-demo/test environment that you control:

```powershell
$env:FLOODLENS_BACKEND_URL = "http://127.0.0.1:8000"
$env:FLOODLENS_AUTHORITY_TOKEN = "<authorized test authority JWT>"
python -m ml.scripts.submit_demo_forecast --features-file ml/examples/historical_demo_inputs.json --location-id loc_barahachhetra_w2 --submit
```

The bridge uses `POST /api/v1/predictions/ingest`, checks the returned forecast
identifier, and confirms `GET /api/v1/predictions/latest?location_id=...` contains
all +1h/+3h/+6h horizon records. The backend must be started separately with a
valid PostGIS database and authorized test account. The bridge **never sends
alerts, requests rescue, or performs real operational dispatch**.

The optional test database roundtrip is **not executed by GitHub ML CI**, because
CI has no authorized PostGIS deployment or authority credentials. Do not claim
it passed until a real authenticated instance is tested.

## Required before deployment or merging into main

- Recover the exact original historical dataset and verify its frozen SHA-256.
- Independently validate flood outcomes with audited gauge/flood event observations;
  rainfall-derived proxy labels alone do not establish real-world flood accuracy.
- Review temporal leakage in label generation and feature availability, including
  whether discharge threshold statistics were fitted solely on training history.
- Agree on actual event and location IDs with Member 2's GIS/PostGIS import.
- Confirm full authenticated FastAPI ingest/readback against a temporary test database.
- Review PR changes and resolve differences with current `main` before merging.
