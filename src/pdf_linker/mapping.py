from __future__ import annotations

from collections import Counter, defaultdict
import difflib
import re

from pdf_linker.models import DestinationResult, InspectionReport, MappingCandidate, TocEntry


TOKEN_RE = re.compile(r"[a-z0-9]+")


def _has_meaningful_page_labels(inspection: InspectionReport) -> bool:
    return inspection.page_label_mismatch_count > 0


def _labels_for_page(evidence, *, include_page_label: bool) -> set[str]:
    values = {evidence.page_label} if include_page_label else set()
    values.update(evidence.header_labels)
    values.update(evidence.footer_labels)
    return {value.lower() for value in values if value}


def _offset_from_entry(entry: TocEntry, page_index: int) -> int | None:
    if entry.page_number_style != "arabic" or entry.printed_page_number is None:
        return None
    return page_index - entry.printed_page_number + 1


def _normalize(text: str) -> str:
    return " ".join(TOKEN_RE.findall(text.lower()))


def _core_title(title: str) -> str:
    return re.sub(r"^\s*(?:chapter|part|appendix)\s+[A-Z0-9]+[.:]?\s*|^\s*(?:\d+(?:\.\d+){0,5}|[A-Z](?:\.\d+){0,5})\s*", "", title, flags=re.IGNORECASE).strip()


def _similarity(expected: str, actual: str) -> float:
    expected_tokens = set(TOKEN_RE.findall(expected.lower()))
    actual_tokens = set(TOKEN_RE.findall(actual.lower()))
    if not expected_tokens or not actual_tokens:
        return 0.0
    overlap = len(expected_tokens & actual_tokens) / len(expected_tokens)
    ratio = difflib.SequenceMatcher(None, _normalize(expected), _normalize(actual)).ratio()
    return (overlap * 0.6) + (ratio * 0.4)


def infer_dominant_offset(entries: list[TocEntry], inspection: InspectionReport) -> int | None:
    include_page_label = _has_meaningful_page_labels(inspection)
    offsets: defaultdict[int, float] = defaultdict(float)
    for entry in entries:
        label = entry.printed_page_label.lower()
        if entry.page_number_style != "arabic":
            continue
        for evidence in inspection.page_evidence:
            if label in _labels_for_page(evidence, include_page_label=include_page_label):
                offset = _offset_from_entry(entry, evidence.page_index)
                if offset is not None:
                    offsets[offset] += 1.0
                    continue

            if not evidence.heading_candidates:
                continue
            best_heading_score = max(
                max(_similarity(entry.title, heading), _similarity(_core_title(entry.title), heading))
                for heading in evidence.heading_candidates
            )
            if best_heading_score >= 0.72:
                offset = _offset_from_entry(entry, evidence.page_index)
                if offset is not None:
                    offsets[offset] += round(best_heading_score, 3)
    if not offsets:
        return None
    ordered = sorted(offsets.items(), key=lambda item: (-item[1], item[0]))
    offset, score = ordered[0]
    runner_up_score = ordered[1][1] if len(ordered) > 1 else 0.0
    if score < 1.8:
        return None
    if runner_up_score and score - runner_up_score < 0.2:
        return None
    return offset


def map_printed_pages_to_pdf_indices(
    entries: list[TocEntry],
    inspection: InspectionReport,
    *,
    page_offset: int | None = None,
    auto_offset: bool = False,
) -> list[DestinationResult]:
    include_page_label = _has_meaningful_page_labels(inspection)
    page_lookup: defaultdict[str, list[int]] = defaultdict(list)
    for evidence in inspection.page_evidence:
        for label in _labels_for_page(evidence, include_page_label=include_page_label):
            page_lookup[label].append(evidence.page_index)

    inferred_offset = infer_dominant_offset(entries, inspection) if auto_offset else None
    chosen_offset = page_offset if page_offset is not None else inferred_offset

    results: list[DestinationResult] = []
    for entry in entries:
        candidates_by_page: dict[int, MappingCandidate] = {}
        label = entry.printed_page_label.lower()

        def upsert(page_index: int, score: float, reason: str, *, matched_label: str | None = None, offset: int | None = None) -> None:
            if page_index < 0 or page_index >= inspection.page_count:
                return
            current = candidates_by_page.get(page_index)
            if current is None:
                candidates_by_page[page_index] = MappingCandidate(
                    page_index=page_index,
                    mapping_score=score,
                    evidence=[reason],
                    matched_label=matched_label,
                    offset=offset,
                )
                return
            current.mapping_score = max(current.mapping_score, score)
            if reason not in current.evidence:
                current.evidence.append(reason)
            if matched_label:
                current.matched_label = matched_label
            if offset is not None:
                current.offset = offset

        for page_index in page_lookup.get(label, []):
            evidence = inspection.page_evidence[page_index]
            exact_page_label = include_page_label and label == evidence.page_label
            upsert(
                page_index,
                0.9 if exact_page_label else 0.78,
                "matched page label" if exact_page_label else "matched header/footer label",
                matched_label=label,
            )

        if chosen_offset is not None and entry.page_number_style == "arabic" and entry.printed_page_number is not None:
            page_index = entry.printed_page_number + chosen_offset - 1
            upsert(
                page_index,
                0.82 if page_offset is not None else 0.64,
                "manual page offset" if page_offset is not None else "dominant inferred offset",
                offset=chosen_offset,
            )

        ordered_candidates = sorted(
            candidates_by_page.values(),
            key=lambda item: (-item.mapping_score, item.page_index),
        )
        if not ordered_candidates:
            results.append(
                DestinationResult(
                    entry_id=entry.entry_id,
                    status="unresolved",
                    selected_page_index=None,
                    confidence=0.0,
                    warning="No destination candidates found from page labels, footers, or offsets.",
                    candidates=[],
                )
            )
            continue

        results.append(
            DestinationResult(
                entry_id=entry.entry_id,
                status="candidate",
                selected_page_index=ordered_candidates[0].page_index,
                confidence=round(ordered_candidates[0].mapping_score, 3),
                warning=None,
                candidates=ordered_candidates,
            )
        )
    return results
