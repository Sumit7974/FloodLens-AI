"""
fetch_nepal_flood_data.py
=========================
FloodLens AI — Satellite & GIS Data Fetching Module
Task  : Fetch pre-flood / post-flood imagery for the August 2017 Nepal
        (Koshi River Basin) flood event using Google Earth Engine.

Datasets fetched
----------------
1. Sentinel-2 MSI (optical)  — pre & post flood, cloud-filtered
2. Sentinel-1 SAR GRD (radar)— pre & post flood (cloud-penetrating)
3. SRTM DEM 30m              — terrain elevation

Requirements
------------
    pip install earthengine-api geemap

Authenticate once (one-time setup):
    python -m earthengine.cli.eecli authenticate
  OR inside the script call: ee.Authenticate()

Author : FloodLens AI Team
"""

import ee
import geemap  # optional but useful for interactive Map display

# ---------------------------------------------------------------------------
# 1.  INITIALISE GOOGLE EARTH ENGINE
# ---------------------------------------------------------------------------
# Run `earthengine authenticate` in your terminal ONCE before executing.
# Remove the project arg if you are using a legacy (non-Cloud) GEE account.
try:
    ee.Initialize(project="floodlens-ai-512012")
except Exception:
    # Token missing or expired — re-authenticate then initialise
    ee.Authenticate()
    ee.Initialize(project="floodlens-ai-512012")

print("✅  Earth Engine initialised successfully.")

# ---------------------------------------------------------------------------
# 2.  AREA OF INTEREST — KOSHI RIVER BASIN, NEPAL TERAI
# ---------------------------------------------------------------------------
# Approximate bounding box covering the Koshi flood-plain in the eastern
# Terai.  Coordinates: [xmin, ymin, xmax, ymax] (lon/lat, WGS-84)
#
#   West  : 86.5°E   East  : 88.2°E
#   South : 26.2°N   North : 27.8°N
#
AOI = ee.Geometry.Rectangle([86.5, 26.2, 88.2, 27.8])

print("📍  Area of Interest (Koshi Basin) defined.")

# ---------------------------------------------------------------------------
# 3.  DATE WINDOWS
# ---------------------------------------------------------------------------
# August 2017 Nepal floods — peak inundation ~4-18 Aug 2017
PRE_FLOOD_START  = "2017-07-01"
PRE_FLOOD_END    = "2017-07-31"

POST_FLOOD_START = "2017-08-05"
POST_FLOOD_END   = "2017-08-25"

# ---------------------------------------------------------------------------
# 4.  SENTINEL-2 OPTICAL IMAGERY
# ---------------------------------------------------------------------------
# Dataset: COPERNICUS/S2_SR_HARMONIZED  (Surface Reflectance, L2A)
# Cloud cover filtered to ≤ 20 %.  Median composite to further remove clouds.

MAX_CLOUD_COVER = 20  # percent

def get_s2_collection(start_date: str, end_date: str) -> ee.ImageCollection:
    """Return a cloud-filtered Sentinel-2 SR collection over the AOI."""
    return (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(AOI)
        .filterDate(start_date, end_date)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", MAX_CLOUD_COVER))
        .select(["B2", "B3", "B4", "B8", "B11", "B12"])
        # B2=Blue, B3=Green, B4=Red, B8=NIR, B11/B12=SWIR
    )


s2_pre  = get_s2_collection(PRE_FLOOD_START,  PRE_FLOOD_END)
s2_post = get_s2_collection(POST_FLOOD_START, POST_FLOOD_END)

# Median composite — robust against remaining cloud / shadow pixels
s2_pre_composite  = s2_pre.median().clip(AOI)
s2_post_composite = s2_post.median().clip(AOI)

print(f"🛰️   Sentinel-2 pre-flood  images in collection : {s2_pre.size().getInfo()}")
print(f"🛰️   Sentinel-2 post-flood images in collection : {s2_post.size().getInfo()}")

# ---------------------------------------------------------------------------
# 5.  SENTINEL-1 SAR (RADAR) DATA
# ---------------------------------------------------------------------------
# Dataset: COPERNICUS/S1_GRD
# SAR penetrates clouds — critical for flood mapping during monsoon.
# Using VV + VH polarisation, Interferometric Wide (IW) swath, Descending pass.

def get_s1_collection(start_date: str, end_date: str) -> ee.ImageCollection:
    """Return Sentinel-1 GRD IW collection over the AOI."""
    return (
        ee.ImageCollection("COPERNICUS/S1_GRD")
        .filterBounds(AOI)
        .filterDate(start_date, end_date)
        .filter(ee.Filter.eq("instrumentMode", "IW"))
        .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
        .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VH"))
        .filter(ee.Filter.eq("orbitProperties_pass", "DESCENDING"))
        .select(["VV", "VH"])
    )


s1_pre  = get_s1_collection(PRE_FLOOD_START,  PRE_FLOOD_END)
s1_post = get_s1_collection(POST_FLOOD_START, POST_FLOOD_END)

# Mean composite for SAR
s1_pre_composite  = s1_pre.mean().clip(AOI)
s1_post_composite = s1_post.mean().clip(AOI)

