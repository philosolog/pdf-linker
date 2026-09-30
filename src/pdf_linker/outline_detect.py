from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import fitz

from pdf_linker.models import DestinationResult, TocEntry


NUMBERED_HEADING_RE = re.compile(
    r"^(?P<numbering>(?:\d+(?:\.\d+)*|[A-Z]\.\d+(?:\.\d+)*))(?:\.)?\s+(?P<title>\D.*)$"
)
SPECIAL_HEADING_RE = re.compile(
    r"^(?:appendix(?:\s+[A-Z0-9]+)?|acknowledg(?:e)?ments?|references|bibliography)$",
    re.IGNORECASE,
)
FILE_TITLE_RE = re.compile(r"\.(?:dvi|pdf|ps)$", re.IGNORECASE)


def _body_font_size(document: fitz.Document) -> float:
    counts: Counter[float] = Counter()
    for page in document:
        for block in page.get_text("dict").get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = span.get("text", "").strip()
                    if text:
                        counts[round(float(span.get("size", 0.0)), 1)] += len(text)
    return counts.most_common(1)[0][0] if counts else 0.0


def _page_rows(page: fitz.Page) -> list[dict[str, object]]:
    fragments: list[dict[str, object]] = []
    for block in page.get_text("dict").get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            spans = [span for span in line.get("spans", []) if span.get("text", "").strip()]
            if not spans:
                continue
            fragments.append(
                {
                    "text": " ".join(span.get("text", "").strip() for span in spans),
                    "bbox": [float(value) for value in line.get("bbox", spans[0].get("bbox"))],
                    "size": max(float(span.get("size", 0.0)) for span in spans),
                }
            )

    fragments.sort(key=lambda item: (round(float(item["bbox"][1]), 1), float(item["bbox"][0])))
    rows: list[dict[str, object]] = []
    for fragment in fragments:
        bbox = fragment["bbox"]
        same_baseline = rows and abs(float(rows[-1]["bbox"][1]) - float(bbox[1])) <= 2.0
        same_size = rows and abs(float(rows[-1]["size"]) - float(fragment["size"])) <= 0.6
        if same_baseline and same_size:
            row = rows[-1]
            row["text"] = f"{row['text']} {fragment['text']}"
            old_bbox = row["bbox"]
            row["bbox"] = [
                min(float(old_bbox[0]), float(bbox[0])),
                min(float(old_bbox[1]), float(bbox[1])),
                max(float(old_bbox[2]), float(bbox[2])),
                max(float(old_bbox[3]), float(bbox[3])),
            ]
        else:
            rows.append(fragment.copy())
    return rows


def _merge_wrapped_heading(rows: list[dict[str, object]], index: int) -> tuple[str, list[float]]:
    row = rows[index]
    text = str(row["text"])
    bbox = list(row["bbox"])
    cursor = index + 1
    while cursor < len(rows):
        candidate = rows[cursor]
        candidate_bbox = candidate["bbox"]
        vertical_gap = float(candidate_bbox[1]) - float(bbox[3])
        if abs(float(candidate["size"]) - float(row["size"])) > 0.6:
            break
        if vertical_gap < -1.0 or vertical_gap > float(row["size"]) * 0.8:
            break
        if NUMBERED_HEADING_RE.match(str(candidate["text"])) or SPECIAL_HEADING_RE.match(str(candidate["text"])):
            break
        if text.endswith("-"):
            text = f"{text[:-1]}{str(candidate['text']).lstrip()}"
        else:
            text = f"{text} {str(candidate['text']).lstrip()}"
        bbox = [
            min(float(bbox[0]), float(candidate_bbox[0])),
            min(float(bbox[1]), float(candidate_bbox[1])),
            max(float(bbox[2]), float(candidate_bbox[2])),
            max(float(bbox[3]), float(candidate_bbox[3])),
        ]
        cursor += 1
    return re.sub(r"\s+", " ", text).strip(), bbox


def _heading_level(numbering: str | None) -> int:
    if not numbering:
        return 1
    return min(6, numbering.rstrip(".").count(".") + 1)


