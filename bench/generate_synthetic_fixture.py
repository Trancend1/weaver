"""Generate Weaver's large synthetic EPUB benchmark fixture."""

from __future__ import annotations

import argparse
from pathlib import Path

from ebooklib import epub

DEFAULT_OUTPUT = Path("tests/fixtures/synthetic_200_chapter.epub")
DEFAULT_CHAPTERS = 200
DEFAULT_BLOCKS_PER_CHAPTER = 50


def generate_synthetic_epub(
    output_path: Path,
    *,
    chapter_count: int = DEFAULT_CHAPTERS,
    blocks_per_chapter: int = DEFAULT_BLOCKS_PER_CHAPTER,
) -> Path:
    """Write a deterministic EPUB with many small text blocks."""

    if chapter_count < 1:
        raise ValueError("chapter_count must be >= 1")
    if blocks_per_chapter < 2:
        raise ValueError("blocks_per_chapter must be >= 2")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    book = epub.EpubBook()
    book.set_identifier("weaver-synthetic-200-chapter")
    book.set_title("Weaver Synthetic 200 Chapter Fixture")
    book.set_language("ja")
    book.add_author("Weaver Benchmark Suite")

    css = epub.EpubItem(
        uid="style",
        file_name="style/main.css",
        media_type="text/css",
        content=b"body { font-family: serif; } .lead { font-weight: bold; }\n",
    )
    book.add_item(css)

    chapters = [
        _build_chapter(index, blocks_per_chapter=blocks_per_chapter)
        for index in range(1, chapter_count + 1)
    ]
    for chapter in chapters:
        chapter.add_item(css)
        book.add_item(chapter)

    book.toc = tuple(chapters)
    book.spine = ["nav", *chapters]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    epub.write_epub(str(output_path), book)
    return output_path


def _build_chapter(index: int, *, blocks_per_chapter: int) -> epub.EpubHtml:
    title = f"\u7b2c{index:03d}\u7ae0"
    body_lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        "<!DOCTYPE html>",
        '<html xmlns="http://www.w3.org/1999/xhtml">',
        "<head>",
        f"<title>{title}</title>",
        '<link rel="stylesheet" type="text/css" href="../style/main.css" />',
        "</head>",
        "<body>",
        f"<h1>{title}</h1>",
    ]

    paragraph_count = blocks_per_chapter - 1
    for paragraph_index in range(1, paragraph_count + 1):
        body_lines.append(_paragraph(index, paragraph_index))

    body_lines.extend(["</body>", "</html>"])
    chapter = epub.EpubHtml(
        uid=f"chapter-{index:03d}",
        title=title,
        file_name=f"text/chapter-{index:03d}.xhtml",
        lang="ja",
    )
    chapter.content = "\n".join(body_lines).encode("utf-8")
    return chapter


def _paragraph(chapter_index: int, paragraph_index: int) -> str:
    character = "\u30ab\u30a4" if paragraph_index % 2 else "\u30df\u30aa"
    place = "\u6771\u90fd" if chapter_index % 2 else "\u897f\u90fd"
    role = "\u8b77\u885b" if paragraph_index % 3 else "\u9b54\u5c0e\u58eb"
    return (
        f'<p class="lead">{character}\u3055\u3093\u306f{place}\u3067'
        f"{role}\u3068\u4f1a\u8a71\u3057\u3001"
        f"\u7b2c{chapter_index:03d}\u7ae0\u306e"
        f"\u7b2c{paragraph_index:02d}\u6bb5\u843d\u3092\u6b69\u3044\u305f\u3002</p>"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--chapters", type=int, default=DEFAULT_CHAPTERS)
    parser.add_argument("--blocks-per-chapter", type=int, default=DEFAULT_BLOCKS_PER_CHAPTER)
    args = parser.parse_args()

    output_path = generate_synthetic_epub(
        args.output,
        chapter_count=args.chapters,
        blocks_per_chapter=args.blocks_per_chapter,
    )
    segment_count = args.chapters * args.blocks_per_chapter
    print(f"Wrote {output_path} ({args.chapters} chapters, {segment_count} blocks)")


if __name__ == "__main__":
    main()
