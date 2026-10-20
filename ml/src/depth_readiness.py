"""Flood-depth modelling input evaluation and data-readiness assessment.

Inspects the availability, quality, spatial coverage, temporal coverage, and units of:
  1. Rainfall intensity and accumulated rainfall
  2. Elevation and Digital Elevation Models (DEM)
  3. Terrain slope and low-lying areas
  4. Drainage density, capacity, and blockage information
  5. River / drainage water-level measurements
  6. Historical flood extent and observed flood depth
  7. Soil infiltration, land use, and surface roughness
  8. Simulated IoT water-level readings

SCIENTIFIC & OPERATIONAL SAFETY DIRECTIVE:
  - Do NOT claim a flood-depth model has been trained or validated without actual data.
  - Do NOT treat categorical flood-risk classifications (e.g. 'high') as measured flood depths (e.g. '1.5 m').
  - Clearly document data gaps and recommended hydraulic approaches rather than generating misleading depth numbers.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class InputReadinessItem:
    """Assessment of a specific data input required for flood depth estimation."""
    input_name: str
    readiness_status: str  # "AVAILABLE", "PARTIALLY_AVAILABLE", "MISSING", "REQUIRES_VALIDATION"
    relevance_to_depth_modelling: str
    source_and_format: str
    spatial_coverage_and_resolution: str
    temporal_coverage_and_frequency: str
    physical_units: str
    missing_data_and_quality_issues: str
    suitability_for_current_prototype: str
    additional_data_needed_for_operational_use: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DepthModellingReadinessReport:
    """Comprehensive readiness assessment report for hydraulic depth modelling."""
    report_title: str
    assessment_timestamp: str
    study_area: str
    overall_readiness_status: str  # "INSUFFICIENT_FOR_OPERATIONAL_DEPTH"
    inputs_evaluated_count: int
    available_count: int
    partially_available_count: int
    missing_count: int
    requires_validation_count: int
    inputs: List[InputReadinessItem] = field(default_factory=list)
    recommended_modelling_approach: Dict[str, Any] = field(default_factory=dict)
    unsupported_modelling_approaches: List[Dict[str, str]] = field(default_factory=list)
    next_steps_action_plan: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def evaluate_flood_depth_inputs(repo_root: Optional[Path] = None) -> DepthModellingReadinessReport:
    """Evaluate repository assets and external sources for flood depth estimation feasibility."""
    root = repo_root or Path(__file__).resolve().parents[2]
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # 1. Rainfall intensity and accumulated rainfall
    # Check if ERA5 / synthetic hourly data files exist in repo
    era5_csv = root / "ml" / "data" / "raw" / "era5_glofas_chatara_combined.csv"
    synth_csv = root / "ml" / "data" / "synthetic" / "synthetic_koshi_event.csv"
    has_rainfall_data = era5_csv.exists() or synth_csv.exists()

    rain_status = "AVAILABLE" if has_rainfall_data else "PARTIALLY_AVAILABLE"
    rain_item = InputReadinessItem(
        input_name="Rainfall Intensity and Accumulated Precipitation",
        readiness_status=rain_status,
        relevance_to_depth_modelling="Primary meteorological forcing for surface runoff volume and flash inundation accumulation.",
        source_and_format="Open-Meteo ERA5 hourly reanalysis CSV + synthetic Koshi rainfall time-series.",
        spatial_coverage_and_resolution="~25 km grid cell for ERA5 (Point proxy at Lat 26.87°N, Lon 87.16°E).",
        temporal_coverage_and_frequency="Hourly frequency; covers 2017 & 2024 monsoon seasons (June–September).",
        physical_units="mm/h (intensity), mm (3h, 6h, 24h accumulations).",
        missing_data_and_quality_issues="ERA5 25 km grid averages smooth out intense localized mountain cloudbursts; in-situ DHM AWS automatic rain gauges are unavailable via automated REST API.",
        suitability_for_current_prototype="SUITABLE for area-level runoff proxy and multi-horizon risk scoring; INSUFFICIENT for street-scale hydrodynamic water depth.",
        additional_data_needed_for_operational_use="Automated API telemetry from high-altitude DHM mountain rain gauges (Chatara 1204, Dharan 1206) and calibrated radar rainfall (GPM IMERG 10 km / dual-pol Doppler).",
    )

    # 2. Elevation and Digital Elevation Models (DEM)
    dem_item = InputReadinessItem(
        input_name="Elevation and Digital Elevation Models (DEM)",
        readiness_status="PARTIALLY_AVAILABLE",
        relevance_to_depth_modelling="Foundational geometric boundary for hydraulic head, gravity drainage routing, and stage-to-inundation mapping.",
        source_and_format="Copernicus DEM GLO-30 / SRTM 30m raster (GeoTIFF, referenced in GIS specifications).",
        spatial_coverage_and_resolution="30-meter horizontal resolution; global coverage spanning Koshi basin.",
        temporal_coverage_and_frequency="Static baseline topography (acquisition period 2011–2015).",
        physical_units="Meters above sea level (WGS84 ellipsoidal / EGM2008 geoid).",
        missing_data_and_quality_issues="30m resolution is far too coarse to resolve urban roadside culverts, drainage ditches, road embankments, and channel levee crests in the flat Terai plain (vertical RMSE ~1.5m, often exceeding flood depth).",
        suitability_for_current_prototype="SUITABLE for macroscopic basin slope and coarse terrain visualization; INSUFFICIENT for sub-meter floodwater depth estimation.",
        additional_data_needed_for_operational_use="High-resolution airborne LiDAR or drone photogrammetry DEM (1-meter resolution, vertical accuracy <= 0.15 m) for settlement floodplains.",
    )

    # 3. Terrain Slope and Low-Lying Depressions
    slope_item = InputReadinessItem(
        input_name="Terrain Slope and Low-Lying Topographic Depressions",
        readiness_status="PARTIALLY_AVAILABLE",
        relevance_to_depth_modelling="Determines flow velocity, ponding potential, and water surface gradient along drainage paths.",
        source_and_format="Derivable from 30m DEM via spatial gradient and Topographic Wetness Index (TWI) algorithms.",
        spatial_coverage_and_resolution="30-meter resolution across Barahachhetra / Chatara study area.",
        temporal_coverage_and_frequency="Static baseline.",
        physical_units="Degrees slope (0°–90°) or percentage gradient; TWI unitless index.",
        missing_data_and_quality_issues="Flat alluvial Terai plain features gradients < 0.1%, causing flow direction algorithms (D8, D-infinity) to fail without artificial stream burning.",
        suitability_for_current_prototype="SUITABLE for relative hazard indexing; INSUFFICIENT for hydrodynamic ponding depth calculation.",
        additional_data_needed_for_operational_use="Hydro-conditioned DEM with culvert and bridge enforcement (stream burning) to avoid false damming artifacts.",
    )

    # 4. Drainage Density, Capacity, and Blockage Information
    drainage_item = InputReadinessItem(
        input_name="Drainage Network Density, Channel Capacity, and Blockages",
        readiness_status="MISSING",
        relevance_to_depth_modelling="Directly governs whether surface runoff drains safely or ponds into streets and agricultural parcels.",
        source_and_format="None available in repository or public Nepal municipal repositories.",
        spatial_coverage_and_resolution="Unmapped for Barahachhetra Ward 2 rural drainage networks.",
        temporal_coverage_and_frequency="No real-time sensor feeds or maintenance logs.",
        physical_units="m3/s drainage discharge capacity; percentage trash-rack blockage.",
        missing_data_and_quality_issues="Complete data void: no culvert dimensions, no invert elevations, no debris accumulation records.",
        suitability_for_current_prototype="UNAVAILABLE. Prototype cannot model localized drainage surcharge.",
        additional_data_needed_for_operational_use="Municipal stormwater GIS asset inventory (culvert dimensions, outfall locations, invert levels) and community-reported blockage telemetry.",
    )

    # 5. River Channel Bathymetry and Water-Level Measurements
    river_item = InputReadinessItem(
        input_name="River Channel Bathymetry and Continuous Water-Level Records",
        readiness_status="REQUIRES_VALIDATION",
        relevance_to_depth_modelling="Essential for hydraulic backwater curves, bankfull discharge calculation, and overbank inundation depth.",
        source_and_format="DHM Chatara Station 695 benchmark thresholds (Warning: 6.0m, Danger: 7.0m); GloFAS reanalysis discharge proxy.",
        spatial_coverage_and_resolution="Single point station (Lat 26.87°N, Lon 87.16°E); no cross-sectional bathymetry surveys.",
        temporal_coverage_and_frequency="Hourly benchmark specifications documented; live automated DHM API offline.",
        physical_units="Meters river stage (W_t), m3/s discharge (Q_t).",
        missing_data_and_quality_issues="River cross-section geometry (channel bottom topography below water surface) is completely absent. Without channel bathymetry, river water level cannot be translated into floodplain inundation depth.",
        suitability_for_current_prototype="SUITABLE for threshold-based upstream hazard warning; INSUFFICIENT for continuous water depth simulation.",
        additional_data_needed_for_operational_use="Acoustic Doppler Current Profiler (ADCP) cross-sectional bathymetry surveys for Sapta Koshi reach from Chatara to Koshi Barrage, plus restored DHM telemetry.",
    )

    # 6. Historical Flood Extent and Observed Flood Depth (Ground Truth)
    extent_item = InputReadinessItem(
        input_name="Historical Flood Extent Polygons and Ground-Truth Depth Observations",
        readiness_status="PARTIALLY_AVAILABLE",
        relevance_to_depth_modelling="Critical for model calibration, loss function formulation, and empirical depth validation.",
        source_and_format="Sentinel-2 optical NDWI/MNDWI flood extent polygons (Member 2 GIS pipeline).",
        spatial_coverage_and_resolution="10-meter optical pixels across Sapta Koshi floodplain.",
        temporal_coverage_and_frequency="Discrete satellite overpasses (5-day revisit for Sentinel-2, often cloud-obscured during monsoon).",
        physical_units="Binary water presence (0/1); area in km2; NO DEPTH MEASUREMENTS.",
        missing_data_and_quality_issues="CRITICAL GAP: Satellite optical and radar sensors detect surface water presence/extent, NOT water depth. High-water marks (HWM), peg readings, or field-surveyed flood depths are absent.",
        suitability_for_current_prototype="Extent is SUITABLE for 2D spatial validation; Depth is MISSING and CANNOT BE VALIDATED against real observations.",
        additional_data_needed_for_operational_use="Post-flood field survey depth measurements, citizen water-level geotags, or calibrated ultrasonic river staff gauges.",
    )

    # 7. Soil Infiltration, Land Use, and Surface Roughness
    soil_item = InputReadinessItem(
        input_name="Soil Infiltration, Land Cover, and Surface Roughness (Manning's n)",
        readiness_status="PARTIALLY_AVAILABLE",
        relevance_to_depth_modelling="Determines runoff infiltration loss (SCS Curve Number) and hydraulic flow friction resistance.",
        source_and_format="Global FAO Harmonized World Soil Database (HWSD) & ESA WorldCover 10m land cover.",
        spatial_coverage_and_resolution="10m land cover; 1 km soil hydrologic group.",
        temporal_coverage_and_frequency="Annual baseline map (2020/2021).",
        physical_units="Hydrologic Soil Group (A/B/C/D); Manning's n roughness coefficient (0.025–0.150).",
        missing_data_and_quality_issues="Uncalibrated infiltration rates can create +/- 40% errors in overland runoff volume in tropical monsoon soils.",
        suitability_for_current_prototype="SUITABLE for relative runoff retention indexing; requires hydraulic calibration.",
        additional_data_needed_for_operational_use="In-situ double-ring infiltrometer soil tests in Sunsari farming zones.",
    )

    # 8. Simulated IoT Water-Level Readings
    iot_item = InputReadinessItem(
        input_name="Simulated or Deployed IoT Water-Level Sensor Feeds",
        readiness_status="MISSING",
        relevance_to_depth_modelling="Provides dense real-time ground truth for boundary assimilation and automated depth calibration.",
        source_and_format="None present in active workspace.",
        spatial_coverage_and_resolution="No sensor nodes deployed.",
        temporal_coverage_and_frequency="None.",
        physical_units="Centimeters or meters water depth.",
        missing_data_and_quality_issues="Sensor hardware network is not yet deployed.",
        suitability_for_current_prototype="MISSING. Do not invent simulated sensor readings without explicit demo fixtures.",
        additional_data_needed_for_operational_use="Deployment of solar-powered LoRaWAN ultrasonic or radar distance sensors on Chatara bridge and Barahachhetra drainage culverts.",
    )

    inputs_list = [rain_item, dem_item, slope_item, drainage_item, river_item, extent_item, soil_item, iot_item]

    counts = {
        "AVAILABLE": sum(1 for i in inputs_list if i.readiness_status == "AVAILABLE"),
        "PARTIALLY_AVAILABLE": sum(1 for i in inputs_list if i.readiness_status == "PARTIALLY_AVAILABLE"),
        "MISSING": sum(1 for i in inputs_list if i.readiness_status == "MISSING"),
        "REQUIRES_VALIDATION": sum(1 for i in inputs_list if i.readiness_status == "REQUIRES_VALIDATION"),
    }

    # Recommended modelling approach
    recommendation = {
        "recommended_approach": "Height Above Nearest Drainage (HAND) + Stage-Discharge Rating Curve (Empirical)",
        "rationale": (
            "Because cross-sectional channel bathymetry, street drainage capacity, and ground-truth depth observations "
            "are completely absent, numerical 2D hydrodynamic simulation (e.g. full shallow-water equations in HEC-RAS 2D) "
            "or ML depth regression would suffer from severe unconstrained equifinality. "
            "The HAND method provides a robust, physically grounded topographic relative head model once DHM stage is integrated, "
            "avoiding the fabrication of unverified sub-meter water depths."
        ),
        "prototype_recommendation": (
            "Retain discrete 4-tier risk classification (+1h, +3h, +6h) for the operational baseline. "
            "Document depth estimation as an experimental research track (P2/P3) until channel bathymetry is surveyed."
        ),
    }

    unsupported = [
        {
            "approach": "Direct Machine Learning Regression of Flood Depth (meters)",
            "why_unsupported": (
                "Zero ground-truth water depth training labels exist in the historical record. "
                "Training an ML regressor on synthetic or uncalibrated depth labels would violate core engineering safety rules "
                "and produce misleading depth predictions for disaster response."
            ),
        },
        {
            "approach": "Fully Dynamic 2D Hydrodynamic Modeling (e.g. shallow-water equations)",
            "why_unsupported": (
                "Requires cross-sectional river bathymetry, 1-meter LiDAR topography, and culvert geometry. "
                "Applying 30m DEM directly results in vertical errors (1.5 m) exceeding typical flood depths, "
                "creating massive numerical instabilities and false damming."
            ),
        },
    ]

    next_steps = [
        "1. Maintain clear separation between categorical flood risk (low/moderate/high/critical) and floodwater depth.",
        "2. Coordinate with Nepal DHM / Department of Water Resources & Irrigation (DWRI) to obtain Sapta Koshi Chatara ADCP river cross-section bathymetry.",
        "3. Ingest high-resolution Copernicus DEM or national LiDAR tiles for Barahachhetra Ward 2 when released.",
        "4. Prototype a HAND (Height Above Nearest Drainage) terrain layer using the DEM as a relative flood hazard index.",
        "5. Deploy low-cost ultrasonic IoT staff gauges on critical bridges to establish true depth calibration points.",
    ]

    return DepthModellingReadinessReport(
        report_title="FloodLens AI — Flood-Depth Modelling Input Readiness Assessment",
        assessment_timestamp=now_iso,
        study_area="Sapta Koshi Basin — Barahachhetra / Chatara, Sunsari District, Nepal Terai",
        overall_readiness_status="INSUFFICIENT_FOR_OPERATIONAL_DEPTH",
        inputs_evaluated_count=len(inputs_list),
        available_count=counts["AVAILABLE"],
        partially_available_count=counts["PARTIALLY_AVAILABLE"],
        missing_count=counts["MISSING"],
        requires_validation_count=counts["REQUIRES_VALIDATION"],
        inputs=inputs_list,
        recommended_modelling_approach=recommendation,
        unsupported_modelling_approaches=unsupported,
        next_steps_action_plan=next_steps,
    )


def export_depth_readiness_report(output_path: Union[str, Path]) -> DepthModellingReadinessReport:
    """Run assessment and write structured JSON summary to reports directory."""
    rep = evaluate_flood_depth_inputs()
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(rep.to_dict(), f, indent=2)
    logger.info(f"Depth input readiness report saved to {out}")
    return rep


if __name__ == "__main__":
    report = evaluate_flood_depth_inputs()
    print(f"\n{'='*70}\n{report.report_title}\n{'='*70}")
    print(f"Study Area: {report.study_area}")
    print(f"Overall Status: {report.overall_readiness_status}")
    print(f"Evaluated: {report.inputs_evaluated_count} inputs "
          f"({report.available_count} Available, {report.partially_available_count} Partial, "
          f"{report.missing_count} Missing, {report.requires_validation_count} Needs Validation)")
    print(f"\nRecommended Approach: {report.recommended_modelling_approach['recommended_approach']}")
    print(f"\nInputs Summary:")
    for inp in report.inputs:
        print(f"  [{inp.readiness_status:^19}] {inp.input_name}")
    print(f"{'='*70}\n")
