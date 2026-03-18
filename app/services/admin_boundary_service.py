"""Administrative boundary spatial query service backed by ESRI Shapefiles.

This service loads a single village-level boundary shapefile that contains
county (COUN_NA), town (TOWN_NA), and village (VLG_NA) fields.  The
shapefile may be in TWD97 TM2 (EPSG:3826) projection — in that case it is
automatically reprojected to WGS84 (EPSG:4326) at load time so that queries
can be made directly with WGS84 lon/lat.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import geopandas as gpd
from shapely.geometry import Point
from shapely.geometry.base import BaseGeometry

from app.core.logging_config import get_logger

LOGGER: logging.Logger = get_logger(__name__)

# Shapefile field names → result field mapping
_COUNTY_FIELD = "COUN_NA"
_TOWN_FIELD = "TOWN_NA"
_VILLAGE_FIELD = "VLG_NA"
_REQUIRED_FIELDS: tuple[str, ...] = (_COUNTY_FIELD, _TOWN_FIELD, _VILLAGE_FIELD)

# ---------------------------------------------------------------------------
# Result data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AdminBoundaryResult:
    """行政區查詢結果 — 縣市/鄉鎮市區/村里."""

    county_name: str
    """County/city name (e.g. '台東縣')."""

    town_name: str
    """Town/district name (e.g. '台東市')."""

    village_name: str
    """Village/borough name (e.g. '光明里')."""


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class AdminBoundaryService:
    """Spatial query service for Taiwan administrative boundaries.

    Parameters
    ----------
    shapefile_dir:
        Directory containing the village-level boundary shapefile.
        The shapefile must include ``COUN_NA``, ``TOWN_NA``, and ``VLG_NA``
        columns.  TWD97 TM2 data is reprojected to WGS84 automatically.
    """

    _ENCODINGS: tuple[str, ...] = ("utf-8", "big5")

    def __init__(self, shapefile_dir: Path) -> None:
        self._dir: Path = Path(shapefile_dir)
        self._gdf: gpd.GeoDataFrame | None = None
        self._load_shapefile()

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def _load_shapefile(self) -> None:
        """Load the village-level boundary shapefile."""
        if not self._dir.exists():
            LOGGER.warning("Shapefile directory not found: %s", self._dir)
            return

        shapefiles = sorted(self._dir.glob("*.shp"))
        if not shapefiles:
            LOGGER.warning("No shapefile found in directory: %s", self._dir)
            return

        path = shapefiles[0]
        last_exception: Exception | None = None
        for encoding in self._ENCODINGS:
            try:
                gdf = cast(gpd.GeoDataFrame, gpd.read_file(path, encoding=encoding))

                missing = [f for f in _REQUIRED_FIELDS if f not in gdf.columns]
                if missing:
                    LOGGER.warning(
                        "行政區 shapefile missing required fields %s in %s (cols: %s)",
                        missing,
                        path,
                        list(gdf.columns),
                    )
                    return

                # Reproject from TWD97 TM2 → WGS84 if needed
                if gdf.crs is not None and not gdf.crs.equals("EPSG:4326"):
                    LOGGER.info(
                        "Reprojecting %s from %s to EPSG:4326",
                        path.name,
                        gdf.crs,
                    )
                    gdf = cast(gpd.GeoDataFrame, gdf.to_crs("EPSG:4326"))

                _ = gdf.sindex  # Build spatial index

                LOGGER.info(
                    "Loaded %s (行政區): %d records, CRS=%s",
                    path.name,
                    len(gdf),
                    gdf.crs,
                )
                self._gdf = gdf
                return
            except Exception as exc:
                last_exception = exc

        LOGGER.warning(
            "Failed to load shapefile %s with encodings %s",
            path,
            self._ENCODINGS,
            exc_info=last_exception,
        )

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def query(self, lon: float, lat: float) -> AdminBoundaryResult | None:
        """Return county/town/village for the given WGS84 coordinate."""
        if self._gdf is None:
            return None

        pt = Point(lon, lat)

        candidates_idx = list(self._gdf.sindex.query(pt, predicate="intersects"))
        if not candidates_idx:
            LOGGER.debug("query(%.6f, %.6f): no bounding-box hit", lon, lat)
            return None

        for idx in candidates_idx:
            row = self._gdf.iloc[int(idx)]
            geometry = cast(BaseGeometry, row.get("geometry"))
            if geometry is not None and geometry.contains(pt):
                result = AdminBoundaryResult(
                    county_name=str(row.get(_COUNTY_FIELD, "") or ""),
                    town_name=str(row.get(_TOWN_FIELD, "") or ""),
                    village_name=str(row.get(_VILLAGE_FIELD, "") or ""),
                )
                LOGGER.debug(
                    "query(%.6f, %.6f): %s %s %s",
                    lon,
                    lat,
                    result.county_name,
                    result.town_name,
                    result.village_name,
                )
                return result

        LOGGER.debug("query(%.6f, %.6f): no exact polygon hit", lon, lat)
        return None

    # ------------------------------------------------------------------
    # Display helpers
    # ------------------------------------------------------------------

    def to_display_text(self, result: AdminBoundaryResult) -> str:
        """Convert a :class:`AdminBoundaryResult` to a human-readable string."""
        parts = [
            value
            for value in (result.county_name, result.town_name, result.village_name)
            if value
        ]
        return f"📍 行政區：{' '.join(parts)}"
