"""Build DocumentIR for readers with no native markup (TXT/HTML).

EPUB blocks carry an ``EpubMarkupContext`` for write-back; TXT/HTML have none, so
these blocks set ``markup_context=None``. Chapter and segment ids fold in the
source file name so two volumes imported into one novel never collide, even when
their text is identical.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from weaver.core.ir import BlockIR, BlockKind, ChapterIR, DocumentIR, DocumentMetadata
from weaver.core.segment import compute_chapter_id, compute_segment_id, normalize_japanese_text


@dataclass(frozen=True)
class BlockDraft:
    """A parsed block before id assignment."""

    kind: BlockKind
    text: str


@dataclass(frozen=True)
class ChapterDraft:
    """A parsed chapter before id assignment."""

    title: str | None
    blocks: list[BlockDraft] = field(default_factory=list)


def build_document(*, source_name: str, language: str, chapters: list[ChapterDraft]) -> DocumentIR:
    """Assemble a DocumentIR from parsed drafts.

    Args:
        source_name: Source file name (folded into ids for cross-volume uniqueness).
        language: Source language tag for metadata.
        chapters: Parsed chapter drafts in reading order.

    Returns:
        DocumentIR with synthesized, collision-safe ids and no markup context.
    """

    return DocumentIR(
        metadata=DocumentMetadata(
            title=source_name,
            author=None,
            language=language,
            identifier=source_name,
            publisher=None,
            description=None,
        ),
        assets=[],
        chapters=[
            _build_chapter(source_name, order, draft)
            for order, draft in enumerate(chapters)
        ],
    )


def _build_chapter(source_name: str, order: int, draft: ChapterDraft) -> ChapterIR:
    chapter_href = f"{source_name}#ch{order}"
    chapter_id = compute_chapter_id(book_identifier=source_name, spine_href=chapter_href)
    blocks = [
        _build_block(chapter_href, chapter_id, block_order, block)
        for block_order, block in enumerate(draft.blocks)
    ]
    title = draft.title or next(
        (block.source_text for block in blocks if block.kind == "heading"), None
    )
    return ChapterIR(id=chapter_id, title=title, href=chapter_href, order=order, blocks=blocks)


def _build_block(
    chapter_href: str, chapter_id: str, block_order: int, draft: BlockDraft
) -> BlockIR:
    return BlockIR(
        id=compute_segment_id(
            chapter_href=chapter_href,
            dom_path=f"/{draft.kind}[{block_order}]",
            paragraph_index=block_order,
        ),
        chapter_id=chapter_id,
        order=block_order,
        kind=draft.kind,
        source_text=draft.text,
        normalized_source_text=normalize_japanese_text(draft.text),
        markup_context=None,
    )
