"""Sprint M OCR adapter contract tests — no real OCR provider."""

from __future__ import annotations

from weaver.services.ocr_contract import FakeOcrAdapter, OcrImageRef, OcrResult


def test_fake_ocr_adapter_returns_draft_artifact_only() -> None:
    adapter = FakeOcrAdapter(text="extracted text")
    image_ref = OcrImageRef(project_name="demo", volume_id=1, manifest_id="img-1")

    result = adapter.extract_text(image_ref)

    assert isinstance(result, OcrResult)
    assert result.status == "draft"
    assert result.extracted_text == "extracted text"
    assert result.provenance.no_auto_apply is True
    assert result.provenance.no_image_mutation is True
    assert result.cost.estimated_cost == 0.0
    assert adapter.calls == [image_ref]


def test_ocr_contract_uses_safe_image_reference_not_file_path() -> None:
    image_ref = OcrImageRef(project_name="demo", volume_id=7, manifest_id="cover-image")

    assert image_ref.project_name == "demo"
    assert image_ref.volume_id == 7
    assert image_ref.manifest_id == "cover-image"
    assert not hasattr(image_ref, "path")
    assert not hasattr(image_ref, "bytes")
