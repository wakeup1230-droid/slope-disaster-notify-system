from __future__ import annotations

import hashlib
from io import BytesIO
from typing import Callable, cast

import pytest
from PIL import Image

from app.services.image_processor import ExifData, ImageProcessor


@pytest.fixture
def processor() -> ImageProcessor:
    return ImageProcessor(thumbnail_size=150, max_size_mb=5)


@pytest.fixture
def sample_jpeg() -> bytes:
    img = Image.new("RGB", (800, 600), color=(255, 0, 0))
    buf = BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture
def small_image() -> bytes:
    img = Image.new("RGB", (50, 50), color=(0, 255, 0))
    buf = BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def test_validate_image_valid(processor: ImageProcessor, sample_jpeg: bytes) -> None:
    errors = processor.validate_image(sample_jpeg, "test.jpg")
    assert errors == []


def test_validate_image_too_small(processor: ImageProcessor, small_image: bytes) -> None:
    errors = processor.validate_image(small_image, "small.jpg")
    assert "Image dimensions must be at least 100x100 pixels." in errors


def test_validate_image_empty(processor: ImageProcessor) -> None:
    errors = processor.validate_image(b"", "empty.jpg")
    assert errors == ["Image data is empty."]


def test_validate_image_too_large(sample_jpeg: bytes) -> None:
    tiny_limit_processor = ImageProcessor(thumbnail_size=150, max_size_mb=0)
    errors = tiny_limit_processor.validate_image(sample_jpeg, "test.jpg")
    assert any("File size exceeds limit of 0 MB." in err for err in errors)


def test_compute_hash(processor: ImageProcessor, sample_jpeg: bytes) -> None:
    expected = hashlib.sha256(sample_jpeg).hexdigest()
    assert processor.compute_hash(sample_jpeg) == expected


def test_generate_thumbnail(processor: ImageProcessor, sample_jpeg: bytes) -> None:
    thumbnail_data = processor.generate_thumbnail(sample_jpeg, size=150)
    assert thumbnail_data

    with Image.open(BytesIO(thumbnail_data)) as thumb:
        assert thumb.format == "JPEG"


def test_generate_thumbnail_size(processor: ImageProcessor, sample_jpeg: bytes) -> None:
    thumbnail_data = processor.generate_thumbnail(sample_jpeg, size=120)

    with Image.open(BytesIO(thumbnail_data)) as thumb:
        assert thumb.width <= 120
        assert thumb.height <= 120


def test_extract_exif_no_gps(processor: ImageProcessor, sample_jpeg: bytes) -> None:
    exif = processor.extract_exif(sample_jpeg)
    assert isinstance(exif, ExifData)
    assert exif.has_gps is False
    assert exif.gps_lat is None
    assert exif.gps_lon is None


@pytest.mark.asyncio
async def test_process_image(processor: ImageProcessor, sample_jpeg: bytes) -> None:
    result = await processor.process_image(sample_jpeg, "test.jpg")
    assert result.is_valid is True
    assert result.width == 800
    assert result.height == 600
    assert result.content_type in {"image/jpeg", "application/octet-stream"}
    assert result.thumbnail_data


def test_parse_gps_coordinate_dms(processor: ImageProcessor) -> None:
    parse_gps = cast(Callable[[object], float | None], getattr(processor, "_parse_gps_coordinate"))
    result = parse_gps((24, 49, 48.0))
    assert result is not None
    assert abs(result - 24.83) < 0.01


def test_parse_gps_coordinate_none(processor: ImageProcessor) -> None:
    parse_gps = cast(Callable[[object], float | None], getattr(processor, "_parse_gps_coordinate"))
    assert parse_gps(None) is None


def test_to_float_rational(processor: ImageProcessor) -> None:
    to_float = cast(Callable[[object], float | None], getattr(processor, "_to_float"))
    assert to_float((3, 2)) == 1.5
