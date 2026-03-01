from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from collections.abc import Mapping, Sequence
from typing import SupportsFloat, SupportsIndex, cast

from PIL import ExifTags, Image, ImageOps, UnidentifiedImageError

# Register HEIC/HEIF support if pillow-heif is available
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:
    pass

from app.core.logging_config import get_logger


logger = get_logger(__name__)


@dataclass(slots=True)
class ExifData:
    gps_lat: float | None = None
    gps_lon: float | None = None
    datetime_original: str | None = None
    camera_make: str | None = None
    camera_model: str | None = None
    orientation: int | None = None
    image_width: int | None = None
    image_height: int | None = None
    has_gps: bool = False


@dataclass(slots=True)
class ImageResult:
    sha256: str
    original_filename: str
    content_type: str
    file_size_bytes: int
    width: int
    height: int
    thumbnail_data: bytes
    exif: ExifData
    validation_errors: list[str]
    is_valid: bool


class ImageProcessor:
    thumbnail_size: int
    max_size_mb: int
    max_size_bytes: int
    accepted_formats: set[str]

    def __init__(
        self,
        thumbnail_size: int = 300,
        max_size_mb: int = 10,
        accepted_formats: list[str] | None = None,
    ) -> None:
        self.thumbnail_size = thumbnail_size
        self.max_size_mb = max_size_mb
        self.max_size_bytes = max_size_mb * 1024 * 1024
        defaults = ["JPEG", "JPG", "PNG", "WEBP", "HEIC", "HEIF"]
        self.accepted_formats = {fmt.upper() for fmt in (accepted_formats or defaults)}

    async def process_image(self, image_data: bytes, original_filename: str) -> ImageResult:
        logger.info(
            "[PROCESS_IMAGE] Start: filename=%s, data_size=%d bytes",
            original_filename, len(image_data),
        )

        validation_errors = await asyncio.to_thread(self.validate_image, image_data, original_filename)

        sha256 = await asyncio.to_thread(self.compute_hash, image_data)
        logger.info("[PROCESS_IMAGE] SHA256=%s", sha256[:16])

        exif = ExifData()
        try:
            exif = await asyncio.to_thread(self.extract_exif, image_data)
        except Exception:
            logger.exception("[PROCESS_IMAGE] Failed to extract EXIF metadata for %s", original_filename)

        width = 0
        height = 0
        content_type = "application/octet-stream"
        thumbnail_data = b""

        try:
            width, height, content_type = await asyncio.to_thread(self._get_image_info, image_data)
            logger.info(
                "[PROCESS_IMAGE] Image info: %dx%d, content_type=%s",
                width, height, content_type,
            )
            thumbnail_data = await asyncio.to_thread(
                self.generate_thumbnail,
                image_data,
                self.thumbnail_size,
            )
            logger.info("[PROCESS_IMAGE] Thumbnail generated: %d bytes", len(thumbnail_data))
        except Exception:
            logger.exception("[PROCESS_IMAGE] Failed to read image info or generate thumbnail for %s", original_filename)

        is_valid = len(validation_errors) == 0
        logger.info(
            "[PROCESS_IMAGE] Done: filename=%s, valid=%s, errors=%s, exif_gps=%s, exif_camera=%s %s",
            original_filename, is_valid, validation_errors or 'none',
            f"({exif.gps_lat},{exif.gps_lon})" if exif.has_gps else 'N/A',
            exif.camera_make or '?', exif.camera_model or '?',
        )

        return ImageResult(
            sha256=sha256,
            original_filename=original_filename,
            content_type=content_type,
            file_size_bytes=len(image_data),
            width=width,
            height=height,
            thumbnail_data=thumbnail_data,
            exif=exif,
            validation_errors=validation_errors,
            is_valid=is_valid,
        )

    def extract_exif(self, image_data: bytes) -> ExifData:
        with Image.open(BytesIO(image_data)) as image:
            image = self.auto_orient(image)
            raw_exif_obj = image.getexif()
            raw_exif_map = dict(cast(Mapping[int, object], raw_exif_obj))

            exif_dict: dict[str, object] = {}
            for key, value in raw_exif_map.items():
                tag_name = ExifTags.TAGS.get(key, key)
                exif_dict[str(tag_name)] = value

            gps_info = exif_dict.get("GPSInfo")
            if isinstance(gps_info, Mapping):
                gps_info_map = cast(Mapping[object, object], gps_info)
                gps_named: dict[str, object] = {}
                for key, value in gps_info_map.items():
                    gps_name_obj: object
                    if isinstance(key, int):
                        gps_name_obj = ExifTags.GPSTAGS.get(key, key)
                    else:
                        gps_name_obj = key
                    gps_named[str(gps_name_obj)] = value
                exif_dict["GPSInfo"] = gps_named

            gps = self.extract_gps_from_exif(exif_dict)

            dt_iso = None
            dt_original = exif_dict.get("DateTimeOriginal")
            if isinstance(dt_original, str):
                dt_iso = self._to_iso_datetime(dt_original)

            orientation = exif_dict.get("Orientation")
            orientation_value = int(orientation) if isinstance(orientation, int) else None

            make = self._safe_str(exif_dict.get("Make"))
            model = self._safe_str(exif_dict.get("Model"))

            logger.info(
                "[EXIF] Extracted: gps=%s, datetime=%s, camera=%s %s, orientation=%s, size=%dx%d",
                f"({gps[0]:.6f},{gps[1]:.6f})" if gps else 'N/A',
                dt_iso or 'N/A',
                make or '?', model or '?',
                orientation_value,
                image.width, image.height,
            )

            return ExifData(
                gps_lat=gps[0] if gps else None,
                gps_lon=gps[1] if gps else None,
                datetime_original=dt_iso,
                camera_make=make,
                camera_model=model,
                orientation=orientation_value,
                image_width=image.width,
                image_height=image.height,
                has_gps=gps is not None,
            )

    def extract_gps_from_exif(self, exif_dict: dict[str, object]) -> tuple[float, float] | None:
        gps_info_obj = exif_dict.get("GPSInfo")
        if not isinstance(gps_info_obj, Mapping):
            return None

        gps_info = cast(Mapping[object, object], gps_info_obj)

        lat_ref = gps_info.get("GPSLatitudeRef") or gps_info.get(1)
        lon_ref = gps_info.get("GPSLongitudeRef") or gps_info.get(3)
        lat_raw = gps_info.get("GPSLatitude") or gps_info.get(2)
        lon_raw = gps_info.get("GPSLongitude") or gps_info.get(4)

        lat = self._parse_gps_coordinate(lat_raw)
        lon = self._parse_gps_coordinate(lon_raw)
        if lat is None or lon is None:
            return None

        lat_ref_val = str(lat_ref).strip().upper() if lat_ref else "N"
        lon_ref_val = str(lon_ref).strip().upper() if lon_ref else "E"

        if lat_ref_val == "S":
            lat = -abs(lat)
        elif lat_ref_val == "N":
            lat = abs(lat)

        if lon_ref_val == "W":
            lon = -abs(lon)
        elif lon_ref_val == "E":
            lon = abs(lon)

        return lat, lon

    def generate_thumbnail(self, image_data: bytes, size: int = 300) -> bytes:
        with Image.open(BytesIO(image_data)) as image:
            image = self.auto_orient(image)
            original_mode = image.mode
            if image.mode not in ("RGB", "L"):
                image = image.convert("RGB")
            elif image.mode == "L":
                image = image.convert("RGB")

            image.thumbnail((size, size), Image.Resampling.LANCZOS)

            output = BytesIO()
            image.save(output, format="JPEG", quality=85, optimize=True)
            thumb_bytes = output.getvalue()
            logger.info(
                "[THUMBNAIL] Generated: original_mode=%s, thumb_size=%dx%d, bytes=%d",
                original_mode, image.width, image.height, len(thumb_bytes),
            )
            return thumb_bytes

    def validate_image(self, image_data: bytes, filename: str) -> list[str]:
        errors: list[str] = []

        if not image_data:
            return ["Image data is empty."]

        if len(image_data) > self.max_size_bytes:
            errors.append(
                f"File size exceeds limit of {self.max_size_mb} MB."
            )

        heic_detected = self._is_heic(image_data, filename)
        if heic_detected:
            logger.info(
                "HEIC/HEIF image detected (filename=%s, size=%d bytes)",
                filename, len(image_data),
            )
        try:
            with Image.open(BytesIO(image_data)) as image:
                detected_format = (image.format or "").upper()
                logger.info(
                    "Image opened: format=%s, size=%dx%d, filename=%s",
                    detected_format, image.width, image.height, filename,
                )
                try:
                    image.verify()
                except Exception:
                    errors.append("Image appears to be corrupted.")

            with Image.open(BytesIO(image_data)) as image:
                width, height = image.size
                detected_format = (image.format or detected_format).upper()

            if not self._is_format_accepted(detected_format, heic_detected):
                # Show clean format names in error (strip IMAGE/ prefix from MIME types)
                display_formats = sorted({f.upper().removeprefix("IMAGE/") for f in self.accepted_formats})
                accepted_text = ", ".join(display_formats)
                errors.append(
                    f"Unsupported image format '{detected_format or 'UNKNOWN'}'. Accepted formats: {accepted_text}."
                )

            if width < 100 or height < 100:
                errors.append("Image dimensions must be at least 100x100 pixels.")

        except UnidentifiedImageError:
            logger.error(
                "UnidentifiedImageError: cannot open image. filename=%s, size=%d bytes, heic_detected=%s",
                filename, len(image_data), heic_detected,
            )
            errors.append("File is not a valid image or format is unsupported.")
        except Exception:
            logger.exception("Unexpected error while validating image (filename=%s)", filename)
            errors.append("Unable to validate image due to an internal error.")

        if errors:
            logger.warning("Image validation failed for %s: %s", filename, errors)

        return errors

    def auto_orient(self, image: Image.Image) -> Image.Image:
        return ImageOps.exif_transpose(image)

    def compute_hash(self, data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def _get_image_info(self, image_data: bytes) -> tuple[int, int, str]:
        with Image.open(BytesIO(image_data)) as image:
            image = self.auto_orient(image)
            width, height = image.size
            detected_format = (image.format or "").upper()

        content_type = Image.MIME.get(detected_format)
        if not content_type and detected_format in {"HEIC", "HEIF"}:
            content_type = "image/heic"

        if not content_type and self._is_heic(image_data, ""):
            content_type = "image/heic"

        if not content_type:
            content_type = "application/octet-stream"

        return width, height, content_type

    def _is_heic(self, image_data: bytes, filename: str) -> bool:
        lower_name = filename.lower()
        if lower_name.endswith((".heic", ".heif")):
            return True

        if len(image_data) >= 12 and image_data[4:8] == b"ftyp":
            brand = image_data[8:12].lower()
            if brand in {b"heic", b"heix", b"hevc", b"hevx", b"mif1", b"msf1"}:
                return True

        return False

    def _is_format_accepted(self, detected_format: str, heic_detected: bool) -> bool:
        # accepted_formats may contain Pillow names ("JPEG") or MIME types ("IMAGE/JPEG").
        # Normalise both sides for comparison.
        normalised: set[str] = set()
        for fmt in self.accepted_formats:
            upper = fmt.upper()
            # Strip "IMAGE/" prefix if present (MIME type -> Pillow name)
            if upper.startswith("IMAGE/"):
                upper = upper[6:]  # "IMAGE/JPEG" -> "JPEG"
            normalised.add(upper)

        if detected_format in normalised:
            return True

        if detected_format == "JPEG" and "JPG" in normalised:
            return True

        if detected_format == "JPG" and "JPEG" in normalised:
            return True

        if heic_detected and ({"HEIC", "HEIF"} & normalised):
            return True

        return False

    def _parse_gps_coordinate(self, value: object) -> float | None:
        if value is None:
            return None

        if isinstance(value, (int, float)):
            return float(value)

        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                return None

        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            if len(value) == 3:
                degrees = self._to_float(value[0])
                minutes = self._to_float(value[1])
                seconds = self._to_float(value[2])
                if degrees is None or minutes is None or seconds is None:
                    return None
                return degrees + (minutes / 60.0) + (seconds / 3600.0)

            if len(value) == 2:
                first = self._to_float(value[0])
                second = self._to_float(value[1])
                if first is None or second is None or second == 0:
                    return None
                return first / second

        try:
            return float(cast(SupportsFloat | SupportsIndex, value))
        except (TypeError, ValueError):
            return None

    def _to_float(self, value: object) -> float | None:
        if isinstance(value, (int, float)):
            return float(value)

        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                return None

        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)) and len(value) == 2:
            num = self._to_float(value[0])
            den = self._to_float(value[1])
            if num is None or den is None or den == 0:
                return None
            return num / den

        try:
            return float(cast(SupportsFloat | SupportsIndex, value))
        except (TypeError, ValueError):
            return None

    def _to_iso_datetime(self, value: str) -> str | None:
        value = value.strip()
        for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y:%m:%d %H:%M:%S%z"):
            try:
                return datetime.strptime(value, fmt).isoformat()
            except ValueError:
                continue

        try:
            return datetime.fromisoformat(value).isoformat()
        except ValueError:
            logger.debug("Failed to parse EXIF DateTimeOriginal: %s", value)
            return None

    def _safe_str(self, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text if text else None
