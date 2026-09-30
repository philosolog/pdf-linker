from __future__ import annotations

import re
from pathlib import Path

import fitz

from pdf_linker.models import TocDetection


PAGE_END_RE = re.compile(r"(?:\b\d+\b|\b[ivxlcdm]+\b)\s*$", re.IGNORECASE)
NUMBERING_RE = re.compile(r"^\s*(?:chapter|part|appendix|\d+(?:\.\d+){0,3})\b", re.IGNORECASE)
CONTENTS_HEADING_RE = re.compile(r"^(?:table\s+of\s+)?contents$", re.IGNORECASE)


def detect_toc_pages(pdf_path: str | Path, *, front_window: int = 80) -> list[TocDetection]:
    detections: list[TocDetection] = []
    with fitz.open(str(pdf_path)) as document:
        limit = min(document.page_count, front_window)
        for page_index in range(limit):
            page = document[page_index]
            text = page.get_text("text")
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            has_contents_heading = any(CONTENTS_HEADING_RE.fullmatch(line) for line in lines)

            trailing_page_lines = sum(1 for line in lines if PAGE_END_RE.search(line))
            dot_leader_lines = sum(1 for line in lines if "..." in line or ". ." in line)
            numbered_lines = sum(1 for line in lines if NUMBERING_RE.search(line))

            score = 0.0
            reasons: list[str] = []
            if has_contents_heading:
                score += 7.0
                reasons.append("contains TOC heading")
            if trailing_page_lines >= 6:
                score += min(6.0, trailing_page_lines * 0.4)
                reasons.append(f"{trailing_page_lines} lines end with page labels")
            if dot_leader_lines >= 3:
                score += min(4.5, dot_leader_lines * 0.45)
                reasons.append(f"{dot_leader_lines} dot-leader lines")
            if numbered_lines >= 4:
                score += min(3.0, numbered_lines * 0.25)
                reasons.append(f"{numbered_lines} numbered heading lines")
            if 10 <= len(lines) <= 80:
                score += 0.75
                reasons.append("line density resembles a TOC")

            detections.append(
                TocDetection(
                    page_index=page_index,
                    score=round(score, 3),
                    reasons=reasons,
                    line_count=len(lines),
                )
            )
    return detections


def choose_toc_pages(detections: list[TocDetection]) -> list[int]:
    if not detections:
        return []
    anchors = [
        detection
        for detection in detections
        if "contains TOC heading" in detection.reasons
    ]
    if not anchors:
        return []
    anchor = max(anchors, key=lambda item: item.score)
    cluster = [anchor.page_index]
    cursor = anchor.page_index - 1
    while cursor >= 0 and detections[cursor].score >= 2.0:
        cluster.append(cursor)
        cursor -= 1
    cursor = anchor.page_index + 1
    while cursor < len(detections) and detections[cursor].score >= 2.0:
        cluster.append(cursor)
        cursor += 1
    return sorted(set(cluster))
