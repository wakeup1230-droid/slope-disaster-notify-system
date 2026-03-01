"""Geology spatial query service backed by ESRI Shapefiles.

This service loads three shapefiles from the 易淹水計畫流域地質圖 dataset at
startup and provides spatial queries for auto-populating geology information
when a user shares a GPS coordinate:

- **a1p.shp** (polygons): geological formations → point-in-polygon query
- **b1l.shp** (lines): fault lines → buffer distance query (default 500 m)
- **c1l.shp** (lines): fold lines → buffer distance query (default 500 m)

All shapefiles are encoded in Big5 and projected in EPSG:3826 (TWD97 TM).
Input coordinates are WGS84 (EPSG:4326) and converted automatically.

No mutable shared state is modified after initialisation, so the service is
safe for concurrent read usage.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import pandas as pd
from pyproj import Transformer
from shapely.geometry import Point

from app.core.logging_config import get_logger

LOGGER: logging.Logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Result data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GeologyResult:
    """地質查詢結果 — 地層/岩性."""

    stratum_name: str
    """NAME_C from a1p (e.g. '廬山層清水湖段')."""

    rock_description: str
    """NOTE_C from a1p (e.g. '厚層變質砂岩，偶夾薄層板岩')."""


@dataclass(frozen=True)
class FaultResult:
    """斷層查詢結果."""

    name: str
    """NAME_C from b1l (e.g. '新城斷層')."""

    name_en: str
    """NAME_E — English name (may be empty)."""

    fault_type: str
    """TYPE field — fault classification (may be empty)."""

    distance_m: float
    """Distance in metres from query point to the fault line."""


@dataclass(frozen=True)
class FoldResult:
    """褶皺查詢結果."""

    name: str
    """NAME_C from c1l (e.g. '花蓮向斜')."""

    note: str
    """NOTE_C description (may be empty)."""

    distance_m: float
    """Distance in metres from query point to the fold line."""


@dataclass(frozen=True)
class GeologyQueryResult:
    """Combined geology query result for a single coordinate."""

    geology: GeologyResult | None
    """None when the point falls outside all geological polygons."""

    nearby_faults: list[FaultResult]
    """Faults within the search buffer, sorted by distance. May be empty."""

    nearby_folds: list[FoldResult]
    """Folds within the search buffer, sorted by distance. May be empty."""

    query_lon: float
    """Original WGS84 longitude used for the query."""

    query_lat: float
    """Original WGS84 latitude used for the query."""


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class GeologyService:
    """Spatial query service for geological formation, fault, and fold data.

    Parameters
    ----------
    shapefile_dir:
        Directory containing ``a1p.shp``, ``b1l.shp``, and ``c1l.shp``.
        All three shapefiles must be in EPSG:3826 with Big5 encoding.
    """

    _ENCODING: str = "big5"

    def __init__(self, shapefile_dir: Path) -> None:
        self._dir: Path = Path(shapefile_dir)
        self._transformer: Transformer = Transformer.from_crs(
            "EPSG:4326", "EPSG:3826", always_xy=True,
        )

        self._geology: gpd.GeoDataFrame | None = None
        self._faults: gpd.GeoDataFrame | None = None
        self._folds: gpd.GeoDataFrame | None = None

        self._load_shapefiles()

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def _load_shapefiles(self) -> None:
        """Load all three shapefiles and pre-filter invalid rows."""
        self._geology = self._safe_load("a1p.shp", "地質")
        self._faults = self._safe_load("b1l.shp", "斷層")
        self._folds = self._safe_load("c1l.shp", "褶皺")

        # Drop rows without NAME_C for line shapefiles (faults / folds)
        if self._faults is not None:
            before = len(self._faults)
            self._faults = gpd.GeoDataFrame(self._faults[self._faults["NAME_C"].notna()])  # type: ignore[assignment]
            dropped = before - len(self._faults)  # type: ignore[arg-type]
            if dropped:
                LOGGER.info("b1l: dropped %d rows with empty NAME_C", dropped)

        if self._folds is not None:
            before = len(self._folds)
            self._folds = gpd.GeoDataFrame(self._folds[self._folds["NAME_C"].notna()])  # type: ignore[assignment]
            dropped = before - len(self._folds)  # type: ignore[arg-type]
            if dropped:
                LOGGER.info("c1l: dropped %d rows with empty NAME_C", dropped)

    def _safe_load(self, filename: str, label: str) -> gpd.GeoDataFrame | None:
        """Load a single shapefile, returning *None* on failure."""
        path = self._dir / filename
        if not path.exists():
            LOGGER.warning("Shapefile not found: %s", path)
            return None
        try:
            gdf = gpd.read_file(path, encoding=self._ENCODING)
            # Ensure spatial index is built eagerly
            _ = gdf.sindex
            LOGGER.info(
                "Loaded %s (%s): %d records, CRS=%s",
                filename, label, len(gdf), gdf.crs,
            )
            return gdf
        except Exception:
            LOGGER.warning("Failed to load shapefile %s", path, exc_info=True)
            return None

    # ------------------------------------------------------------------
    # Coordinate helpers
    # ------------------------------------------------------------------

    def _to_epsg3826(self, lon: float, lat: float) -> Point | None:
        """Convert WGS84 (lon, lat) → EPSG:3826 Point, or *None* on error."""
        try:
            x, y = self._transformer.transform(lon, lat)
            return Point(x, y)
        except Exception:
            LOGGER.error(
                "Coordinate transform failed for lon=%s, lat=%s",
                lon, lat, exc_info=True,
            )
            return None

    # ------------------------------------------------------------------
    # Query: geology (point-in-polygon)
    # ------------------------------------------------------------------

    def query_geology(self, lon: float, lat: float) -> GeologyResult | None:
        """Return the geological formation at the given WGS84 coordinate.

        Uses a spatial-index accelerated point-in-polygon test against
        the *a1p* polygon dataset.  Returns ``None`` when the point does
        not fall inside any polygon.
        """
        if self._geology is None:
            return None

        pt = self._to_epsg3826(lon, lat)
        if pt is None:
            return None

        # Spatial index → candidate indices
        candidates_idx = list(self._geology.sindex.query(pt, predicate="intersects"))
        if not candidates_idx:
            LOGGER.debug("query_geology(%.6f, %.6f): no polygon hit", lon, lat)
            return None

        # Exact containment check (sindex returns bounding-box candidates)
        for idx in candidates_idx:
            row = self._geology.iloc[idx]
            if row.geometry.contains(pt):
                name = str(row.get("NAME_C", "") or "")
                note = str(row.get("NOTE_C", "") or "")
                LOGGER.debug(
                    "query_geology(%.6f, %.6f): %s", lon, lat, name,
                )
                return GeologyResult(stratum_name=name, rock_description=note)

        LOGGER.debug("query_geology(%.6f, %.6f): no exact polygon hit", lon, lat)
        return None

    # ------------------------------------------------------------------
    # Query: nearby faults (buffer)
    # ------------------------------------------------------------------

    def query_nearby_faults(
        self,
        lon: float,
        lat: float,
        buffer_m: float = 500.0,
    ) -> list[FaultResult]:
        """Find fault lines within *buffer_m* metres of the WGS84 coordinate.

        Results are deduplicated by fault name (keeping the closest
        segment) and sorted by ascending distance.
        """
        if self._faults is None:
            return []

        pt = self._to_epsg3826(lon, lat)
        if pt is None:
            return []

        buf = pt.buffer(buffer_m)

        # Spatial index filter
        candidates_idx = list(self._faults.sindex.query(buf, predicate="intersects"))
        if not candidates_idx:
            LOGGER.debug("query_nearby_faults(%.6f, %.6f): none within %dm", lon, lat, int(buffer_m))
            return []

        # Compute exact distance & deduplicate by NAME_C
        seen: dict[str, FaultResult] = {}
        for idx in candidates_idx:
            row = self._faults.iloc[idx]
            if not row.geometry.intersects(buf):
                continue
            name = str(row.get("NAME_C", "") or "")
            if not name:
                continue
            dist = pt.distance(row.geometry)
            if name not in seen or dist < seen[name].distance_m:
                seen[name] = FaultResult(
                    name=name,
                    name_en=str(row.get("NAME_E", "") or ""),
                    fault_type=str(row.get("TYPE", "") or "").replace("nan", ""),
                    distance_m=round(dist, 1),
                )

        results = sorted(seen.values(), key=lambda r: r.distance_m)
        LOGGER.debug(
            "query_nearby_faults(%.6f, %.6f): %d faults within %dm",
            lon, lat, len(results), int(buffer_m),
        )
        return results

    # ------------------------------------------------------------------
    # Query: nearby folds (buffer)
    # ------------------------------------------------------------------

    def query_nearby_folds(
        self,
        lon: float,
        lat: float,
        buffer_m: float = 500.0,
    ) -> list[FoldResult]:
        """Find fold lines within *buffer_m* metres of the WGS84 coordinate.

        Results are deduplicated by fold name (keeping the closest
        segment) and sorted by ascending distance.
        """
        if self._folds is None:
            return []

        pt = self._to_epsg3826(lon, lat)
        if pt is None:
            return []

        buf = pt.buffer(buffer_m)

        candidates_idx = list(self._folds.sindex.query(buf, predicate="intersects"))
        if not candidates_idx:
            LOGGER.debug("query_nearby_folds(%.6f, %.6f): none within %dm", lon, lat, int(buffer_m))
            return []

        seen: dict[str, FoldResult] = {}
        for idx in candidates_idx:
            row = self._folds.iloc[idx]
            if not row.geometry.intersects(buf):
                continue
            name = str(row.get("NAME_C", "") or "")
            if not name:
                continue
            dist = pt.distance(row.geometry)
            if name not in seen or dist < seen[name].distance_m:
                note_c = str(row.get("NOTE_C", "") or "")
                if note_c == "nan":
                    note_c = ""
                seen[name] = FoldResult(
                    name=name,
                    note=note_c,
                    distance_m=round(dist, 1),
                )

        results = sorted(seen.values(), key=lambda r: r.distance_m)
        LOGGER.debug(
            "query_nearby_folds(%.6f, %.6f): %d folds within %dm",
            lon, lat, len(results), int(buffer_m),
        )
        return results

    # ------------------------------------------------------------------
    # Combined query
    # ------------------------------------------------------------------

    def query_all(
        self,
        lon: float,
        lat: float,
        buffer_m: float = 500.0,
    ) -> GeologyQueryResult:
        """Run geology + fault + fold queries in one call."""
        return GeologyQueryResult(
            geology=self.query_geology(lon, lat),
            nearby_faults=self.query_nearby_faults(lon, lat, buffer_m),
            nearby_folds=self.query_nearby_folds(lon, lat, buffer_m),
            query_lon=lon,
            query_lat=lat,
        )

    # ------------------------------------------------------------------
    # Display helpers
    # ------------------------------------------------------------------

    def to_display_dict(self, result: GeologyQueryResult) -> dict[str, object]:
        """Convert a :class:`GeologyQueryResult` to a user-facing dict.

        Keys are in Traditional Chinese, suitable for LINE Flex Message
        display or direct JSON serialisation into case records.
        """
        if result.geology:
            stratum = result.geology.stratum_name
            rock = result.geology.rock_description
        else:
            stratum = "(查無資料)"
            rock = ""

        faults = [
            {
                "名稱": f.name,
                "類型": f.fault_type if f.fault_type else "",
                "距離": f"{int(f.distance_m)}m",
            }
            for f in result.nearby_faults
        ]

        folds = [
            {
                "名稱": f.name,
                "距離": f"{int(f.distance_m)}m",
            }
            for f in result.nearby_folds
        ]

        return {
            "地層名稱": stratum,
            "岩性描述": rock,
            "鄰近斷層": faults,
            "鄰近褶皺": folds,
        }

    def to_display_text(self, result: GeologyQueryResult) -> str:
        """Convert a :class:`GeologyQueryResult` to a human-readable string.

        Used for LINE text messages when presenting geology info to the
        user for review.
        """
        lines: list[str] = ["🪨 地質資訊查詢結果"]

        if result.geology:
            lines.append(f"📍 地層：{result.geology.stratum_name}")
            lines.append(f"   岩性：{result.geology.rock_description}")
        else:
            lines.append("📍 地層：(查無資料)")

        if result.nearby_faults:
            lines.append("")
            lines.append("⚠️ 鄰近斷層（500m 內）：")
            for f in result.nearby_faults:
                type_str = f"（{f.fault_type}）" if f.fault_type else ""
                lines.append(f"   • {f.name}{type_str} — {int(f.distance_m)}m")
        else:
            lines.append("\n✅ 500m 內無已知斷層")

        if result.nearby_folds:
            lines.append("")
            lines.append("📐 鄰近褶皺（500m 內）：")
            for f in result.nearby_folds:
                lines.append(f"   • {f.name} — {int(f.distance_m)}m")
        else:
            lines.append("✅ 500m 內無已知褶皺")

        return "\n".join(lines)