print(f"📡  Sentinel-1 SAR pre-flood  images : {s1_pre.size().getInfo()}")
print(f"📡  Sentinel-1 SAR post-flood images : {s1_post.size().getInfo()}")

# ---------------------------------------------------------------------------
# 6.  SRTM DIGITAL ELEVATION MODEL (DEM)
# ---------------------------------------------------------------------------
# Dataset: USGS/SRTMGL1_003  — 30 m resolution global DEM
# Used to derive: elevation, slope, flow direction for flood-risk modelling.

srtm = ee.Image("USGS/SRTMGL1_003").clip(AOI)

# Derive terrain layers
terrain   = ee.Terrain.products(srtm)
elevation = terrain.select("elevation")
slope     = terrain.select("slope")
aspect    = terrain.select("aspect")

print(f"🏔️   SRTM DEM loaded — bands: {terrain.bandNames().getInfo()}")

# ---------------------------------------------------------------------------
# 7.  QUICK NDWI — WATER INDEX (Sentinel-2 post-flood)
# ---------------------------------------------------------------------------
# NDWI = (Green - NIR) / (Green + NIR)
# Positive values → water; useful for thresholding flood extent.

ndwi_pre  = s2_pre_composite.normalizedDifference(["B3", "B8"]).rename("NDWI_pre")
ndwi_post = s2_post_composite.normalizedDifference(["B3", "B8"]).rename("NDWI_post")

# Flood mask: pixels where post-flood NDWI > 0.1 (water)
flood_mask = ndwi_post.gt(0.1).rename("flood_mask")

print("💧  NDWI and flood mask computed.")

# ---------------------------------------------------------------------------
# 8.  EXPORT TASKS — save to Google Drive
# ---------------------------------------------------------------------------
# Each export is a GEE Task; start them and monitor via the GEE Code Editor
# Tasks panel, or programmatically via ee.batch.Task.list().

EXPORT_SCALE  = 10    # 10 m resolution (Sentinel-2 native)
EXPORT_FOLDER = "FloodLens_Koshi_2017"

def make_export_task(image: ee.Image, description: str, scale: int = EXPORT_SCALE) -> ee.batch.Task:
    """Create and start a Drive export task."""
    task = ee.batch.Export.image.toDrive(
        image       = image,
        description = description,
        folder      = EXPORT_FOLDER,
        region      = AOI,
        scale       = scale,
        maxPixels   = 1e13,
        fileFormat  = "GeoTIFF",
    )
    task.start()
    print(f"  ↗  Export started : {description}")
    return task


print("\n🚀  Starting export tasks to Google Drive …")

tasks = {
    "s2_pre_flood_optical"  : make_export_task(s2_pre_composite.toFloat(),   "S2_Pre_Flood_Optical"),
    "s2_post_flood_optical" : make_export_task(s2_post_composite.toFloat(),  "S2_Post_Flood_Optical"),
    "s1_pre_flood_sar"      : make_export_task(s1_pre_composite.toFloat(),   "S1_Pre_Flood_SAR"),
    "s1_post_flood_sar"     : make_export_task(s1_post_composite.toFloat(),  "S1_Post_Flood_SAR"),
    "ndwi_pre"              : make_export_task(ndwi_pre.toFloat(),            "NDWI_Pre_Flood"),
    "ndwi_post"             : make_export_task(ndwi_post.toFloat(),           "NDWI_Post_Flood"),
    "flood_mask"            : make_export_task(flood_mask.toByte(),           "Flood_Mask_Aug2017"),
    "srtm_elevation"        : make_export_task(elevation.toFloat(),           "SRTM_Elevation",  scale=30),
    "srtm_slope"            : make_export_task(slope.toFloat(),               "SRTM_Slope",      scale=30),
}

print("\n✅  All export tasks submitted.")
print("    Monitor at: https://code.earthengine.google.com/ → Tasks tab")

# ---------------------------------------------------------------------------
# 9.  OPTIONAL — INTERACTIVE MAP (geemap)
# ---------------------------------------------------------------------------
# Uncomment in a Jupyter Notebook environment to display an interactive map.

# Map = geemap.Map(center=[27.0, 87.3], zoom=8)
#
# vis_rgb = {"bands": ["B4", "B3", "B2"], "min": 0, "max": 3000, "gamma": 1.4}
# vis_sar = {"bands": ["VV"],             "min": -25, "max": 0}
# vis_ndwi= {"min": -0.3, "max": 0.5,    "palette": ["brown", "white", "blue"]}
# vis_dem = {"min": 50,   "max": 1500,   "palette": ["green", "yellow", "brown", "white"]}
#
# Map.addLayer(s2_pre_composite,  vis_rgb,  "S2 Pre-Flood (RGB)")
# Map.addLayer(s2_post_composite, vis_rgb,  "S2 Post-Flood (RGB)")
# Map.addLayer(s1_pre_composite,  vis_sar,  "SAR Pre-Flood (VV)")
# Map.addLayer(s1_post_composite, vis_sar,  "SAR Post-Flood (VV)")
# Map.addLayer(ndwi_post,         vis_ndwi, "NDWI Post-Flood")
# Map.addLayer(flood_mask,        {"palette": ["white", "blue"]}, "Flood Mask")
# Map.addLayer(elevation,         vis_dem,  "SRTM Elevation")
# Map
