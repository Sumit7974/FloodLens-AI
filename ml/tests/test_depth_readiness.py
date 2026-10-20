"""Unit and integration tests for flood-depth modelling input evaluation.

Verifies:
  - Inspection of all 8 required depth modelling inputs.
  - Correct classification of data readiness (available, partial, missing, validation).
  - Overall readiness status is 'INSUFFICIENT_FOR_OPERATIONAL_DEPTH' (prevents uncalibrated depth fabrication).
  - Recommended and unsupported hydraulic modelling approaches.
  - Serialization and export of the data readiness assessment report.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from ml.src.depth_readiness import (
    DepthModellingReadinessReport,
    InputReadinessItem,
    evaluate_flood_depth_inputs,
    export_depth_readiness_report,
)


def test_evaluate_flood_depth_inputs_structure():
    """Verify that the evaluation checks all 8 required inputs."""
    report = evaluate_flood_depth_inputs()

    assert isinstance(report, DepthModellingReadinessReport)
    assert report.inputs_evaluated_count == 8
    assert len(report.inputs) == 8
    assert report.study_area != ""
    assert report.overall_readiness_status == "INSUFFICIENT_FOR_OPERATIONAL_DEPTH"


def test_required_depth_inputs_present():
    """Verify each of the 8 required inputs is explicitly inspected."""
    report = evaluate_flood_depth_inputs()
    input_names = [inp.input_name.lower() for inp in report.inputs]

    expected_keywords = [
        "rainfall",
        "elevation",
        "slope",
        "drainage",
        "water-level",
        "historical flood",
        "soil",
        "iot",
    ]

    for kw in expected_keywords:
        assert any(kw in name for name in input_names), f"Missing evaluation of input keyword '{kw}'"


def test_input_readiness_items_attributes():
    """Verify every input item contains required scientific metadata."""
    report = evaluate_flood_depth_inputs()

    valid_statuses = {"AVAILABLE", "PARTIALLY_AVAILABLE", "MISSING", "REQUIRES_VALIDATION"}

    for item in report.inputs:
        assert isinstance(item, InputReadinessItem)
        assert item.readiness_status in valid_statuses
        assert item.relevance_to_depth_modelling != ""
        assert item.source_and_format != ""
        assert item.physical_units != ""
        assert item.suitability_for_current_prototype != ""
        assert item.additional_data_needed_for_operational_use != ""

        # Test dictionary serialization
        d = item.to_dict()
        assert isinstance(d, dict)
        assert d["input_name"] == item.input_name
        assert d["readiness_status"] == item.readiness_status


def test_critical_gaps_identified():
    """Verify that missing critical inputs for depth are correctly flagged as MISSING or REQUIRES_VALIDATION."""
    report = evaluate_flood_depth_inputs()

    items_by_name = {inp.input_name: inp for inp in report.inputs}

    # Drainage capacity is a complete data void
    drainage = [v for k, v in items_by_name.items() if "drainage" in k.lower()][0]
    assert drainage.readiness_status == "MISSING"

    # Satellite extent is available, but ground-truth depth observations are absent -> PARTIALLY_AVAILABLE
    obs_depth = [v for k, v in items_by_name.items() if "depth" in k.lower() or "extent" in k.lower()][0]
    assert obs_depth.readiness_status == "PARTIALLY_AVAILABLE"

    # Simulated IoT readings must be missing or require physical validation
    iot = [v for k, v in items_by_name.items() if "iot" in k.lower()][0]
    assert iot.readiness_status in ("MISSING", "REQUIRES_VALIDATION")


def test_recommended_and_unsupported_approaches():
    """Verify scientific recommendation avoids ungrounded ML depth regression."""
    report = evaluate_flood_depth_inputs()

    rec = report.recommended_modelling_approach
    assert "Height Above Nearest Drainage" in rec["recommended_approach"]
    assert "Stage-Discharge" in rec["recommended_approach"]

    unsupported_approaches = [u["approach"] for u in report.unsupported_modelling_approaches]
    assert any("Direct Machine Learning Regression" in app for app in unsupported_approaches)
    assert any("2D Hydrodynamic" in app for app in unsupported_approaches)


def test_export_depth_readiness_report(tmp_path: Path):
    """Verify exporting report to JSON creates valid, loadable JSON with correct schema."""
    out_file = tmp_path / "test_depth_readiness.json"
    rep = export_depth_readiness_report(out_file)

    assert out_file.exists()
    with open(out_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["report_title"] == rep.report_title
    assert data["overall_readiness_status"] == "INSUFFICIENT_FOR_OPERATIONAL_DEPTH"
    assert len(data["inputs"]) == 8
    assert "recommended_modelling_approach" in data