def _normalized_title(title: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", title.lower()).split())


def _visual_document_title(document: fitz.Document) -> tuple[str, list[float]] | None:
    rows = _page_rows(document[0])
    eligible = [
        (index, row)
        for index, row in enumerate(rows)
        if float(row["bbox"][1]) < document[0].rect.height * 0.6
        and not NUMBERED_HEADING_RE.match(str(row["text"]))
        and not SPECIAL_HEADING_RE.match(str(row["text"]))
    ]
    if not eligible:
        return None
    largest_size = max(float(row["size"]) for _, row in eligible)
    for index, row in eligible:
        if float(row["size"]) >= largest_size - 0.6:
            return _merge_wrapped_heading(rows, index)
    return None


def _document_title(document: fitz.Document) -> tuple[str, list[float]] | None:
    metadata_title = re.sub(r"\s+", " ", document.metadata.get("title", "")).strip()
    visual_title = _visual_document_title(document)
    if metadata_title and not FILE_TITLE_RE.search(metadata_title):
        bbox = visual_title[1] if visual_title else [0.0, 72.0, 0.0, 72.0]
        return metadata_title, bbox
    return visual_title


def _remove_document_title(
    document: fitz.Document,
    entries: list[TocEntry],
    destinations: list[DestinationResult],
) -> None:
    title_result = _document_title(document)
    if not title_result or not entries:
        return
    title, _bbox = title_result
    if _normalized_title(entries[0].title) != _normalized_title(title):
        return
    entries.pop(0)
    destinations.pop(0)
    for entry in entries:
        entry.level = max(1, entry.level - 1)
    for sequence, (entry, destination) in enumerate(zip(entries, destinations, strict=True), start=1):
        entry_id = f"outline-{sequence:04d}"
        entry.entry_id = entry_id
        destination.entry_id = entry_id


def extract_document_outline(pdf_path: str | Path) -> tuple[list[TocEntry], list[DestinationResult]]:
    entries: list[TocEntry] = []
    destinations: list[DestinationResult] = []
    with fitz.open(str(pdf_path)) as document:
        body_size = _body_font_size(document)
        for page_index, page in enumerate(document):
            rows = _page_rows(page)
            for index, row in enumerate(rows):
                raw_text = re.sub(r"\s+", " ", str(row["text"])).strip()
                numbered = NUMBERED_HEADING_RE.match(raw_text)
                special = SPECIAL_HEADING_RE.match(raw_text)
                if not numbered and not special:
                    continue
                if float(row["size"]) < body_size + 0.8:
                    continue
                title, bbox = _merge_wrapped_heading(rows, index)
                numbering = numbered.group("numbering") if numbered else None
                entry_id = f"outline-{len(entries) + 1:04d}"
                entries.append(
                    TocEntry(
                        entry_id=entry_id,
                        title=title,
                        level=_heading_level(numbering),
                        printed_page_label=str(page_index + 1),
                        printed_page_number=page_index + 1,
                        page_number_style="arabic",
                        toc_page_index=page_index,
                        bbox=bbox,
                        source_lines=[raw_text],
                        numbering=numbering,
                        indent=float(bbox[0]),
                        font_size=float(row["size"]),
                        parse_confidence=0.9,
                    )
                )
                destinations.append(
                    DestinationResult(
                        entry_id=entry_id,
                        status="resolved",
                        selected_page_index=page_index,
                        confidence=0.9,
                        selected_heading=title,
                        destination_y=max(0.0, float(bbox[1]) - 12.0),
                    )
                )
    return entries, destinations


def read_existing_outline(pdf_path: str | Path) -> tuple[list[TocEntry], list[DestinationResult]]:
    entries: list[TocEntry] = []
    destinations: list[DestinationResult] = []
    with fitz.open(str(pdf_path)) as document:
        for level, title, page_number, details in document.get_toc(simple=False):
            page_index = page_number - 1
            if page_index < 0 or page_index >= document.page_count:
                continue
            entry_id = f"outline-{len(entries) + 1:04d}"
            entries.append(
                TocEntry(
                    entry_id=entry_id,
                    title=title,
                    level=level,
                    printed_page_label=str(page_number),
                    printed_page_number=page_number,
                    page_number_style="arabic",
                    toc_page_index=page_index,
                    bbox=[0.0, 0.0, 0.0, 0.0],
                    source_lines=[title],
                    parse_confidence=1.0,
                )
            )
            destinations.append(
                DestinationResult(
                    entry_id=entry_id,
                    status="resolved",
                    selected_page_index=page_index,
                    confidence=1.0,
                    selected_heading=title,
                    destination_y=(
                        float(details["to"].y)
                        if details.get("to") is not None
                        else 72.0
                    ),
                )
            )
        _remove_document_title(document, entries, destinations)
    return entries, destinations
