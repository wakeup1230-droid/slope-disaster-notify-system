from __future__ import annotations

from pathlib import Path
from typing import Callable, cast

import pytest

from app.services.lrs_service import LRSService


@pytest.fixture
def sample_csv(tmp_path: Path) -> Path:
    csv_path = tmp_path / "test_milepost.csv"
    content = "\n".join(
        [
            "公路編號,坐標-Y-WGS84,坐標-X-WGS84,起點樁號,牌面內容",
            "台7線,24.830000,121.470000,0K+000,0.0",
            "台7線,24.835000,121.475000,1K+000,1.0",
            "台7線,24.840000,121.480000,2K+000,2.0",
            "台7線,24.845000,121.485000,3K+000,3.0",
            "台7線,24.850000,121.490000,4K+000,4.0",
            "台7線,24.855000,121.495000,5K+000,5.0",
            "台3線,25.030000,121.520000,0K+000,0.0",
            "台3線,25.035000,121.525000,1K+000,1.0",
            "台3線,25.040000,121.530000,2K+000,2.0",
        ]
    )
    _ = csv_path.write_text(content + "\n", encoding="utf-8")
    return csv_path


@pytest.fixture
def lrs(sample_csv: Path) -> LRSService:
    return LRSService(csv_path=sample_csv, grid_size_deg=0.01, max_distance_m=2000.0)


def test_load_markers(lrs: LRSService) -> None:
    markers = cast(tuple[object, ...], getattr(lrs, "_markers"))
    assert len(markers) == 9


def test_get_roads(lrs: LRSService) -> None:
    assert lrs.get_roads() == ["台3線", "台7線"]


def test_get_road_range(lrs: LRSService) -> None:
    assert lrs.get_road_range("台7線") == (0.0, 5.0)


def test_forward_lookup_exact(lrs: LRSService) -> None:
    results = lrs.forward_lookup(24.83, 121.47)
    assert results
    assert results[0].road == "台7線"
    assert results[0].milepost_display == "0K+000"


def test_forward_lookup_interpolated(lrs: LRSService) -> None:
    results = lrs.forward_lookup(24.8375, 121.4775)
    interpolated = [candidate for candidate in results if candidate.is_interpolated and candidate.road == "台7線"]
    assert interpolated
    assert abs(interpolated[0].milepost_km - 1.5) < 0.1


def test_forward_lookup_road_filter(lrs: LRSService) -> None:
    results = lrs.forward_lookup(25.035, 121.525, road_filter="台3線")
    assert results
    assert all(candidate.road == "台3線" for candidate in results)


def test_forward_lookup_too_far(lrs: LRSService) -> None:
    assert lrs.forward_lookup(0.0, 0.0) == []


def test_forward_lookup_no_markers(tmp_path: Path) -> None:
    empty_csv = tmp_path / "empty.csv"
    _ = empty_csv.write_text("公路編號,坐標-Y-WGS84,坐標-X-WGS84,起點樁號,牌面內容\n", encoding="utf-8")
    service = LRSService(csv_path=empty_csv)
    assert service.forward_lookup(24.83, 121.47) == []


def test_reverse_lookup_exact(lrs: LRSService) -> None:
    result = lrs.reverse_lookup("台7線", 3.0)
    assert result is not None
    lat, lon = result
    assert abs(lat - 24.845) < 1e-9
    assert abs(lon - 121.485) < 1e-9


def test_reverse_lookup_interpolated(lrs: LRSService) -> None:
    result = lrs.reverse_lookup("台7線", 2.5)
    assert result is not None
    lat, lon = result
    assert abs(lat - 24.8425) < 1e-6
    assert abs(lon - 121.4825) < 1e-6


def test_reverse_lookup_out_of_range(lrs: LRSService) -> None:
    assert lrs.reverse_lookup("台7線", 8.0) is None


def test_reverse_lookup_unknown_road(lrs: LRSService) -> None:
    assert lrs.reverse_lookup("台9線", 1.0) is None


def test_parse_milepost_km() -> None:
    parse_milepost = cast(Callable[[str], float | None], getattr(LRSService, "_parse_milepost_km"))
    assert parse_milepost("3K+500") == 3.5
    assert parse_milepost("10K") == 10.0
    # Case-insensitive K
    assert parse_milepost("12k+400") == 12.4
    assert parse_milepost("12K+400") == 12.4
    # Decimal km (e.g. 12.4 = 12K+400)
    assert parse_milepost("12.4") == 12.4
    # No plus sign (12K400)
    assert parse_milepost("12K400") == 12.4
    assert parse_milepost("12k400") == 12.4
    # Edge cases
    assert parse_milepost("0K+000") == 0.0
    assert parse_milepost("5k") == 5.0
    assert parse_milepost("") is None
    assert parse_milepost("abc") is None


def test_format_milepost() -> None:
    format_milepost = cast(Callable[[float], str], getattr(LRSService, "_format_milepost"))
    assert format_milepost(3.5) == "3K+500"
    assert format_milepost(10.0) == "10K+000"
