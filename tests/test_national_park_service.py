# pyright: reportUnknownMemberType=false
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import Polygon

from app.services.national_park_service import NationalParkResult, NationalParkService


@pytest.fixture()
def empty_park_service(tmp_path: Path) -> NationalParkService:
    return NationalParkService(shapefile_dir=tmp_path)


def test_service_initializes_without_shapefiles(tmp_path: Path) -> None:
    service = NationalParkService(shapefile_dir=tmp_path / "missing_dir")
    assert service is not None


def test_query_returns_none_when_no_shapefiles_loaded(empty_park_service: NationalParkService) -> None:
    result = empty_park_service.query(lon=121.5, lat=25.05)
    assert result is None


def test_to_display_text_formats_both_cases(empty_park_service: NationalParkService) -> None:
    in_park = NationalParkResult(park_name="太魯閣國家公園", is_within=True)
    in_park_text = empty_park_service.to_display_text(in_park)
    outside_text = empty_park_service.to_display_text(None)

    assert in_park_text == "🏞️ 位於國家公園範圍：太魯閣國家公園"
    assert outside_text == "✅ 不在國家公園範圍內"


def test_query_with_mock_geodataframe_polygon(tmp_path: Path) -> None:
    polygon = Polygon(
        [
            (121.0, 24.0),
            (122.0, 24.0),
            (122.0, 25.0),
            (121.0, 25.0),
            (121.0, 24.0),
        ],
    )
    parks = gpd.GeoDataFrame(
        {"PARKNAME": ["測試國家公園"]},
        geometry=[polygon],
        crs="EPSG:4326",
    )
    parks.to_file(tmp_path / "mock_park.shp", encoding="utf-8")

    service = NationalParkService(shapefile_dir=tmp_path)

    inside = service.query(lon=121.5, lat=24.5)
    outside = service.query(lon=123.0, lat=26.0)

    assert inside is not None
    assert inside.park_name == "測試國家公園"
    assert inside.is_within is True
    assert outside is None
