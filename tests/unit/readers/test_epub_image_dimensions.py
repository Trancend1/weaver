"""Tests for the dependency-free image-dimension decoders (Sprint J5)."""

from __future__ import annotations

from weaver.readers.epub import (
    PARSER_VERSION,
    _decode_jpeg_dimensions,
    _decode_png_dimensions,
    _decode_svg_dimensions,
    _decode_webp_dimensions,
)


def test_parser_version_constant_exists() -> None:
    # Sprint J snapshot keys on this; bumping the parser MUST bump the constant.
    assert isinstance(PARSER_VERSION, int)
    assert PARSER_VERSION >= 2


def test_decode_png_reads_real_ihdr_offsets() -> None:
    # Standard PNG: 8B signature + 4B chunk length + 4B "IHDR" + width + height.
    payload = (
        b"\x89PNG\r\n\x1a\n"
        + b"\x00\x00\x00\x0d"
        + b"IHDR"
        + (320).to_bytes(4, "big")
        + (240).to_bytes(4, "big")
    )
    assert _decode_png_dimensions(payload) == (320, 240)


def test_decode_png_returns_none_for_short_payload() -> None:
    assert _decode_png_dimensions(b"") == (None, None)
    assert _decode_png_dimensions(b"not a png") == (None, None)


def test_decode_jpeg_baseline_sof0() -> None:
    # SOI + APP0 (16 bytes) + SOF0 with 800x600 + EOI.
    payload = (
        b"\xff\xd8"  # SOI
        + b"\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
        + b"\xff\xc0\x00\x11"  # SOF0 marker + length
        + b"\x08"  # precision
        + (600).to_bytes(2, "big")  # height
        + (800).to_bytes(2, "big")  # width
        + b"\x03\x01\x22\x00\x02\x11\x01\x03\x11\x01"
        + b"\xff\xd9"  # EOI
    )
    assert _decode_jpeg_dimensions(payload) == (800, 600)


def test_decode_jpeg_handles_progressive_sof2() -> None:
    payload = (
        b"\xff\xd8"
        + b"\xff\xc2\x00\x11"  # SOF2 (progressive)
        + b"\x08"
        + (1080).to_bytes(2, "big")
        + (1920).to_bytes(2, "big")
        + b"\x03\x01\x22\x00\x02\x11\x01\x03\x11\x01"
    )
    assert _decode_jpeg_dimensions(payload) == (1920, 1080)


def test_decode_jpeg_rejects_non_jpeg() -> None:
    assert _decode_jpeg_dimensions(b"random bytes") == (None, None)


def test_decode_webp_vp8_lossy() -> None:
    # 256x128 lossy WebP: VP8 chunk + 0x9D012A signature + size words.
    inner = (
        b"\x00\x00\x00"  # frame tag (3 bytes)
        + b"\x9d\x01\x2a"  # signature
        + (256).to_bytes(2, "little")
        + (128).to_bytes(2, "little")
    )
    chunk = b"VP8 " + len(inner).to_bytes(4, "little") + inner
    payload = b"RIFF" + (4 + len(chunk)).to_bytes(4, "little") + b"WEBP" + chunk
    assert _decode_webp_dimensions(payload) == (256, 128)


def test_decode_webp_vp8l_lossless() -> None:
    # 64x32 lossless WebP. Width-1 = 63, height-1 = 31, packed across 4 bytes.
    width_minus_one = 63  # 14 bits
    height_minus_one = 31  # 14 bits
    b0 = width_minus_one & 0xFF
    b1 = ((width_minus_one >> 8) & 0x3F) | ((height_minus_one & 0x03) << 6)
    b2 = (height_minus_one >> 2) & 0xFF
    b3 = (height_minus_one >> 10) & 0x0F
    inner = b"\x2f" + bytes([b0, b1, b2, b3]) + b"\x00\x00\x00\x00"
    chunk = b"VP8L" + len(inner).to_bytes(4, "little") + inner
    payload = b"RIFF" + (4 + len(chunk)).to_bytes(4, "little") + b"WEBP" + chunk
    assert _decode_webp_dimensions(payload) == (64, 32)


def test_decode_webp_vp8x_extended() -> None:
    # 4096x2048 extended WebP: width-1 / height-1 as 24-bit LE values.
    inner = (
        b"\x00"  # flags
        + b"\x00\x00\x00"  # reserved
        + (4095).to_bytes(3, "little")
        + (2047).to_bytes(3, "little")
    )
    chunk = b"VP8X" + len(inner).to_bytes(4, "little") + inner
    payload = b"RIFF" + (4 + len(chunk)).to_bytes(4, "little") + b"WEBP" + chunk
    assert _decode_webp_dimensions(payload) == (4096, 2048)


def test_decode_webp_rejects_non_webp() -> None:
    assert _decode_webp_dimensions(b"\x00" * 32) == (None, None)
    assert _decode_webp_dimensions(b"RIFF" + b"\x00\x00\x00\x10" + b"AVI ") == (None, None)


def test_decode_svg_reads_width_and_height_attributes() -> None:
    payload = b'<?xml version="1.0"?>\n<svg xmlns="..." width="120" height="80"></svg>'
    assert _decode_svg_dimensions(payload) == (120, 80)


def test_decode_svg_falls_back_to_view_box() -> None:
    payload = b'<svg xmlns="..." viewBox="0 0 500 300"><g/></svg>'
    assert _decode_svg_dimensions(payload) == (500, 300)


def test_decode_svg_handles_units_with_numeric_prefix() -> None:
    # "100px" -> 100; pure-percent values discarded (no concrete pixel size).
    payload = b'<svg width="100px" height="50pt"></svg>'
    assert _decode_svg_dimensions(payload) == (100, 50)


def test_decode_svg_ignores_percent_only_size() -> None:
    payload = b'<svg width="100%" height="50%"></svg>'
    assert _decode_svg_dimensions(payload) == (None, None)


def test_decode_svg_rejects_non_svg() -> None:
    assert _decode_svg_dimensions(b"<html></html>") == (None, None)
    assert _decode_svg_dimensions(b"") == (None, None)
