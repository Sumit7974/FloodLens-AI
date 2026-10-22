"""
vectorize_flood.py
==================
FloodLens AI — Flood Mask Vectorization Pipeline
------------------------------------------------
Converts binary flood extent pixels (where value == 1) from Sentinel-2
flood_mask.tif into polygon vector geometries using rasterio and geopandas.

Outputs:
    flood_polygons.geojson - Vector polygons with accurate metric area
                             attributes (m², ha, km²) in standard WGS84 (EPSG:4326).

Author : FloodLens AI Team
"""

import os
import sys
import time
import argparse
import subprocess
from pathlib import Path


# ---------------------------------------------------------------------------
# AUTOMATIC DEPENDENCY MANAGEMENT
# ---------------------------------------------------------------------------
def check_and_install_dependencies():
    """Ensure geopandas, shapely, pyproj, and rasterio are installed."""
    required_packages = {
        "shapely": "shapely",
        "pyproj": "pyproj",
        "geopandas": "geopandas",
        "rasterio": "rasterio",
    }

    for module_name, pip_name in required_packages.items():
        try:
            __import__(module_name)
        except ImportError:
            print(f"[*] Package '{module_name}' is not installed. Attempting installation...")
            # Check for local wheel file first (useful for rasterio on Python 3.14)
            installed = False
            if module_name == "rasterio":
                search_dirs = [
                    Path.cwd(),
                    Path(__file__).resolve().parent,
                    Path(__file__).resolve().parent.parent,
                    Path(__file__).resolve().parent.parent.parent,
                ]
                for d in search_dirs:
                    wheels = list(d.glob("*rasterio*.whl"))
                    if wheels:
                        print(f"[*] Found local wheel: {wheels[0]}")
                        try:
                            subprocess.check_call([
                                sys.executable, "-m", "pip", "install",
                                str(wheels[0]), "--no-deps"
                            ])
                            installed = True
                            print(f"[+] Installed {module_name} from local wheel.")
                            break
                        except Exception as e:
                            print(f"[!] Local wheel installation failed: {e}")

            if not installed:
                try:
                    subprocess.check_call([sys.executable, "-m", "pip", "install", pip_name])
                    print(f"[+] Successfully installed '{pip_name}'.")
                except Exception as e:
                    print(f"[!] Warning: pip install failed for '{pip_name}': {e}")


# Run dependency checks before importing spatial libraries
check_and_install_dependencies()

import numpy as np
from shapely.geometry import shape, Polygon, MultiPolygon
from shapely.validation import make_valid
import geopandas as gpd

try:
    import rasterio
    from rasterio.features import shapes
    HAS_RASTERIO = True
except ImportError:
    HAS_RASTERIO = False
    rasterio = None


# ---------------------------------------------------------------------------
# PATH LOCATOR
# ---------------------------------------------------------------------------
def find_flood_mask(custom_path=None) -> Path:
    """Locate flood_mask.tif across standard workspace directories."""
    if custom_path:
        p = Path(custom_path).resolve()
        if p.is_file():
            return p
        raise FileNotFoundError(f"Specified mask file not found: {custom_path}")

    script_dir = Path(__file__).resolve().parent
    cwd = Path.cwd()

    candidate_locations = [
        script_dir / "downloads" / "flood_mask.tif",
        script_dir / "flood_mask.tif",
        cwd / "FloodLens-AI" / "ml" / "gis_processing" / "downloads" / "flood_mask.tif",
        cwd / "ml" / "gis_processing" / "downloads" / "flood_mask.tif",
        cwd / "downloads" / "flood_mask.tif",
        cwd / "flood_mask.tif",
    ]

    for cand in candidate_locations:
        if cand.is_file() and cand.stat().st_size > 1000:
            return cand.resolve()

    # Fallback: search recursively in workspace
    for root_dir in [script_dir.parent.parent, cwd]:
        for match in root_dir.rglob("flood_mask.tif"):
            if match.is_file() and match.stat().st_size > 1000:
                return match.resolve()

    raise FileNotFoundError(
        "Could not find 'flood_mask.tif'. Please run calculate_ndwi.py first "
        "or specify the file path via --input."
    )


