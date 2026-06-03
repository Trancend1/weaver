"""Deterministic segment identity and source hashing."""

from __future__ import annotations

import hashlib
import unicodedata


def normalize_japanese_text(source_text: str) -> str:
    """Normalize source text before hashing or translation.

    Args:
        source_text: Original text extracted from the EPUB.

    Returns:
        NFKC-normalized text with repeated whitespace collapsed.
    """

    normalized = unicodedata.normalize("NFKC", source_text)
    return " ".join(normalized.split())


def compute_segment_id(chapter_href: str, dom_path: str, paragraph_index: int) -> str:
    """Compute stable segment id from EPUB structural position.

    Args:
        chapter_href: EPUB spine href for the XHTML item.
        dom_path: Absolute XPath to the source element.
        paragraph_index: 0-indexed extracted block position within the chapter.

    Returns:
        Blake2b digest as 16 lowercase hexadecimal characters.
    """

    identity = f"{chapter_href}\x1f{dom_path}\x1f{paragraph_index}".encode()
    return hashlib.blake2b(identity, digest_size=8).hexdigest()


def compute_chapter_id(book_identifier: str | None, spine_href: str) -> str:
    """Compute stable chapter id from book identifier and spine href.

    Args:
        book_identifier: EPUB unique identifier, when present.
        spine_href: EPUB spine href for the XHTML item.

    Returns:
        Blake2b digest as 16 lowercase hexadecimal characters.
    """

    identity = f"{book_identifier or ''}\x1f{spine_href}".encode()
    return hashlib.blake2b(identity, digest_size=8).hexdigest()


def scope_id_to_volume(volume_id: int, raw_id: str) -> str:
    """Fold the owning volume id into a content-derived chapter/segment id.

    Chapter and segment ids are blake2b digests of source structure
    (:func:`compute_chapter_id` / :func:`compute_segment_id`) and carry **no**
    volume component. Two volumes built from identical source content would
    therefore yield colliding ids and the ``ON CONFLICT(id)`` upsert in
    ``sync_document_segments`` would re-parent the first volume's rows onto the
    second. Scoping the stored id by volume keeps each volume's chapters and
    segments distinct while staying deterministic and in the same 16-hex format
    (re-syncing the *same* volume reproduces the same ids — idempotent).

    Args:
        volume_id: Owning volume row id.
        raw_id: Content-derived chapter or segment id from the reader/IR.

    Returns:
        Blake2b digest as 16 lowercase hexadecimal characters, unique per volume.
    """

    identity = f"{volume_id}\x1f{raw_id}".encode()
    return hashlib.blake2b(identity, digest_size=8).hexdigest()


def compute_source_hash(normalized_source_text: str) -> str:
    """Compute source hash used for stale translation detection.

    Args:
        normalized_source_text: Source text, normalized or raw.

    Returns:
        SHA-256 digest as 64 lowercase hexadecimal characters.
    """

    normalized = normalize_japanese_text(normalized_source_text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def is_source_stale(stored_hash: str, current_source_hash: str) -> bool:
    """Return whether stored translation state no longer matches source text.

    Args:
        stored_hash: Hash stored with a previous segment or translation.
        current_source_hash: Hash computed from the current source text.

    Returns:
        True when hashes differ.
    """

    return stored_hash != current_source_hash
