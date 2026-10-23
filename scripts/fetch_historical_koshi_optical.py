"""Fetch and curate verified historical Sentinel-2 Level-2A optical imagery for the Koshi flood event.

Study Area: Koshi River Basin / Eastern Nepal Terai (Morang/Jhapa districts)
Pre-flood baseline: 2017-06-04 (S2A_MSIL2A_20170604T043701_R033_T45RWK_20210209T202032)
Post-flood scene:   2017-08-23 (S2A_MSIL2A_20170823T043701_R033_T45RWK_20210201T071627)
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Dict, Any

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.windows import Window
import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_BASE = REPO_ROOT / "data" / "historical_koshi_optical"
PRE_DIR = OUTPUT_BASE / "pre_flood"
POST_DIR = OUTPUT_BASE / "post_flood"
MANIFEST_PATH = OUTPUT_BASE / "scene_manifest.json"

STAC_ITEM_URL = "https://planetarycomputer.microsoft.com/api/stac/v1/collections/sentinel-2-l2a/items/{item_id}"
SAS_SIGN_URL = "https://planetarycomputer.microsoft.com/api/sas/v1/sign"

SCENES = {
    "pre_flood": {
        "id": "S2A_MSIL2A_20170604T043701_R033_T45RWK_20210209T202032",
        "captured_at": "2017-06-04T04:37:01.026000Z",
        "dir": PRE_DIR,
    },
    "post_flood": {
        "id": "S2A_MSIL2A_20170823T043701_R033_T45RWK_20210201T071627",
        "captured_at": "2017-08-23T04:37:01.026000Z",
        "dir": POST_DIR,
    },
}

# 10m grid AOI window: 2000x2000 pixels = 20km x 20km = 400 km²
WINDOW_10M = Window(col_off=8500, row_off=7500, width=2000, height=2000)
# 20m grid AOI window for SCL: 1000x1000 pixels
WINDOW_20M = Window(col_off=4250, row_off=3750, width=1000, height=1000)


def get_signed_asset_url(item_id: str, asset_key: str) -> str:
    item_resp = requests.get(STAC_ITEM_URL.format(item_id=item_id), timeout=30)
    item_resp.raise_for_status()
    raw_href = item_resp.json()["assets"][asset_key]["href"]
    sign_resp = requests.get(SAS_SIGN_URL, params={"href": raw_href}, timeout=30)
    sign_resp.raise_for_status()
    return sign_resp.json()["href"]


def compute_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def fetch_and_save_bands():
    PRE_DIR.mkdir(parents=True, exist_ok=True)
    POST_DIR.mkdir(parents=True, exist_ok=True)

    manifest_data: Dict[str, Any] = {
        "event": {
            "name": "August 2017 Nepal Terai Monsoon Flooding",
            "study_area": "Koshi River Basin & Eastern Terai Plains (Morang/Jhapa districts, Nepal)",
            "aoi_utm45n": {
                "left": 584980.0,
                "bottom": 2905000.0,
                "right": 604980.0,
                "top": 2925000.0,
            },
            "aoi_wgs84": {
                "west": 87.8512,
                "south": 26.2625,
                "east": 88.0519,
                "north": 26.4421,
            },
            "area_km2": 400.0,
            "crs": "EPSG:32645",
            "spatial_resolution_meters": 10.0,
        },
        "license": "Copernicus Open Access Policy / Creative Commons CC BY 4.0",
        "provider": "European Space Agency (ESA) Copernicus via Microsoft Planetary Computer",
        "processing_level": "Level-2A Bottom-Of-Atmosphere (BOA) Surface Reflectance",
        "scenes": {},
    }

    for label, info in SCENES.items():
        item_id = info["id"]
        out_dir = info["dir"]
        print(f"\n=== Fetching {label} ({item_id}) ===")

        # 1. Fetch B03 (Green, 10m)
        b03_url = get_signed_asset_url(item_id, "B03")
        with rasterio.open(b03_url) as src:
            b03_data = src.read(1, window=WINDOW_10M)
            prof_10m = src.profile.copy()
            trans_10m = src.window_transform(WINDOW_10M)
            crs_10m = src.crs

        prof_10m.update(
            driver="GTiff",
            height=WINDOW_10M.height,
            width=WINDOW_10M.width,
            transform=trans_10m,
            crs=crs_10m,
            compress="deflate",
            count=1,
            dtype="uint16",
        )
        b03_path = out_dir / f"{label}_B03.tif"
        with rasterio.open(b03_path, "w", **prof_10m) as dst:
            dst.write(b03_data, 1)
        print(f"  Saved {b03_path.name} (shape={b03_data.shape}, min={b03_data.min()}, max={b03_data.max()})")

        # 2. Fetch B08 (NIR, 10m)
        b08_url = get_signed_asset_url(item_id, "B08")
        with rasterio.open(b08_url) as src:
            b08_data = src.read(1, window=WINDOW_10M)
        b08_path = out_dir / f"{label}_B08.tif"
        with rasterio.open(b08_path, "w", **prof_10m) as dst:
            dst.write(b08_data, 1)
        print(f"  Saved {b08_path.name} (shape={b08_data.shape}, min={b08_data.min()}, max={b08_data.max()})")

        # 3. Fetch SCL (Scene Classification Layer, native 20m resampled to 10m)
        scl_url = get_signed_asset_url(item_id, "SCL")
        with rasterio.open(scl_url) as src:
            scl_data_20m = src.read(1, window=WINDOW_20M)
            # Resample 20m (1000x1000) to 10m (2000x2000) using nearest neighbor for categorical classes
            scl_data_10m = np.repeat(np.repeat(scl_data_20m, 2, axis=0), 2, axis=1)

        prof_scl = prof_10m.copy()
        prof_scl.update(dtype="uint8", nodata=0)
        scl_path = out_dir / f"{label}_SCL.tif"
        with rasterio.open(scl_path, "w", **prof_scl) as dst:
            dst.write(scl_data_10m.astype(np.uint8), 1)
        print(f"  Saved {scl_path.name} (shape={scl_data_10m.shape}, unique classes={np.unique(scl_data_10m).tolist()})")

        manifest_data["scenes"][label] = {
            "product_id": item_id,
            "captured_at": info["captured_at"],
            "directory": str(out_dir.relative_to(REPO_ROOT)),
            "files": {
                "B03": {
                    "filename": b03_path.name,
                    "sha256": compute_sha256(b03_path),
                    "size_bytes": b03_path.stat().st_size,
                    "band_name": "Green (560 nm)",
                    "resolution_m": 10.0,
                },
                "B08": {
                    "filename": b08_path.name,
                    "sha256": compute_sha256(b08_path),
                    "size_bytes": b08_path.stat().st_size,
                    "band_name": "Near Infrared (842 nm)",
                    "resolution_m": 10.0,
                },
                "SCL": {
                    "filename": scl_path.name,
                    "sha256": compute_sha256(scl_path),
                    "size_bytes": scl_path.stat().st_size,
                    "band_name": "Scene Classification Layer",
                    "resolution_m": 10.0,
                    "classes_present": np.unique(scl_data_10m).tolist(),
                },
            },
        }

    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2)
    print(f"\n[OK] Manifest saved to {MANIFEST_PATH.name}")


if __name__ == "__main__":
    fetch_and_save_bands()
