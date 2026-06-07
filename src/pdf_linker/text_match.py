from __future__ import annotations

import re
from pathlib import Path

import fitz

from pdf_linker.models import DestinationResult, InspectionReport, MappingCandidate, PageEvidence, TocEntry


VISIBLE_PAGE_LABEL_RE = re.compile(r"^(?:\d+|[ivxlcdm]+)$", re.IGNORECASE)
PDF_CIRCUMFLEX_VARIANTS = {
    "â": ("ˆa", "^a", "·a"),
    "ê": ("ˆe", "^e", "·e"),
    "î": ("ˆi", "^i", "·i"),
    "ô": ("ˆo", "^o", "·o"),
    "û": ("ˆu", "^u", "·u"),
    "Â": ("ˆA", "^A", "·A"),
    "Ê": ("ˆE", "^E", "·E"),
    "Î": ("ˆI", "^I", "·I"),
    "Ô": ("ˆO", "^O", "·O"),
    "Û": ("ˆU", "^U", "·U"),
}


def _core_title(title: str) -> str:
    return re.sub(
        r"^\s*(?:chapter|part|appendix)\s+[A-Z0-9]+[.:]?\s*|^\s*(?:\d+(?:\.\d+){0,5}|[A-Z](?:\.\d+){0,5})\s*",
        "",
        title,
        flags=re.IGNORECASE,
    ).strip()


def _pdf_text_variants(text: str) -> list[str]:
    variants = [text]
    for accented, replacements in PDF_CIRCUMFLEX_VARIANTS.items():
        additions: list[str] = []
        for variant in variants:
            if accented not in variant:
                continue
            additions.extend(variant.replace(accented, replacement) for replacement in replacements)
        variants.extend(additions)
    deduplicated: list[str] = []
    for variant in variants:
        if variant not in deduplicated:
            deduplicated.append(variant)
    return deduplicated


def _heading_needles(entry: TocEntry) -> list[str]:
    needles: list[str] = []
    for text in (entry.title, _core_title(entry.title)):
        text = text.strip(" .")
        if not text:
            continue
        needles.extend(_pdf_text_variants(text))
    deduplicated: list[str] = []
    for needle in needles:
        key = needle.lower()
        if key not in {item.lower() for item in deduplicated}:
            deduplicated.append(needle)
    return deduplicated


def _visible_page_labels(page: fitz.Page) -> tuple[list[str], list[str]]:
    header_labels: list[str] = []
    footer_labels: list[str] = []
    height = page.rect.height
    content = page.get_text("dict")
    for block in content.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            spans = [span for span in line.get("spans", []) if span.get("text", "").strip()]
            if not spans:
                continue
            text = " ".join(span.get("text", "").strip() for span in spans).strip()
            if not VISIBLE_PAGE_LABEL_RE.match(text):
                continue
            bbox = line.get("bbox", spans[0].get("bbox"))
            midpoint = (float(bbox[1]) + float(bbox[3])) / 2.0
            normalized = text.lower()
            if midpoint <= height * 0.12:
                header_labels.append(normalized)
            elif midpoint >= height * 0.88:
                footer_labels.append(normalized)
    return header_labels, footer_labels


def _find_heading(page: fitz.Page, entry: TocEntry) -> tuple[float, str] | None:
    seen: set[str] = set()
    for needle in _heading_needles(entry):
        key = needle.lower()
        if not needle or key in seen:
            continue
        seen.add(key)
        rects = _body_rects(page, needle)
        if rects:
            return max(0.0, rects[0].y0 - 12.0), needle
    return None


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
    heading = _find_heading(page, entry)
    if heading:
        return heading
    return 72.0, None


def _matched_page_label(
    page_index: int,
    entry: TocEntry,
    page_labels: list[str],
    visible_labels: dict[int, tuple[list[str], list[str]]],
) -> str | None:
    target = entry.printed_page_label.strip().lower()
    header_labels, footer_labels = visible_labels.get(page_index, ([], []))
    candidates = [page_labels[page_index].strip().lower(), *header_labels, *footer_labels]
    return target if target and target in candidates else None


def _arabic_entries(entries: list[TocEntry]) -> list[TocEntry]:
    return [
        entry
        for entry in entries
        if entry.page_number_style == "arabic" and entry.printed_page_number is not None
    ]