# ---------------------------------------------------------------------------
# VECTORIZATION PIPELINE
# ---------------------------------------------------------------------------
def vectorize_flood_mask(
    mask_path: Path,
    output_geojson: Path,
    min_area_sqm: float = 0.0,
    simplify_tolerance: float = None,
) -> gpd.GeoDataFrame:
    """
    Reads flood_mask.tif, extracts flooded pixels (value == 1),
    converts to Shapely polygons, adds metric attributes, projects to WGS84,
    and saves to GeoJSON.
    """
    t0 = time.time()
    print("=" * 70)
    print(" FLOODLENS AI — FLOOD MASK VECTORIZATION PIPELINE")
    print("=" * 70)
    print(f"[*] Input Mask    : {mask_path}")
    print(f"[*] Target Output : {output_geojson}")

    if not HAS_RASTERIO:
        raise RuntimeError(
            "rasterio is required for vectorization. Please install rasterio or check the wheel."
        )

    # 1. Read Raster with Rasterio
    print("[*] Opening raster with rasterio...")
    with rasterio.open(mask_path) as src:
        mask_data = src.read(1)
        transform = src.transform
        crs = src.crs
        bounds = src.bounds
        nodata = src.nodata
        width = src.width
        height = src.height
        res_x, res_y = src.res

    print(f"    - Dimensions     : {width} x {height} ({width * height:,} pixels)")
    print(f"    - Resolution     : {res_x:.2f}m x {res_y:.2f}m per pixel")
    print(f"    - CRS            : {crs}")
    print(f"    - Bounds         : left={bounds.left:.2f}, bottom={bounds.bottom:.2f}, "
          f"right={bounds.right:.2f}, top={bounds.top:.2f}")

    # 2. Pixel Statistics
    total_flooded_pixels = int(np.count_nonzero(mask_data == 1))
    total_dry_pixels     = int(np.count_nonzero(mask_data == 0))
    total_nodata_pixels  = int(np.count_nonzero(mask_data == 255)) if nodata == 255 else int(np.count_nonzero(np.isnan(mask_data)))

    print(f"[*] Pixel Classification:")
    print(f"    - Flooded pixels (1) : {total_flooded_pixels:,} ({total_flooded_pixels * res_x * res_y / 1e6:.2f} km²)")
    print(f"    - Dry land pixels (0): {total_dry_pixels:,}")
    print(f"    - NoData pixels      : {total_nodata_pixels:,}")

    if total_flooded_pixels == 0:
        print("[!] No flooded pixels (value == 1) detected in the mask.")
        gdf = gpd.GeoDataFrame(columns=["id", "class", "area_m2", "area_ha", "area_km2", "geometry"], crs=crs)
        output_geojson.write_text(gdf.to_json(), encoding="utf-8")
        return gdf

    # 3. Extract Shapes (GDAL polygonize on value == 1)
    print("[*] Extracting vector polygon shapes from flooded pixels...")
    # Passing mask=(mask_data == 1) ensures only flooded pixels are polygonized,
    # skipping background and nodata pixels for maximum speed and efficiency.
    binary_flood = (mask_data == 1).astype(np.uint8)

    poly_generator = shapes(
        binary_flood,
        mask=(binary_flood == 1),
        transform=transform,
        connectivity=4
    )

    records = []
    skipped_empty = 0
    repaired_invalid = 0

    for geom_dict, val in poly_generator:
        if val != 1:
            continue
        try:
            poly = shape(geom_dict)
            if poly.is_empty:
                skipped_empty += 1
                continue
            if not poly.is_valid:
                poly = make_valid(poly)
                repaired_invalid += 1
            if poly.is_empty:
                skipped_empty += 1
                continue

            # If make_valid produced a GeometryCollection or MultiPolygon, unpack
            if poly.geom_type == "MultiPolygon":
                for sub_poly in poly.geoms:
                    if not sub_poly.is_empty and sub_poly.area > 0:
                        records.append(sub_poly)
            elif poly.geom_type == "Polygon":
                if poly.area > 0:
                    records.append(poly)
            elif hasattr(poly, "geoms"):
                for sub_geom in poly.geoms:
                    if isinstance(sub_geom, (Polygon, MultiPolygon)) and not sub_geom.is_empty and sub_geom.area > 0:
                        records.append(sub_geom)
        except Exception:
            continue

    print(f"    - Raw polygons generated : {len(records):,}")
    if repaired_invalid > 0:
        print(f"    - Self-intersections fixed : {repaired_invalid:,}")

    if not records:
        print("[!] No valid geometries could be formed.")
        gdf = gpd.GeoDataFrame(columns=["id", "class", "area_m2", "area_ha", "area_km2", "geometry"], crs=crs)
        output_geojson.write_text(gdf.to_json(), encoding="utf-8")
        return gdf

    # 4. Construct GeoPandas GeoDataFrame (Native UTM CRS)
    print("[*] Computing metric attributes in native projection (meters)...")
    areas_m2 = [float(p.area) for p in records]
    perims_m = [float(p.length) for p in records]

    # Optional filtering by minimum area
    if min_area_sqm > 0:
        filtered = [
            (p, a, perim) for p, a, perim in zip(records, areas_m2, perims_m)
            if a >= min_area_sqm
        ]
        if filtered:
            records, areas_m2, perims_m = zip(*filtered)
            records = list(records)
            areas_m2 = list(areas_m2)
            perims_m = list(perims_m)
            print(f"    - Polygons after filtering (>= {min_area_sqm} m²): {len(records):,}")

    gdf_native = gpd.GeoDataFrame({
        "id": range(1, len(records) + 1),
        "class": ["flood"] * len(records),
        "area_m2": [round(a, 2) for a in areas_m2],
        "area_ha": [round(a / 10000.0, 4) for a in areas_m2],
        "area_km2": [round(a / 1000000.0, 6) for a in areas_m2],
        "perimeter_m": [round(p, 2) for p in perims_m],
    }, geometry=records, crs=crs)

    # Calculate overall flood summary
    total_area_m2 = sum(areas_m2)
    total_area_ha = total_area_m2 / 10000.0
    total_area_km2 = total_area_m2 / 1000000.0
    max_area_km2 = max(areas_m2) / 1000000.0 if areas_m2 else 0.0

    print(f"[*] Summary of Extracted Flood Polygons:")
    print(f"    - Polygon Count     : {len(gdf_native):,}")
    print(f"    - Total Flood Area  : {total_area_km2:.2f} km² ({total_area_ha:,.1f} ha / {total_area_m2:,.0f} m²)")
    print(f"    - Largest Polygon   : {max_area_km2:.2f} km²")

    # 5. Coordinate Transformation to WGS84 (EPSG:4326)
    print("[*] Reprojecting to standard WGS84 geographic coordinates (EPSG:4326)...")
    if gdf_native.crs is not None and gdf_native.crs.to_epsg() != 4326:
        gdf_wgs84 = gdf_native.to_crs(epsg=4326)
    else:
        gdf_wgs84 = gdf_native.copy()

    # Optional geometry simplification
    if simplify_tolerance is not None and simplify_tolerance > 0:
        print(f"[*] Simplifying geometries (tolerance={simplify_tolerance})...")
        gdf_wgs84["geometry"] = gdf_wgs84["geometry"].simplify(simplify_tolerance, preserve_topology=True)

    # 6. Save GeoJSON
    print(f"[*] Serializing and writing to GeoJSON: {output_geojson} ...")
    output_geojson.parent.mkdir(parents=True, exist_ok=True)

    geojson_str = gdf_wgs84.to_json(indent=2)
    output_geojson.write_text(geojson_str, encoding="utf-8")

    file_size_mb = output_geojson.stat().st_size / (1024 * 1024)
    print(f"[+] Output written successfully! File size: {file_size_mb:.2f} MB")

    # Also save a copy to project root if different
    root_copy = Path.cwd() / "flood_polygons.geojson"
    if root_copy.resolve() != output_geojson.resolve():
        root_copy.write_text(geojson_str, encoding="utf-8")
        print(f"[+] Convenience copy saved to: {root_copy}")

    dt = time.time() - t0
    print(f"[+] Vectorization completed in {dt:.2f} seconds.")
    print("=" * 70)
    return gdf_wgs84


# ---------------------------------------------------------------------------
# CLI ENTRY POINT
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Vectorize Sentinel-2 binary flood mask into GeoJSON polygons."
    )
    parser.add_argument(
        "--input", "-i",
        type=str,
        default=None,
        help="Path to flood_mask.tif (auto-detected if omitted)."
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default=None,
        help="Path to output flood_polygons.geojson."
    )
    parser.add_argument(
        "--min-area",
        type=float,
        default=0.0,
        help="Minimum polygon area in square meters to retain (default: 0 = keep all)."
    )
    parser.add_argument(
        "--simplify",
        type=float,
        default=None,
        help="Optional Douglas-Peucker simplification tolerance in degrees."
    )

    args = parser.parse_args()

    mask_file = find_flood_mask(args.input)

    if args.output:
        out_file = Path(args.output).resolve()
    else:
        out_file = mask_file.parent / "flood_polygons.geojson"

    vectorize_flood_mask(
        mask_path=mask_file,
        output_geojson=out_file,
        min_area_sqm=args.min_area,
        simplify_tolerance=args.simplify,
    )


if __name__ == "__main__":
    main()
