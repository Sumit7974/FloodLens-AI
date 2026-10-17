"""Hydrological and meteorological observation monitoring endpoints."""
from typing import Any, Dict, List
from fastapi import APIRouter, Depends, status
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


@router.get(
    "/rivers",
    status_code=status.HTTP_200_OK,
    summary="Get river gauge observations",
)
async def get_river_monitoring(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Retrieve river gauge heights, water trends, and sensor quality flags."""
    sources = db.query(DataSource).filter(DataSource.kind == "river_gauge").all()
    return {
        "status": "active" if sources else "no_configured_sources",
        "stations": [],
        "readings": [],
        "note": "Day 1 baseline skeleton",
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