def _score_offset(
    document: fitz.Document,
    entries: list[TocEntry],
    toc_pages: set[int],
    page_labels: list[str],
    visible_labels: dict[int, tuple[list[str], list[str]]],
    offset: int,
) -> tuple[float, int, int, int]:
    in_range = 0
    heading_matches = 0
    label_matches = 0
    after_toc = 0
    last_toc_page = max(toc_pages) if toc_pages else -1

    for entry in entries:
        assert entry.printed_page_number is not None
        page_index = entry.printed_page_number - 1 + offset
        if page_index < 0 or page_index >= document.page_count:
            continue
        in_range += 1
        if page_index > last_toc_page:
            after_toc += 1
        if _matched_page_label(page_index, entry, page_labels, visible_labels):
            label_matches += 1
        if page_index not in toc_pages and _find_heading(document[page_index], entry):
            heading_matches += 1

    score = heading_matches * 12.0 + label_matches * 6.0 + in_range * 0.1 + after_toc * 0.02
    return score, heading_matches, label_matches, in_range


def _infer_page_offset(
    document: fitz.Document,
    entries: list[TocEntry],
    toc_pages: set[int],
    page_labels: list[str],
    visible_labels: dict[int, tuple[list[str], list[str]]],
) -> tuple[int, int, int]:
    arabic_entries = _arabic_entries(entries)
    if not arabic_entries:
        return 0, 0, 0

    min_printed_page = min(entry.printed_page_number or 0 for entry in arabic_entries)
    max_printed_page = max(entry.printed_page_number or 0 for entry in arabic_entries)
    min_offset = 1 - min_printed_page
    max_offset = document.page_count - max_printed_page

    scored_offsets: list[tuple[int, int, int, float, bool, int, int]] = []
    for offset in range(min_offset, max_offset + 1):
        score, heading_matches, label_matches, in_range = _score_offset(
            document,
            arabic_entries,
            toc_pages,
            page_labels,
            visible_labels,
            offset,
        )
        support = heading_matches + label_matches
        _ = in_range
        scored_offsets.append((support, heading_matches, label_matches, score, offset == 0, -abs(offset), offset))

    if not scored_offsets:
        return 0, 0, 0
    support, heading_matches, label_matches, _score, _is_zero, _distance, offset = max(scored_offsets)
    if support == 0:
        return 0, 0, 0
    return offset, heading_matches, label_matches


def _minimal_inspection(
    path: Path,
    document: fitz.Document,
    page_labels: list[str],
    visible_labels: dict[int, tuple[list[str], list[str]]],
) -> InspectionReport:
    page_evidence = [
        PageEvidence(
            page_index=index,
            page_label=(label or "").strip().lower(),
            word_count=0,
            text_extractable=True,
            header_labels=visible_labels[index][0],
            footer_labels=visible_labels[index][1],
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
    path = Path(pdf_path)
    destinations: list[DestinationResult] = []
    with fitz.open(str(path)) as document:
        toc_page_set = set(toc_pages)
        page_labels = [(document[index].get_label() or "").strip().lower() for index in range(document.page_count)]
        visible_labels = {index: _visible_page_labels(document[index]) for index in range(document.page_count)}
        inspection = _minimal_inspection(path, document, page_labels, visible_labels)
        page_offset, offset_heading_matches, offset_label_matches = _infer_page_offset(
            document,
            entries,
            toc_page_set,
            page_labels,
            visible_labels,
        )
        if page_offset:
            inspection.warnings.append(
                f"Inferred TOC page-number offset {page_offset:+d} from "
                f"{offset_heading_matches} heading matches and {offset_label_matches} page-label matches."
            )
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

            page_index = entry.printed_page_number - 1 + page_offset
            if page_index < 0 or page_index >= document.page_count:
                destinations.append(
                    DestinationResult(
                        entry_id=entry.entry_id,
                        status="unresolved",
                        selected_page_index=None,
                        confidence=0.0,
                        warning=(
                            f"TOC page number {entry.printed_page_number} with inferred offset "
                            f"{page_offset:+d} is outside the PDF page range."
                        ),
                        candidates=[],
                    )
                )
                continue

            if page_index in toc_page_set:
                destination_y, matched_heading = 72.0, None
            else:
                destination_y, matched_heading = _destination_y(document[page_index], entry)
            matched_label = _matched_page_label(page_index, entry, page_labels, visible_labels)
            if matched_heading:
                score = 1.0
            elif matched_label:
                score = 0.98
            elif page_offset and (offset_heading_matches or offset_label_matches):
                score = 0.92
            else:
                score = 0.96
            if page_offset:
                evidence = [f"TOC printed page number mapped with PDF page offset {page_offset:+d}"]
            else:
                evidence = ["TOC printed page number maps directly to the PDF page"]
            if matched_heading:
                evidence.append(f"matched heading {matched_heading!r}")
            if matched_label:
                evidence.append(f"matched visible/page-label {matched_label!r}")
            candidate = MappingCandidate(
                page_index=page_index,
                mapping_score=score,
                evidence=evidence,
                matched_label=matched_label,
                offset=page_offset,
                heading_score=1.0 if matched_heading else 0.0,
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
