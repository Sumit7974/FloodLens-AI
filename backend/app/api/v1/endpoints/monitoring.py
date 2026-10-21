"""Hydrological and meteorological observation monitoring endpoints."""
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.data_source import DataSource

router = APIRouter(prefix="/monitoring", tags=["Monitoring"])


@router.get(
    "/weather",
    status_code=status.HTTP_200_OK,
    summary="Get weather observations and rainfall forecasts",
)
async def get_weather_monitoring(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Retrieve weather readings with issue timestamps and provenance."""
    sources = db.query(DataSource).filter(DataSource.kind == "weather").all()
    return {
        "status": "active" if sources else "no_configured_sources",
        "providers": [s.provider for s in sources],
        "readings": [],
        "note": "Day 1 baseline skeleton",
    }


DEFAULT_GAUGE_STATIONS = [
    {
        "station_id": "gauge-chatara",
        "name": "Chatara Hydro-Station",
        "river": "Saptakoshi Main Stem",
        "coordinates": [87.163, 26.871],
        "current_level": 8.18,
        "warning_level": 7.0,
        "danger_level": 8.0,
        "discharge_rate": 14250,
        "trend": "RISING",
        "last_reported_at": "1m ago",
        "battery_level": 98,
        "status": "CRITICAL",
    },
    {
        "station_id": "gauge-barrage",
        "name": "Koshi Barrage Control",
        "river": "Koshi Main Channel",
        "coordinates": [86.918, 26.522],
        "current_level": 74.85,
        "warning_level": 74.0,
        "danger_level": 75.0,
        "discharge_rate": 12980,
        "trend": "RISING",
        "last_reported_at": "3m ago",
        "battery_level": 94,
        "status": "WARNING",
    },
    {
        "station_id": "gauge-mulghat",
        "name": "Mulghat Station",
        "river": "Tamor River",
        "coordinates": [87.332, 26.935],
        "current_level": 4.62,
        "warning_level": 5.0,
        "danger_level": 6.5,
        "discharge_rate": 3150,
        "trend": "RISING",
        "last_reported_at": "5m ago",
        "battery_level": 91,
        "status": "NORMAL",
    },
    {
        "station_id": "gauge-rabuwaghat",
        "name": "Rabuwaghat Station",
        "river": "Dudh Koshi",
        "coordinates": [86.654, 27.268],
        "current_level": 5.12,
        "warning_level": 5.5,
        "danger_level": 7.0,
        "discharge_rate": 2840,
        "trend": "STABLE",
        "last_reported_at": "8m ago",
        "battery_level": 88,
        "status": "NORMAL",
    },
]


@router.get(
    "/rivers",
    status_code=status.HTTP_200_OK,
    summary="Get river gauge observations",
)
async def get_river_monitoring(
    event_id: Optional[str] = Query(None, description="Optional flood event scenario ID"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Retrieve river gauge heights, water trends, and sensor quality flags."""
    return {
        "status": "active",
        "stations": DEFAULT_GAUGE_STATIONS,
        "readings": [],
        "count": len(DEFAULT_GAUGE_STATIONS),
    }


@router.get(
    "/gauges",
    status_code=status.HTTP_200_OK,
    summary="Get river telemetry gauge stations",
)
async def get_gauge_monitoring(
    event_id: Optional[str] = Query(None, description="Optional flood event scenario ID"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Retrieve telemetry stations for flood forecasting and hydrographs."""
    return {
        "status": "active",
        "stations": DEFAULT_GAUGE_STATIONS,
        "readings": [],
        "count": len(DEFAULT_GAUGE_STATIONS),
    }


@router.get(
    "/dams",
    status_code=status.HTTP_200_OK,
    summary="Get verified dam release notices",
)
async def get_dam_monitoring(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Retrieve verified dam status and release schedules."""
    return {
        "notices": [],
        "verified_count": 0,
        "note": "Only verified dam notices are displayed",
    }
