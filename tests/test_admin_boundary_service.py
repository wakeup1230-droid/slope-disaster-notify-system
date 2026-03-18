from __future__ import annotations

from pathlib import Path

import geopandas as gpd
from shapely.geometry import Polygon

from app.services.admin_boundary_service import AdminBoundaryResult, AdminBoundaryService


def test_to_display_text_formats_correctly(tmp_path: Path) -> None:
    service = AdminBoundaryService(shapefile_dir=tmp_path / "empty")
    result = AdminBoundaryResult(
        county_name="新北市",
        town_name="新店區",
        village_name="中正里",
    )
    assert service.to_display_text(result) == "📍 行政區：新北市 新店區 中正里"


def test_service_initializes_without_shapefiles(tmp_path: Path) -> None:
    service = AdminBoundaryService(shapefile_dir=tmp_path / "missing")
    assert service is not None


def test_query_returns_none_when_no_shapefiles_loaded(tmp_path: Path) -> None:
    service = AdminBoundaryService(shapefile_dir=tmp_path / "missing")
    assert service.query(lon=121.5, lat=25.05) is None


def test_query_returns_admin_names_from_mock_shapefile(tmp_path: Path) -> None:
    data_dir = tmp_path / "boundary"
    data_dir.mkdir()

    polygon = Polygon([(121.4, 25.0), (121.6, 25.0), (121.6, 25.1), (121.4, 25.1)])

    gdf = gpd.GeoDataFrame(
        [{"COUN_NA": "新北市", "TOWN_NA": "新店區", "VLG_NA": "中正里", "geometry": polygon}],
        crs="EPSG:4326",
    )
    gdf.to_file(data_dir / "boundary.shp", encoding="utf-8")

    service = AdminBoundaryService(shapefile_dir=data_dir)
    result = service.query(lon=121.5, lat=25.05)

    assert result is not None
    assert result.county_name == "新北市"
    assert result.town_name == "新店區"
    assert result.village_name == "中正里"


def test_query_returns_none_outside_polygon(tmp_path: Path) -> None:
    data_dir = tmp_path / "boundary"
    data_dir.mkdir()

    polygon = Polygon([(121.4, 25.0), (121.6, 25.0), (121.6, 25.1), (121.4, 25.1)])

    gdf = gpd.GeoDataFrame(
        [{"COUN_NA": "新北市", "TOWN_NA": "新店區", "VLG_NA": "中正里", "geometry": polygon}],
        crs="EPSG:4326",
    )
    gdf.to_file(data_dir / "boundary.shp", encoding="utf-8")

    service = AdminBoundaryService(shapefile_dir=data_dir)
    result = service.query(lon=120.0, lat=22.0)

    assert result is None


def test_query_reprojects_twd97_to_wgs84(tmp_path: Path) -> None:
    """Verify that a shapefile in TWD97 TM2 (EPSG:3826) is reprojected to
    WGS84 and queried correctly with WGS84 coordinates."""
    data_dir = tmp_path / "boundary"
    data_dir.mkdir()

    # Create polygon in TWD97 TM2 centred on (302173, 2769422) which is
    # approximately WGS84 (121.517, 25.032) — central Taipei.
    polygon = Polygon([
        (301000, 2768000),
        (303500, 2768000),
        (303500, 2771000),
        (301000, 2771000),
    ])

    gdf = gpd.GeoDataFrame(
        [{"COUN_NA": "台北市", "TOWN_NA": "中正區", "VLG_NA": "龍福里", "geometry": polygon}],
        crs="EPSG:3826",
    )
    gdf.to_file(data_dir / "boundary.shp", encoding="utf-8")

    service = AdminBoundaryService(shapefile_dir=data_dir)
    # Query with WGS84 coord that falls inside the reprojected polygon
    result = service.query(lon=121.517, lat=25.032)

    assert result is not None
    assert result.county_name == "台北市"
