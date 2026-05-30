"""End-to-end Fake-provider translation through the fixture EPUB.

Exercises: EPUB read → segment sync → `build_context()` → `FakeProvider.translate()`
→ `parse_response()` round-trip → `record_translation()` persistence with token columns.
"""

from __future__ import annotations

from pathlib import Path

from weaver.core.segment import compute_source_hash
from weaver.providers.fake import FakeProvider
from weaver.providers.types import TranslationRequest
from weaver.readers.epub import read_epub
from weaver.services.translation import build_context
from weaver.storage.db import initialize_database, transaction
from weaver.storage.glossary import list_glossary_terms
from weaver.storage.projects import create_project
from weaver.storage.segments import sync_document_segments, update_segment_status
from weaver.storage.translations import record_translation
from weaver.storage.volumes import create_volume

FIXTURE_EPUB = Path(__file__).resolve().parents[2] / "fixtures" / "aozora_sample.epub"


def test_fake_provider_runs_end_to_end_through_fixture_epub(tmp_path) -> None:
    document = read_epub(FIXTURE_EPUB)
    db_path = tmp_path / "weaver.db"

    with initialize_database(db_path) as connection, transaction(connection):
        project_id = create_project(
            connection,
            name="aozora_sample",
            source_path=str(FIXTURE_EPUB),
            source_lang="ja",
            target_lang="en",
        )
        volume_id = create_volume(
            connection,
            project_id=project_id,
            title="Volume 1",
            source_path=str(FIXTURE_EPUB),
            source_format="epub",
            volume_order=0,
        )
        sync_document_segments(
            connection, project_id=project_id, volume_id=volume_id, document=document
        )

    provider = FakeProvider(pattern="EN: {source}")
    translations_recorded = 0

    with initialize_database(db_path) as connection, transaction(connection):
        glossary_terms = list_glossary_terms(connection, project_id=project_id)
        previous_window: list[tuple[str, str]] = []

        for chapter in document.chapters:
            for block in chapter.blocks:
                context = build_context(
                    normalized_source_text=block.normalized_source_text,
                    glossary_terms=glossary_terms,
                    previous_segments=previous_window,
                )
                request = TranslationRequest(
                    segment_id=block.id,
                    source_text=block.source_text,
                    normalized_source_text=block.normalized_source_text,
                    source_language="ja",
                    target_language="en",
                    context=context,
                    provider_model="fake-1",
                )
                response = provider.translate(request)
                assert response.translation.startswith("EN: ")

                record_translation(
                    connection,
                    segment_id=block.id,
                    text=response.translation,
                    source_hash=compute_source_hash(block.normalized_source_text),
                    provider=provider.name,
                    model="fake-1",
                    raw_response=response.raw_response,
                    input_tokens=response.input_tokens,
                    output_tokens=response.output_tokens,
                )
                update_segment_status(connection, segment_id=block.id, status="translated")
                previous_window.append((block.normalized_source_text, response.translation))
                translations_recorded += 1
            previous_window.clear()

    with initialize_database(db_path) as connection:
        translations = connection.execute(
            "SELECT segment_id, provider, model, input_tokens, output_tokens FROM translations"
        ).fetchall()
        translated_segments = connection.execute(
            "SELECT COUNT(*) FROM segments WHERE status = 'translated'"
        ).fetchone()[0]

    assert translations_recorded > 0
    assert len(translations) == translations_recorded
    assert translated_segments == translations_recorded
    assert all(row["provider"] == "fake" for row in translations)
    assert all(row["input_tokens"] is None for row in translations)
    assert all(row["output_tokens"] is None for row in translations)
