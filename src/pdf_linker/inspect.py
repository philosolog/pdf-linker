from __future__ import annotations

import statistics
from pathlib import Path

import fitz

from pdf_linker.models import InspectionReport, PageEvidence


ROMAN_CHARS = set("ivxlcdm")


def _normalize_label(text: str) -> str:
    return " ".join(text.strip().split()).lower()


def _extract_numeric_tokens(words: list[tuple], page_height: float, *, top_band: bool) -> list[str]:
    labels: list[str] = []
    for word in words:
        x0, y0, x1, y1, value = word[:5]
        _ = (x0, x1)
        token = _normalize_label(str(value))
        if top_band and y1 > page_height * 0.12:
            continue
        if not top_band and y0 < page_height * 0.88:
            continue
        compact = token.replace(" ", "")
        if compact.isdigit() or (compact and all(char in ROMAN_CHARS for char in compact)):
            labels.append(compact)
    return labels


def _extract_heading_candidates(page: fitz.Page) -> tuple[list[str], list[list[float]]]:
    candidates: list[tuple[float, str, list[float]]] = []
    height = page.rect.height
    for block in page.get_text("blocks"):
        if len(block) < 5:
            continue
        x0, y0, x1, y1, text = block[:5]
        bbox = [x0, y0, x1, y1]
        if bbox[1] > height * 0.7:
            continue
        normalized_text = " ".join(str(text).split())
        if not normalized_text or len(normalized_text) > 180 or not any(char.isalpha() for char in normalized_text):
            continue
        average_size = max(0.0, bbox[3] - bbox[1])
        alpha_chars = [char for char in normalized_text if char.isalpha()]
        uppercase_ratio = (
            sum(1 for char in alpha_chars if char.isupper()) / len(alpha_chars)
            if alpha_chars
            else 0.0
        )
        if average_size >= 11.5 or uppercase_ratio >= 0.7 or len(normalized_text) <= 90:
            candidates.append((average_size + (2.0 if uppercase_ratio >= 0.7 else 0.0), normalized_text, bbox))
    candidates.sort(key=lambda item: (-item[0], item[2][1]))
    seen: set[str] = set()
    headings: list[str] = []
    boxes: list[list[float]] = []
    for _, text, bbox in candidates:
        normalized = _normalize_label(text)
        if normalized in seen:
            continue
        seen.add(normalized)
        headings.append(text)
        boxes.append(bbox)
        if len(headings) >= 12:
            break
    if headings:
        return headings, boxes
    fallback_lines = [line.strip() for line in page.get_text("text").splitlines() if line.strip()]
    fallback = fallback_lines[:3]
    return fallback, [[0.0, 72.0, page.rect.width, 100.0] for _ in fallback]


def inspect_pdf(pdf_path: str | Path) -> InspectionReport:
    path = Path(pdf_path)
    with fitz.open(path) as document:
        page_labels = [document[i].get_label() or str(i + 1) for i in range(document.page_count)]
        page_evidence: list[PageEvidence] = []
        word_counts: list[int] = []
        extractable_pages = 0
        image_heavy_pages = 0

        for page_index in range(document.page_count):
            page = document[page_index]
            text = page.get_text("text")
            words = page.get_text("words")
            word_count = len(words)
            extractable = word_count > 20
            extractable_pages += int(extractable)
            word_counts.append(word_count)

            # Keep scanned detection lightweight on large born-digital books.
            image_count = len(page.get_images(full=True))
            image_ratio = 1.0 if image_count >= 4 and word_count < 20 else 0.0
            image_heavy_pages += int(image_ratio >= 0.5)

            heading_candidates, heading_boxes = _extract_heading_candidates(page)
            page_evidence.append(
                PageEvidence(
                    page_index=page_index,
                    page_label=_normalize_label(page_labels[page_index]),
                    word_count=word_count,
                    text_extractable=extractable,
                    header_labels=_extract_numeric_tokens(words, page.rect.height, top_band=True),
                    footer_labels=_extract_numeric_tokens(words, page.rect.height, top_band=False),
                    heading_candidates=heading_candidates,
                    heading_boxes=heading_boxes,
                    sample_text=" ".join(text.splitlines()[:4]).strip(),
                    has_large_image=image_ratio >= 0.5,
                    image_area_ratio=round(image_ratio, 4),
                )
            )

        average_words = statistics.fmean(word_counts) if word_counts else 0.0
        text_ratio = extractable_pages / max(document.page_count, 1)
        image_ratio = image_heavy_pages / max(document.page_count, 1)
        born_digital_confidence = round(max(0.0, min(1.0, text_ratio * 0.85 + (1.0 - image_ratio) * 0.15)), 4)
        scanned_confidence = round(max(0.0, min(1.0, image_ratio * 0.6 + (1.0 - text_ratio) * 0.4)), 4)
        warnings: list[str] = []
        if scanned_confidence >= 0.6:
            warnings.append("Document appears partially or fully scanned; OCR may improve extraction.")
        page_label_mismatch_count = sum(
            1
            for index, label in enumerate(page_labels, start=1)
            if _normalize_label(label) not in {str(index), ""}
        )
        existing_outline_count = len(document.get_toc(simple=False))
        if existing_outline_count:
            warnings.append("Input PDF already contains outlines; output outline will be replaced.")

    return InspectionReport(
        input_path=str(path),
        page_count=len(page_evidence),
        existing_outline_count=existing_outline_count,
        existing_page_labels=page_labels,
        page_label_mismatch_count=page_label_mismatch_count,
        sampled_pages=len(page_evidence),
        extractable_pages=extractable_pages,
        average_words_per_page=round(average_words, 2),
        born_digital_confidence=born_digital_confidence,
        scanned_confidence=scanned_confidence,
        is_scanned=scanned_confidence > born_digital_confidence,
        warnings=warnings,
        page_evidence=page_evidence,
    )
