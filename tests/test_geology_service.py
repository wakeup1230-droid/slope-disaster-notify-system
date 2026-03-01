from __future__ import annotations

from pathlib import Path

import pytest

from app.services.geology_service import GeologyQueryResult, GeologyService


@pytest.fixture(scope="module")
def geology_service() -> GeologyService:
    shapefile_dir = Path(__file__).resolve().parents[1] / "Input" / "17_易淹水計畫流域地質圖"
    return GeologyService(shapefile_dir=shapefile_dir)


def test_geology_service_initialization_with_real_shapefiles(geology_service: GeologyService) -> None:
    assert geology_service is not None


def test_query_geology_taipei(geology_service: GeologyService) -> None:
    result = geology_service.query_geology(lon=121.5, lat=25.05)
    assert result is not None
    assert result.stratum_name == "沖積層"


def test_query_nearby_faults_returns_list(geology_service: GeologyService) -> None:
    faults = geology_service.query_nearby_faults(lon=121.5, lat=25.05)
    assert isinstance(faults, list)


def test_query_nearby_folds_returns_list(geology_service: GeologyService) -> None:
    folds = geology_service.query_nearby_folds(lon=121.5, lat=25.05)
    assert isinstance(folds, list)


def test_query_all_returns_result_object(geology_service: GeologyService) -> None:
    result = geology_service.query_all(lon=121.5, lat=25.05)
    assert isinstance(result, GeologyQueryResult)
    assert result.query_lon == 121.5
    assert result.query_lat == 25.05


def test_to_display_dict_has_expected_keys(geology_service: GeologyService) -> None:
    result = geology_service.query_all(lon=121.5, lat=25.05)
    display = geology_service.to_display_dict(result)
    assert isinstance(display, dict)
    assert set(display.keys()) == {"地層名稱", "岩性描述", "鄰近斷層", "鄰近褶皺"}


def test_to_display_text_returns_string(geology_service: GeologyService) -> None:
    result = geology_service.query_all(lon=121.5, lat=25.05)
    text = geology_service.to_display_text(result)
    assert isinstance(text, str)
    assert "地質資訊查詢結果" in text


def test_ocean_coordinate_returns_none_geology(geology_service: GeologyService) -> None:
    result = geology_service.query_all(lon=130.0, lat=30.0)
    assert result.geology is None
