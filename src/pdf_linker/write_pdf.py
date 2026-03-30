from __future__ import annotations

from pathlib import Path

import fitz

from pdf_linker.models import DestinationResult, TocEntry


def write_links_and_bookmarks(
    input_path: str | Path,
    output_path: str | Path,
    entries: list[TocEntry],
    destinations: list[DestinationResult],
) -> tuple[int, int]:
    destination_by_entry = {item.entry_id: item for item in destinations}
    written_links = 0
    outline_rows: list[list[int | str]] = []

    outline_level = 0
    with fitz.open(str(input_path)) as document:
        for entry in entries:
            destination = destination_by_entry.get(entry.entry_id)
            if destination is None or destination.status != "resolved" or destination.selected_page_index is None:
                continue
            toc_page = document[entry.toc_page_index]
            rect = fitz.Rect(*entry.bbox)
            destination_point = fitz.Point(0, destination.destination_y or 72)
            toc_page.insert_link(
                {
                    "kind": fitz.LINK_GOTO,
                    "from": rect,
                    "page": destination.selected_page_index,
                    "to": destination_point,
                }
            )
            written_links += 1
            normalized_level = entry.level
            if not outline_rows:
                normalized_level = 1
            elif normalized_level > outline_level + 1:
                normalized_level = outline_level + 1
            elif normalized_level < 1:
                normalized_level = 1
            outline_level = normalized_level
            outline_rows.append([normalized_level, entry.title, destination.selected_page_index + 1])

        if outline_rows:
            document.set_toc(outline_rows)
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        document.save(str(output), garbage=4, deflate=True)
    return written_links, len(outline_rows)
