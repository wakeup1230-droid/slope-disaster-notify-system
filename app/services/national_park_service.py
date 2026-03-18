"""National park spatial query service backed by ESRI Shapefiles.

This service loads all available national park boundary shapefiles from a
directory at startup and provides a point-in-polygon query for WGS84
coordinates (EPSG:4326).

Shapefiles may be in TWD97 TM2 (EPSG:3826) projection — in that case they
are automatically reprojected to WGS84 at load time.

Shapefiles may be encoded in UTF-8 or Big5. The service attempts UTF-8 first
and falls back to Big5.

No mutable shared state is modified after initialisation, so the service is
safe for concurrent read usage.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import geopandas as gpd
from shapely.geometry import Point
from shapely.geometry.base import BaseGeometry

from app.core.logging_config import get_logger

LOGGER: logging.Logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Result data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NationalParkResult:
    """國家公園查詢結果."""

    park_name: str
    """國家公園名稱 (e.g. '太魯閣國家公園')."""

    is_within: bool
    """Always ``True`` when returned by :meth:`NationalParkService.query`."""


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class NationalParkService:
    """Spatial query service for Taiwan national park boundaries.

    Parameters
    ----------
    shapefile_dir:
        Directory containing one or more national park polygon shapefiles
        in WGS84 (EPSG:4326).
    """

    _ENCODINGS: tuple[str, str] = ("utf-8", "big5")
    _PARK_NAME_FIELDS: tuple[str, str, str, str] = ("PARKNAME", "NAME", "name", "Name")

    def __init__(self, shapefile_dir: Path) -> None:
        self._dir: Path = Path(shapefile_dir)
        self._parks: gpd.GeoDataFrame | None = None
        self._park_name_field: str | None = None

        self._load_shapefiles()

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def _load_shapefiles(self) -> None:
        """Load all ``*.shp`` files and merge into one queryable GeoDataFrame."""
        if not self._dir.exists():
            LOGGER.warning("National park shapefile directory not found: %s", self._dir)
            return

        shapefiles = sorted(self._dir.glob("*.shp"))
        if not shapefiles:
            LOGGER.warning("No national park shapefiles found in directory: %s", self._dir)
            return

        loaded_frames: list[gpd.GeoDataFrame] = []
        for shp_path in shapefiles:
            gdf = self._safe_load(shp_path)
            if gdf is not None:
                loaded_frames.append(gdf)

        if not loaded_frames:
            LOGGER.warning("Failed to load all national park shapefiles under: %s", self._dir)
            return

        features: list[dict[str, Any]] = []
        for frame in loaded_frames:
            features.extend(list(frame.iterfeatures()))

        merged_crs = loaded_frames[0].crs
        self._parks = gpd.GeoDataFrame.from_features(features, crs=merged_crs)

        # Reproject from TWD97 TM2 → WGS84 if needed
        if merged_crs is not None and not merged_crs.equals("EPSG:4326"):
            LOGGER.info(
                "Reprojecting national park data from %s to EPSG:4326",
                merged_crs,
            )
            self._parks = cast(gpd.GeoDataFrame, self._parks.to_crs("EPSG:4326"))

        _ = self._parks.sindex

        self._park_name_field = self._resolve_park_name_field(self._parks)
        if self._park_name_field is None:
            LOGGER.warning(
                "No park name field found. Tried fields: %s",
                ", ".join(self._PARK_NAME_FIELDS),
            )

        LOGGER.info(
            "Loaded national park boundaries: %d shapefiles, %d records, CRS=%s",
            len(loaded_frames),
            len(self._parks),
            self._parks.crs,
        )

    def _safe_load(self, path: Path) -> gpd.GeoDataFrame | None:
        """Load one shapefile with UTF-8 → Big5 fallback, returning *None* on failure."""
        for encoding in self._ENCODINGS:
            try:
                gdf = cast(gpd.GeoDataFrame, gpd.read_file(path, encoding=encoding))
                _ = gdf.sindex
                LOGGER.info(
                    "Loaded %s with encoding=%s: %d records, CRS=%s",
                    path.name,
                    encoding,
                    len(gdf),
                    gdf.crs,
                )
                return gdf
            except Exception:
                LOGGER.debug(
                    "Failed loading %s with encoding=%s",
                    path,
                    encoding,
                    exc_info=True,
                )

        LOGGER.warning("Failed to load shapefile %s with UTF-8/Big5", path, exc_info=True)
        return None

    @classmethod
    def _resolve_park_name_field(cls, gdf: gpd.GeoDataFrame) -> str | None:
        """Pick the first available park-name field from known candidates."""
        for field in cls._PARK_NAME_FIELDS:
            if field in gdf.columns:
                return field
        return None

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def query(self, lon: float, lat: float) -> NationalParkResult | None:
        """Return national park match for the given WGS84 coordinate.

        Returns ``None`` when the point falls outside all park polygons, or
        when no shapefile data is available.
        """
        if self._parks is None:
            return None

        try:
            pt = Point(lon, lat)
        except Exception:
            LOGGER.error("Failed to construct point for lon=%s, lat=%s", lon, lat, exc_info=True)
            return None

        candidates_idx = cast(list[int], list(self._parks.sindex.query(pt, predicate="intersects")))
        if not candidates_idx:
            LOGGER.debug("query(%.6f, %.6f): outside all national parks", lon, lat)
            return None

        for idx in candidates_idx:
            row = cast(dict[str, Any], self._parks.iloc[idx].to_dict())
            geometry = cast(BaseGeometry | None, row.get("geometry"))
            if geometry is None:
                continue

            if geometry.contains(pt) or geometry.touches(pt):
                park_name = self._extract_park_name(row)
                LOGGER.debug("query(%.6f, %.6f): within %s", lon, lat, park_name)
                return NationalParkResult(park_name=park_name, is_within=True)

        LOGGER.debug("query(%.6f, %.6f): no exact polygon hit", lon, lat)
        return None

    def _extract_park_name(self, row: dict[str, Any]) -> str:
        """Extract a park name from one row using the resolved name field."""
        if self._park_name_field is not None:
            name = str(row.get(self._park_name_field, "") or "")
            if name and name != "nan":
                return name
        return "(未命名國家公園)"

    # ------------------------------------------------------------------
    # Display helpers
    # ------------------------------------------------------------------

    def to_display_text(self, result: NationalParkResult | None) -> str:
        """Convert a query result to a human-readable text snippet."""
        if result is None:
            return "✅ 不在國家公園範圍內"
        return f"🏞️ 位於國家公園範圍：{result.park_name}"
