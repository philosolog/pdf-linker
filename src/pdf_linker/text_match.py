from __future__ import annotations

import re
from pathlib import Path

import fitz

from pdf_linker.models import DestinationResult, InspectionReport, MappingCandidate, PageEvidence, TocEntry


def _core_title(title: str) -> str:
    return re.sub(
        r"^\s*(?:chapter|part|appendix)\s+[A-Z0-9]+[.:]?\s*|^\s*(?:\d+(?:\.\d+){0,5}|[A-Z](?:\.\d+){0,5})\s*",
        "",
        title,
        flags=re.IGNORECASE,
    ).strip()


def _body_rects(page: fitz.Page, needle: str) -> list[fitz.Rect]:
    height = page.rect.height
    top = height * 0.08
    bottom = height * 0.92
    return [
        rect
        for rect in page.search_for(needle)
        if top <= ((rect.y0 + rect.y1) / 2.0) <= bottom
    ]


def _destination_y(page: fitz.Page, entry: TocEntry) -> tuple[float, str | None]:
    for needle in (entry.title, _core_title(entry.title)):
        if not needle:
            continue
        rects = _body_rects(page, needle)
        if rects:
            return max(0.0, rects[0].y0 - 12.0), needle
    return 72.0, None


def _minimal_inspection(path: Path, document: fitz.Document) -> InspectionReport:
    page_labels = [document[i].get_label() or str(i + 1) for i in range(document.page_count)]
    page_evidence = [
        PageEvidence(
            page_index=index,
            page_label=(label or "").strip().lower(),
            word_count=0,
            text_extractable=True,
        )
        for index, label in enumerate(page_labels)
    ]
    existing_outline_count = len(document.get_toc(simple=False))
    warnings: list[str] = []
    if existing_outline_count:
        warnings.append("Input PDF already contains outlines; output outline will be replaced.")
    return InspectionReport(
        input_path=str(path),
        page_count=document.page_count,
        existing_outline_count=existing_outline_count,
        existing_page_labels=page_labels,
        page_label_mismatch_count=0,
        sampled_pages=0,
        extractable_pages=0,
        average_words_per_page=0.0,
        born_digital_confidence=1.0,
        scanned_confidence=0.0,
        is_scanned=False,
        warnings=warnings,
        page_evidence=page_evidence,
    )


def map_toc_entries_by_printed_page_numbers(
    pdf_path: str | Path,
    entries: list[TocEntry],
    toc_pages: list[int],
) -> tuple[InspectionReport, list[DestinationResult]]:
    _ = toc_pages
    path = Path(pdf_path)
    destinations: list[DestinationResult] = []
    with fitz.open(str(path)) as document:
        inspection = _minimal_inspection(path, document)
        for entry in entries:
            if entry.page_number_style != "arabic" or entry.printed_page_number is None:
                destinations.append(
                    DestinationResult(
                        entry_id=entry.entry_id,
                        status="unresolved",
                        selected_page_index=None,
                        confidence=0.0,
                        warning="TOC entry does not have an arabic PDF page number.",
                        candidates=[],
                    )
                )
                continue

            page_index = entry.printed_page_number - 1
            if page_index < 0 or page_index >= document.page_count:
                destinations.append(
                    DestinationResult(
                        entry_id=entry.entry_id,
                        status="unresolved",
                        selected_page_index=None,
                        confidence=0.0,
                        warning=f"TOC page number {entry.printed_page_number} is outside the PDF page range.",
                        candidates=[],
                    )
                )
                continue

            destination_y, matched_heading = _destination_y(document[page_index], entry)
            score = 1.0 if matched_heading else 0.96
            candidate = MappingCandidate(
                page_index=page_index,
                mapping_score=score,
                evidence=["TOC printed page number is the PDF page number"],
                heading_score=score,
                matched_heading=matched_heading,
                destination_y=destination_y,
            )
            destinations.append(
                DestinationResult(
                    entry_id=entry.entry_id,
                    status="resolved",
                    selected_page_index=page_index,
                    confidence=score,
                    selected_heading=matched_heading,
                    destination_y=destination_y,
                    candidates=[candidate],
                )
            )

    return inspection, destinations
