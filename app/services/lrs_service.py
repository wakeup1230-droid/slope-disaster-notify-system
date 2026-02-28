"""Linear Referencing System (LRS) service backed by a grid-hash index.

This service loads road milepost marker data from CSV at startup, builds a
fixed grid spatial index, and provides:
- forward lookup: WGS84 (lat, lon) -> nearest milepost candidates
- reverse lookup: (road, milepost km) -> approximate WGS84 coordinate

Distance calculations use WGS84 geodesic distance via ``pyproj.Geod``.
No mutable shared state is modified after initialization, so the service is
safe for concurrent read usage.
"""

from dataclasses import dataclass
from math import cos, floor, radians
from pathlib import Path
import csv
import logging

from pyproj import Geod

from app.core.logging_config import get_logger


LOGGER: logging.Logger = get_logger(__name__)
GEOD = Geod(ellps="WGS84")


@dataclass(frozen=True)
class MilepostCandidate:
    road: str
    milepost_km: float
    milepost_display: str
    distance_m: float
    confidence: float
    is_interpolated: bool
    nearest_markers: list[str]


@dataclass(frozen=True)
class _Marker:
    road: str
    milepost_km: float
    milepost_display: str
    lat: float
    lon: float


class LRSService:
    def __init__(
        self,
        csv_path: Path,
        grid_size_deg: float = 0.01,
        max_distance_m: float = 500.0,
    ) -> None:
        self.grid_size_deg: float = float(grid_size_deg)
        self.max_distance_m: float = float(max_distance_m)

        self._markers: tuple[_Marker, ...] = ()
        self._grid_index: dict[tuple[int, int], tuple[int, ...]] = {}
        self._road_markers: dict[str, tuple[_Marker, ...]] = {}
        self._road_ranges: dict[str, tuple[float, float]] = {}

        self._load_data(csv_path)

    def forward_lookup(
        self,
        lat: float,
        lon: float,
        road_filter: str | None = None,
    ) -> list[MilepostCandidate]:
        if not self._markers:
            return []

        road_filter_norm = road_filter.strip() if road_filter else None
        base_cell = self._grid_cell(lat, lon)

        nearby_indices: list[int] = []
        for d_lat in (-1, 0, 1):
            for d_lon in (-1, 0, 1):
                cell = (base_cell[0] + d_lat, base_cell[1] + d_lon)
                nearby_indices.extend(self._grid_index.get(cell, ()))

        if not nearby_indices:
            return []

        nearby: list[tuple[_Marker, float]] = []
        for idx in nearby_indices:
            marker = self._markers[idx]
            if road_filter_norm and marker.road != road_filter_norm:
                continue
            distance_m = self._distance_m(lat, lon, marker.lat, marker.lon)
            if distance_m <= self.max_distance_m:
                nearby.append((marker, distance_m))

        if not nearby:
            return []

        nearby.sort(key=lambda item: item[1])

        results: list[MilepostCandidate] = []
        for marker, distance_m in nearby[:10]:
            results.append(
                MilepostCandidate(
                    road=marker.road,
                    milepost_km=marker.milepost_km,
                    milepost_display=marker.milepost_display,
                    distance_m=distance_m,
                    confidence=self._confidence(distance_m, is_interpolated=False, interpolation_quality=1.0),
                    is_interpolated=False,
                    nearest_markers=[marker.milepost_display],
                )
            )

        roads_seen: dict[str, tuple[_Marker, float]] = {}
        for marker, distance_m in nearby:
            if marker.road not in roads_seen:
                roads_seen[marker.road] = (marker, distance_m)

        for road, (nearest_marker, nearest_dist) in roads_seen.items():
            road_points = self._road_markers.get(road, ())
            if len(road_points) < 2:
                continue

            nearest_idx = 0
            best_km_diff = abs(road_points[0].milepost_km - nearest_marker.milepost_km)
            for idx in range(1, len(road_points)):
                km_diff = abs(road_points[idx].milepost_km - nearest_marker.milepost_km)
                if km_diff < best_km_diff:
                    best_km_diff = km_diff
                    nearest_idx = idx

            if nearest_idx == 0:
                lower, upper = road_points[0], road_points[1]
            elif nearest_idx == len(road_points) - 1:
                lower, upper = road_points[-2], road_points[-1]
            else:
                a = road_points[nearest_idx - 1]
                b = road_points[nearest_idx]
                c = road_points[nearest_idx + 1]
                d_ab = self._distance_m(lat, lon, a.lat, a.lon) + self._distance_m(lat, lon, b.lat, b.lon)
                d_bc = self._distance_m(lat, lon, b.lat, b.lon) + self._distance_m(lat, lon, c.lat, c.lon)
                lower, upper = (a, b) if d_ab <= d_bc else (b, c)

            interpolated = self._interpolate_on_segment(lower, upper, lat, lon)
            if interpolated is None:
                continue

            interp_lat, interp_lon, milepost_km = interpolated
            interp_dist = self._distance_m(lat, lon, interp_lat, interp_lon)
            if interp_dist > self.max_distance_m:
                continue

            seg_km = abs(upper.milepost_km - lower.milepost_km)
            interpolation_quality = max(0.5, 1.0 - min(seg_km, 2.0) / 4.0)
            results.append(
                MilepostCandidate(
                    road=road,
                    milepost_km=milepost_km,
                    milepost_display=self._format_milepost(milepost_km),
                    distance_m=min(interp_dist, nearest_dist),
                    confidence=self._confidence(
                        interp_dist,
                        is_interpolated=True,
                        interpolation_quality=interpolation_quality,
                    ),
                    is_interpolated=True,
                    nearest_markers=[lower.milepost_display, upper.milepost_display],
                )
            )

        deduped: dict[tuple[str, int, bool], MilepostCandidate] = {}
        for candidate in results:
            key = (candidate.road, int(round(candidate.milepost_km * 1000)), candidate.is_interpolated)
            existing = deduped.get(key)
            if existing is None or candidate.distance_m < existing.distance_m:
                deduped[key] = candidate

        ordered = list(deduped.values())
        ordered.sort(key=lambda c: (c.distance_m, -c.confidence, c.road, c.milepost_km))
        return ordered

    def reverse_lookup(self, road: str, milepost_km: float) -> tuple[float, float] | None:
        road_norm = road.strip()
        points = self._road_markers.get(road_norm, ())
        if not points:
            return None

        if milepost_km < points[0].milepost_km or milepost_km > points[-1].milepost_km:
            return None

        for point in points:
            if abs(point.milepost_km - milepost_km) < 1e-9:
                return (point.lat, point.lon)

        lower: _Marker | None = None
        upper: _Marker | None = None
        for idx in range(1, len(points)):
            if points[idx - 1].milepost_km <= milepost_km <= points[idx].milepost_km:
                lower = points[idx - 1]
                upper = points[idx]
                break

        if lower is None or upper is None:
            return None

        km_span = upper.milepost_km - lower.milepost_km
        if km_span <= 0:
            return (lower.lat, lower.lon)

        ratio = (milepost_km - lower.milepost_km) / km_span
        lat = lower.lat + ratio * (upper.lat - lower.lat)
        lon = lower.lon + ratio * (upper.lon - lower.lon)
        return (lat, lon)

    def get_roads(self) -> list[str]:
        roads = list(self._road_markers.keys())
        roads.sort()
        return roads

    def get_road_range(self, road: str) -> tuple[float, float] | None:
        return self._road_ranges.get(road.strip())

    def _load_data(self, csv_path: Path) -> None:
        if not csv_path.exists() or not csv_path.is_file():
            LOGGER.warning("LRS CSV file not found: %s", csv_path)
            return

        try:
            dialect = csv.excel
            with csv_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
                sample = csv_file.read(4096)
                if sample:
                    dialect = csv.Sniffer().sniff(sample)
            delimiter = dialect.delimiter
        except (csv.Error, OSError):
            delimiter = ","

        rows: list[dict[str, str]] = []
        columns: dict[str, str] = {}
        try:
            with csv_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
                reader = csv.DictReader(csv_file, delimiter=delimiter)
                if reader.fieldnames is None:
                    LOGGER.warning("LRS CSV has no header row: %s", csv_path)
                    return
                for raw_col in reader.fieldnames:
                    col = str(raw_col).replace("\ufeff", "").strip()
                    columns[col] = col
                for row in reader:
                    cleaned: dict[str, str] = {}
                    for key, value in row.items():
                        if key is None:
                            continue
                        normalized_key = str(key).replace("\ufeff", "").strip()
                        cleaned[normalized_key] = "" if value is None else str(value)
                    rows.append(cleaned)
        except OSError as exc:
            LOGGER.warning("Failed to read LRS CSV %s: %s", csv_path, exc)
            return

        if not rows:
            LOGGER.warning("LRS CSV is empty: %s", csv_path)
            return

        road_col = self._pick_column(columns, ("公路編號", "路線", "road"))
        lat_col = self._pick_column(columns, ("坐標-Y-WGS84", "緯度", "lat", "latitude"))
        lon_col = self._pick_column(columns, ("坐標-X-WGS84", "經度", "lon", "longitude"))
        milepost_display_col = self._pick_column(columns, ("起點樁號", "里程樁號", "樁號"))
        milepost_value_col = self._pick_column(columns, ("牌面內容", "里程", "milepost", "km"))

        if not road_col or not lat_col or not lon_col:
            LOGGER.warning("LRS CSV missing required columns: %s", csv_path)
            return

        marker_list: list[_Marker] = []
        road_km_points: dict[str, dict[float, list[tuple[float, float, str]]]] = {}

        for row in rows:
            road_raw = row.get(road_col)
            road = str(road_raw).strip() if road_raw is not None else ""
            if not road or road.lower() == "nan":
                continue

            lat = self._as_float(row.get(lat_col))
            lon = self._as_float(row.get(lon_col))
            if lat is None or lon is None:
                continue

            marker_text = ""
            if milepost_display_col:
                marker_val = row.get(milepost_display_col)
                marker_text = "" if marker_val is None else str(marker_val).strip()

            milepost_km = self._parse_milepost_km(marker_text)
            if milepost_km is None and milepost_value_col:
                milepost_km = self._as_float(row.get(milepost_value_col))

            if milepost_km is None:
                continue

            milepost_display = self._format_milepost(milepost_km) if not marker_text else marker_text
            marker = _Marker(
                road=road,
                milepost_km=milepost_km,
                milepost_display=milepost_display,
                lat=lat,
                lon=lon,
            )
            marker_list.append(marker)

            road_bucket = road_km_points.setdefault(road, {})
            km_bucket = road_bucket.setdefault(milepost_km, [])
            km_bucket.append((lat, lon, milepost_display))

        if not marker_list:
            LOGGER.warning("No valid LRS markers loaded from %s", csv_path)
            return

        grid_build: dict[tuple[int, int], list[int]] = {}
        for idx, marker in enumerate(marker_list):
            cell = self._grid_cell(marker.lat, marker.lon)
            if cell not in grid_build:
                grid_build[cell] = []
            grid_build[cell].append(idx)

        road_markers: dict[str, tuple[_Marker, ...]] = {}
        road_ranges: dict[str, tuple[float, float]] = {}
        for road, km_map in road_km_points.items():
            points: list[_Marker] = []
            sorted_km = list(km_map.keys())
            sorted_km.sort()
            for km in sorted_km:
                bucket = km_map[km]
                lat_sum = 0.0
                lon_sum = 0.0
                display = bucket[0][2]
                for lat, lon, _ in bucket:
                    lat_sum += lat
                    lon_sum += lon
                count = float(len(bucket))
                points.append(
                    _Marker(
                        road=road,
                        milepost_km=km,
                        milepost_display=display,
                        lat=lat_sum / count,
                        lon=lon_sum / count,
                    )
                )

            if points:
                road_markers[road] = tuple(points)
                road_ranges[road] = (points[0].milepost_km, points[-1].milepost_km)

        self._markers = tuple(marker_list)
        self._grid_index = {cell: tuple(indices) for cell, indices in grid_build.items()}
        self._road_markers = road_markers
        self._road_ranges = road_ranges

        LOGGER.info(
            "LRS initialized: markers=%d roads=%d grid_cells=%d",
            len(self._markers),
            len(self._road_markers),
            len(self._grid_index),
        )

    def _grid_cell(self, lat: float, lon: float) -> tuple[int, int]:
        return (int(floor(lat / self.grid_size_deg)), int(floor(lon / self.grid_size_deg)))

    @staticmethod
    def _pick_column(columns: dict[str, str], candidates: tuple[str, ...]) -> str | None:
        for candidate in candidates:
            if candidate in columns:
                return columns[candidate]
        return None

    @staticmethod
    def _as_float(value: object) -> float | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text or text.lower() == "nan":
            return None
        cleaned = text.replace("K", "").replace("+", ".")
        try:
            return float(cleaned)
        except ValueError:
            return None

    @staticmethod
    def _parse_milepost_km(text: str) -> float | None:
        value = text.strip()
        if not value:
            return None

        if "K" in value:
            left, right = value.split("K", 1)
            try:
                km = float(left.strip())
            except ValueError:
                return None

            right = right.strip()
            if right.startswith("+"):
                right = right[1:]
            if not right:
                return km

            meters = ""
            for ch in right:
                if ch.isdigit() or ch == ".":
                    meters += ch
                else:
                    break
            if not meters:
                return km

            try:
                meters_float = float(meters)
            except ValueError:
                return km
            return km + (meters_float / 1000.0)

        try:
            return float(value)
        except ValueError:
            return None

    @staticmethod
    def _format_milepost(km_value: float) -> str:
        km_int = int(km_value)
        meters = int(round((km_value - km_int) * 1000.0))
        if meters == 1000:
            km_int += 1
            meters = 0
        return f"{km_int}K+{meters:03d}"

    @staticmethod
    def _distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        _, _, dist = GEOD.inv(lon1, lat1, lon2, lat2)  # pyright: ignore[reportAny]
        return abs(float(dist))  # pyright: ignore[reportAny]

    @staticmethod
    def _interpolate_on_segment(
        lower: _Marker,
        upper: _Marker,
        query_lat: float,
        query_lon: float,
    ) -> tuple[float, float, float] | None:
        mean_lat_rad = radians((lower.lat + upper.lat) / 2.0)
        lon_scale = cos(mean_lat_rad)

        dx = (upper.lon - lower.lon) * lon_scale
        dy = upper.lat - lower.lat
        seg_len_sq = dx * dx + dy * dy
        if seg_len_sq <= 0.0:
            return None

        qx = (query_lon - lower.lon) * lon_scale
        qy = query_lat - lower.lat
        ratio = (qx * dx + qy * dy) / seg_len_sq
        if ratio < 0.0:
            ratio = 0.0
        elif ratio > 1.0:
            ratio = 1.0

        interp_lat = lower.lat + ratio * (upper.lat - lower.lat)
        interp_lon = lower.lon + ratio * (upper.lon - lower.lon)
        interp_km = lower.milepost_km + ratio * (upper.milepost_km - lower.milepost_km)
        return (interp_lat, interp_lon, interp_km)

    def _confidence(self, distance_m: float, is_interpolated: bool, interpolation_quality: float) -> float:
        if distance_m > self.max_distance_m:
            return 0.0

        if distance_m < 50.0:
            base = 0.95 if is_interpolated else 1.0
        elif distance_m < 200.0:
            span = (distance_m - 50.0) / 150.0
            base = (0.88 if is_interpolated else 0.9) - span * (0.08 if is_interpolated else 0.1)
        else:
            span = (distance_m - 200.0) / 300.0
            base = (0.78 if is_interpolated else 0.8) - span * (0.28 if is_interpolated else 0.3)

        confidence = base
        if is_interpolated:
            quality = interpolation_quality
            if quality < 0.0:
                quality = 0.0
            elif quality > 1.0:
                quality = 1.0
            confidence = confidence * (0.85 + quality * 0.15)

        if confidence < 0.0:
            return 0.0
        if confidence > 1.0:
            return 1.0
        return float(confidence)
