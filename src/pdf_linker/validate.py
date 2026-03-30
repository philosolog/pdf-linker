from __future__ import annotations

import difflib
import re
from pathlib import Path

import fitz

from pdf_linker.models import DestinationResult, InspectionReport, TocEntry


TOKEN_RE = re.compile(r"[a-z0-9]+")


def _normalize(text: str) -> str:
    return " ".join(TOKEN_RE.findall(text.lower()))


def _similarity(expected: str, actual: str) -> float:
    expected_tokens = set(TOKEN_RE.findall(expected.lower()))
    actual_tokens = set(TOKEN_RE.findall(actual.lower()))
    if not expected_tokens or not actual_tokens:
        return 0.0
    overlap = len(expected_tokens & actual_tokens) / len(expected_tokens)
    ratio = difflib.SequenceMatcher(None, _normalize(expected), _normalize(actual)).ratio()
    return round((overlap * 0.6) + (ratio * 0.4), 4)


def _core_title(title: str) -> str:
    return re.sub(r"^\s*(?:chapter|part|appendix)\s+[A-Z0-9]+[.:]?\s*|^\s*(?:\d+(?:\.\d+){0,5}|[A-Z](?:\.\d+){0,5})\s*", "", title, flags=re.IGNORECASE).strip()


def validate_destinations(
    pdf_path: str | Path,
    entries: list[TocEntry],
    mapped: list[DestinationResult],
    inspection: InspectionReport,
) -> list[DestinationResult]:
    entries_by_id = {entry.entry_id: entry for entry in entries}
    resolved: list[DestinationResult] = []
    with fitz.open(str(pdf_path)) as document:
        normalized_page_text: dict[int, str] = {}
        for result in mapped:
            entry = entries_by_id[result.entry_id]
            if not result.candidates:
                resolved.append(result)
                continue

            expanded_candidates = []
            seen_pages: set[int] = set()
            for candidate in result.candidates:
                for page_index in range(max(0, candidate.page_index - 1), min(document.page_count, candidate.page_index + 2)):
                    if page_index in seen_pages:
                        continue
                    seen_pages.add(page_index)
                    evidence = inspection.page_evidence[page_index]
                    page_text = normalized_page_text.get(page_index)
                    if page_text is None:
                        page_text = _normalize(document[page_index].get_text("text"))
                        normalized_page_text[page_index] = page_text
                    full_title = _normalize(entry.title)
                    short_title = _normalize(_core_title(entry.title))
                    best_heading = None
                    best_score = 0.0
                    best_y = 72.0
                    for heading, box in zip(evidence.heading_candidates, evidence.heading_boxes):
                        score = _similarity(entry.title, heading)
                        if score > best_score:
                            best_score = score
                            best_heading = heading
                            best_y = box[1]
                    if full_title and full_title in page_text:
                        best_score = max(best_score, 0.96)
                        if best_heading is None:
                            best_heading = entry.title
                    elif short_title and short_title in page_text:
                        best_score = max(best_score, 0.88)
                        if best_heading is None:
                            best_heading = _core_title(entry.title)
                    clone = type(candidate)(
                        page_index=page_index,
                        mapping_score=candidate.mapping_score - (0.12 if page_index != candidate.page_index else 0.0),
                        evidence=list(candidate.evidence),
                        matched_label=candidate.matched_label,
                        offset=candidate.offset,
                        heading_score=best_score,
                        matched_heading=best_heading,
                        destination_y=best_y,
                    )
                    if page_index != candidate.page_index:
                        clone.evidence.append("neighbor page heading check")
                    expanded_candidates.append(clone)

            expanded_candidates.sort(
                key=lambda item: (-(item.mapping_score * 0.55 + item.heading_score * 0.45), -item.heading_score, item.page_index)
            )
            best = expanded_candidates[0]
            top_score = round(best.mapping_score * 0.55 + best.heading_score * 0.45, 4)
            runner_up_score = 0.0
            if len(expanded_candidates) > 1:
                runner_up = expanded_candidates[1]
                runner_up_score = round(runner_up.mapping_score * 0.55 + runner_up.heading_score * 0.45, 4)

            strong_signal = best.heading_score >= 0.7 and best.mapping_score >= 0.75
            if top_score >= 0.75 and (top_score - runner_up_score >= 0.05 or strong_signal):
                status = "resolved"
                warning = None
            elif top_score >= 0.48:
                status = "ambiguous"
                warning = "Multiple plausible destinations remain; skipped writing link."
            else:
                status = "unresolved"
                warning = "Heading validation was too weak to trust any destination."

            resolved.append(
                DestinationResult(
                    entry_id=result.entry_id,
                    status=status,
                    selected_page_index=best.page_index if status != "unresolved" else None,
                    confidence=top_score,
                    selected_heading=best.matched_heading,
                    destination_y=best.destination_y,
                    warning=warning,
                    candidates=expanded_candidates,
                )
            )
    return resolved
