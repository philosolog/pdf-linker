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
