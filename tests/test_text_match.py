from pathlib import Path

import fitz

from pdf_linker.models import TocEntry
from pdf_linker.text_match import map_toc_entries_by_printed_page_numbers


def _entry(entry_id: str, title: str, label: str) -> TocEntry:
    return TocEntry(
        entry_id=entry_id,
        title=title,
        level=1,
        printed_page_label=label,
        printed_page_number=int(label),
        page_number_style="arabic",
        toc_page_index=0,
        bbox=[72, 72, 300, 90],
        source_lines=[f"{title} .... {label}"],
    )


def test_text_matcher_uses_toc_page_number_as_pdf_page_number(tmp_path: Path):
    pdf_path = tmp_path / "direct-pages.pdf"
    document = fitz.open()

    page = document.new_page()
    page.insert_text((72, 72), "Contents\nTarget Section .... 3")
    document.new_page().insert_text((72, 72), "Wrong page with Target Section in a margin")
    document.new_page().insert_text((72, 240), "Target Section")

    document.save(pdf_path)
    document.close()

    entries = [_entry("toc-0001", "Target Section", "3")]
    _, destinations = map_toc_entries_by_printed_page_numbers(pdf_path, entries, [0])

    assert destinations[0].status == "resolved"
    assert destinations[0].selected_page_index == 2
    assert destinations[0].confidence == 1.0


def test_text_matcher_resolves_page_even_if_title_search_misses(tmp_path: Path):
    pdf_path = tmp_path / "direct-pages-title-miss.pdf"
    document = fitz.open()
    document.new_page().insert_text((72, 72), "Contents\nTarget Section .... 2")
    document.new_page().insert_text((72, 240), "Different extracted text")
    document.save(pdf_path)
    document.close()

    entries = [_entry("toc-0001", "Target Section", "2")]
    _, destinations = map_toc_entries_by_printed_page_numbers(pdf_path, entries, [0])

    assert destinations[0].status == "resolved"
    assert destinations[0].selected_page_index == 1
    assert destinations[0].confidence == 0.96
    assert destinations[0].destination_y == 72.0


def test_text_matcher_infers_front_matter_page_offset(tmp_path: Path):
    pdf_path = tmp_path / "front-matter-offset.pdf"
    document = fitz.open()

    toc_page = document.new_page(width=400, height=400)
    toc_page.insert_text((72, 72), "Contents", fontsize=20)
    toc_page.insert_text((72, 108), "Chapter 1 Probability .................... 1", fontsize=12)
    toc_page.insert_text((96, 128), "1.1 Sample Spaces ....................... 2", fontsize=12)

    document.new_page(width=400, height=400).insert_text((72, 72), "Preface", fontsize=18)

    page = document.new_page(width=400, height=400)
    page.insert_text((72, 72), "Chapter 1 Probability", fontsize=18)
    page.insert_text((190, 380), "1", fontsize=11)

    page = document.new_page(width=400, height=400)
    page.insert_text((72, 72), "1.1 Sample Spaces", fontsize=16)
    page.insert_text((190, 380), "2", fontsize=11)

    document.save(pdf_path)
    document.close()

    entries = [
        _entry("toc-0001", "Chapter 1 Probability", "1"),
        _entry("toc-0002", "1.1 Sample Spaces", "2"),
    ]
    inspection, destinations = map_toc_entries_by_printed_page_numbers(pdf_path, entries, [0])

    assert [item.selected_page_index for item in destinations] == [2, 3]
    assert destinations[0].candidates[0].offset == 2
    assert inspection.warnings == [
        "Inferred TOC page-number offset +2 from 2 heading matches and 2 page-label matches."
    ]


def test_text_matcher_searches_extracted_circumflex_variants(tmp_path: Path):
    pdf_path = tmp_path / "circumflex-heading.pdf"
    document = fitz.open()
    document.new_page().insert_text((72, 72), "Contents\nItˆo Integrals .... 2")
    document.new_page().insert_text((72, 240), "Itˆo Integrals")
    document.save(pdf_path)
    document.close()

    entries = [_entry("toc-0001", "Itô Integrals", "2")]
    _, destinations = map_toc_entries_by_printed_page_numbers(pdf_path, entries, [0])

    assert destinations[0].status == "resolved"
    assert destinations[0].confidence == 1.0
    assert destinations[0].selected_heading == "It·o Integrals"
