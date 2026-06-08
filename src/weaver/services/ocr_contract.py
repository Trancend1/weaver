"""OCR adapter contract (Sprint M gate only; no real OCR implementation)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class OcrImageRef:
    """Safe image reference for future OCR adapters."""

    project_name: str
    volume_id: int
    manifest_id: str


@dataclass(frozen=True)
class OcrCostMetadata:
    """Provider cost metadata for a future OCR run."""

    currency: str | None = None
    estimated_cost: float | None = None
    billable_units: int | None = None
    unit_name: str | None = None


@dataclass(frozen=True)
class OcrProvenance:
    """Audit provenance for OCR draft artifacts."""

    provider: str
    model: str
    source: str = "image_preview_reference"
    no_auto_apply: bool = True
    no_image_mutation: bool = True
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class OcrResult:
    """Future OCR output contract.

    Output is a draft artifact candidate only. It must never auto-apply to
    translations, segments, exports, or EPUB image bytes.
    """

    image_ref: OcrImageRef
    extracted_text: str
    provenance: OcrProvenance
    cost: OcrCostMetadata
    status: str
    failure_reason: str | None = None


class OcrAdapter(Protocol):
    """Protocol implemented only by explicit future OCR adapters."""

    provider: str
    model: str

    def extract_text(self, image_ref: OcrImageRef) -> OcrResult:
        """Return OCR text for a safe image reference."""
        raise NotImplementedError


class FakeOcrAdapter:
    """Deterministic test adapter. Does not read images or call providers."""

    provider = "fake-ocr"
    model = "fake-ocr-1"

    def __init__(self, text: str = "") -> None:
        self.text = text
        self.calls: list[OcrImageRef] = []

    def extract_text(self, image_ref: OcrImageRef) -> OcrResult:
        self.calls.append(image_ref)
        return OcrResult(
            image_ref=image_ref,
            extracted_text=self.text,
            provenance=OcrProvenance(provider=self.provider, model=self.model),
            cost=OcrCostMetadata(currency=None, estimated_cost=0.0, billable_units=0),
            status="draft",
        )


__all__ = [
    "FakeOcrAdapter",
    "OcrAdapter",
    "OcrCostMetadata",
    "OcrImageRef",
    "OcrProvenance",
    "OcrResult",
]
