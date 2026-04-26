from __future__ import annotations

import re
from itertools import count
from pathlib import Path

import fitz

from pdf_linker.models import TocEntry, TocLine


TERMINAL_PAGE_RE = re.compile(
    r"^(?P<title>.+?)\s*(?:\.{2,}\s*|\s+)(?P<label>\d+|[ivxlcdm]+)\s*$",
    re.IGNORECASE,
)
NUMBERING_RE = re.compile(
    r"^\s*(?P<numbering>(?:chapter|part|appendix)\s+[A-Z0-9]+|(?:\d+(?:\.\d+){0,5})|(?:[A-Z](?:\.\d+){0,5}))\b[.:]?\s*",
    re.IGNORECASE,
)
NUMBERING_ONLY_RE = re.compile(r"^(?:\d+(?:\.\d+){0,5}|[A-Z](?:\.\d+){0,5})$", re.IGNORECASE)
PAGE_ONLY_RE = re.compile(r"^(?:\d+|(?:[ivxlcdm]{2,}|[ivx]))$")
LEADER_ONLY_RE = re.compile(r"^(?:\.\s*){3,}$")
LEADER_WITH_PAGE_RE = re.compile(r"^(?:\.\s*){3,}(?P<label>\d+|[ivxlcdm]+)$", re.IGNORECASE)


def roman_to_int(value: str) -> int | None:
    numerals = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}
    total = 0
    previous = 0
    for char in value.lower()[::-1]:
        if char not in numerals:
            return None
        current = numerals[char]
        if current < previous:
            total -= current
        else:
            total += current
            previous = current
    return total


def _clean_title(text: str) -> str:
    text = re.sub(r"\s*\.{2,}\s*", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip(" .\t")


def _entry_key(entry: TocEntry) -> tuple[str, str]:
    title = _clean_title(entry.title).lower()
    title = re.sub(r"[^a-z0-9]+", " ", title)
    return (" ".join(title.split()), entry.printed_page_label.strip().lower())


def _entry_quality(entry: TocEntry) -> tuple[float, int, int]:
    digit_count = sum(char.isdigit() for char in entry.printed_page_label)
    alpha_count = sum(char.isalpha() for char in entry.printed_page_label)
    return (entry.parse_confidence, digit_count - alpha_count, entry.toc_page_index)


def _parse_numbering(title: str) -> str | None:
    match = NUMBERING_RE.match(title)
    return match.group("numbering") if match else None


def _is_noise_line(text: str) -> bool:
    normalized = text.strip().lower()
    return normalized in {"contents", "table of contents"} or normalized in {"i", "ii", "iii", "iv", "v", "vi", "vii", "viii"}


def _has_meaningful_title(text: str) -> bool:
    normalized = _clean_title(text)
    return bool(re.search(r"[A-Za-z]", normalized))


def _make_entry(entry_id: str, lines: list[TocLine], title: str, page_label: str, numbering: str | None = None) -> TocEntry:
    page_number, style = _page_label_to_number(page_label)
    parse_confidence = 0.68
    if len(lines) > 1:
        parse_confidence += 0.07
    if numbering:
        parse_confidence += 0.1
    if any(LEADER_ONLY_RE.match(line.text.strip()) for line in lines):
        parse_confidence += 0.05
    return TocEntry(
        entry_id=entry_id,
        title=_clean_title(title),
        level=1,
        printed_page_label=page_label.strip(),
        printed_page_number=page_number,
        page_number_style=style,
        toc_page_index=lines[-1].toc_page_index,
        bbox=_merge_bbox(lines),
        source_lines=[item.text for item in lines],
        numbering=numbering or _parse_numbering(title),
        indent=min(item.indent for item in lines),
        font_size=max(item.font_size or 0.0 for item in lines) or None,
        parse_confidence=round(min(parse_confidence, 0.98), 3),
    )


def _merge_bbox(lines: list[TocLine]) -> list[float]:
    return [
        min(line.bbox[0] for line in lines),
        min(line.bbox[1] for line in lines),
        max(line.bbox[2] for line in lines),
        max(line.bbox[3] for line in lines),
    ]


def _page_label_to_number(label: str) -> tuple[int | None, str]:
    stripped = label.strip()
    if stripped.isdigit():
        return int(stripped), "arabic"
    value = roman_to_int(stripped)
    if value is not None:
        return value, "roman"
    return None, "unknown"


def _repair_outlier_page_numbers(entries: list[TocEntry]) -> None:
    for index, entry in enumerate(entries):
        if entry.page_number_style != "arabic" or entry.printed_page_number is None:
            continue
        previous_number = next(
            (
                candidate.printed_page_number
                for candidate in reversed(entries[:index])
                if candidate.page_number_style == "arabic" and candidate.printed_page_number is not None
            ),
            None,
        )
        next_number = next(
            (
                candidate.printed_page_number
                for candidate in entries[index + 1 :]
                if candidate.page_number_style == "arabic" and candidate.printed_page_number is not None
            ),
            None,
        )
        if previous_number is None or next_number is None:
            continue
        current = entry.printed_page_number
        if previous_number <= current <= next_number:
            continue
        if current < 100 or previous_number >= next_number:
            continue

        suffix = current % 100
        hundreds = {previous_number // 100, next_number // 100}
        replacements = [hundred * 100 + suffix for hundred in hundreds]
        plausible = [value for value in replacements if previous_number <= value <= next_number]
        if len(plausible) == 1:
            repaired = plausible[0]
            entry.printed_page_number = repaired
            entry.printed_page_label = str(repaired)


def _deduplicate_entries(entries: list[TocEntry]) -> list[TocEntry]:
    deduplicated: list[TocEntry] = []
    seen: dict[tuple[str, str], int] = {}
    for entry in entries:
        key = _entry_key(entry)
        existing_index = seen.get(key)
        if existing_index is None:
            seen[key] = len(deduplicated)
            deduplicated.append(entry)
            continue
        existing = deduplicated[existing_index]
        if _entry_quality(entry) > _entry_quality(existing):
            deduplicated[existing_index] = entry
    return deduplicated


def extract_toc_lines(pdf_path: str | Path, toc_pages: list[int]) -> list[TocLine]:
    lines: list[TocLine] = []
    with fitz.open(str(pdf_path)) as document:
        for page_index in toc_pages:
            page = document[page_index]
            content = page.get_text("dict")
            page_lines: list[tuple[float, TocLine]] = []
            for block in content.get("blocks", []):
                if block.get("type") != 0:
                    continue
                for line in block.get("lines", []):
                    spans = [span for span in line.get("spans", []) if span.get("text", "").strip()]
                    if not spans:
                        continue
                    text = " ".join(span.get("text", "").strip() for span in spans).strip()
                    if not text:
                        continue
                    bbox = list(line.get("bbox", spans[0].get("bbox")))
                    average_size = sum(float(span.get("size", 0.0)) for span in spans) / max(len(spans), 1)
                    page_lines.append(
                        (
                            bbox[1],
                            TocLine(
                                text=text,
                                bbox=bbox,
                                indent=bbox[0],
                                toc_page_index=page_index,
                                font_size=round(average_size, 2),
                                source_page_number=page_index + 1,
                            ),
                        )
                    )
            page_lines.sort(key=lambda item: item[0])
            lines.extend(line for _, line in page_lines)
    return lines


def parse_toc_lines(lines: list[TocLine]) -> list[TocEntry]:
    entries: list[TocEntry] = []
    filtered_lines = [line for line in lines if not _is_noise_line(line.text)]
    sequence = count(1)
    index = 0

    while index < len(filtered_lines):
        line = filtered_lines[index]
        text = re.sub(r"\s+", " ", line.text).strip()
        if not text:
            index += 1
            continue

        next_line = filtered_lines[index + 1] if index + 1 < len(filtered_lines) else None
        next_text = re.sub(r"\s+", " ", next_line.text).strip() if next_line else ""
        next_next_line = filtered_lines[index + 2] if index + 2 < len(filtered_lines) else None
        next_next_text = re.sub(r"\s+", " ", next_next_line.text).strip() if next_next_line else ""
        leader_with_page = LEADER_WITH_PAGE_RE.match(next_text) if next_line else None
        next_next_leader = LEADER_WITH_PAGE_RE.match(next_next_text) if next_next_line else None

        if _parse_numbering(text) and leader_with_page:
            entries.append(_make_entry(f"toc-{next(sequence):04d}", [line, next_line], text, leader_with_page.group("label")))
            index += 2
            continue

        if _has_meaningful_title(text) and next_line and NUMBERING_ONLY_RE.match(next_text) and next_next_leader:
            entries.append(
                _make_entry(
                    f"toc-{next(sequence):04d}",
                    [line, next_line, next_next_line],
                    f"{next_text} {text}",
                    next_next_leader.group("label"),
                    numbering=next_text,
                )
            )
            index += 3
            continue

        if (
            _has_meaningful_title(text)
            and next_line
            and not TERMINAL_PAGE_RE.match(text)
            and not NUMBERING_ONLY_RE.match(text)
        ):
            wrapped_match = TERMINAL_PAGE_RE.match(next_text)
            if wrapped_match and _has_meaningful_title(wrapped_match.group("title")):
                entries.append(
                    _make_entry(
                        f"toc-{next(sequence):04d}",
                        [line, next_line],
                        f"{text} {wrapped_match.group('title')}",
                        wrapped_match.group("label"),
                    )
                )
                index += 2
                continue

        direct_match = TERMINAL_PAGE_RE.match(text)
        if direct_match and _has_meaningful_title(direct_match.group("title")):
            numbering = _parse_numbering(direct_match.group("title"))
            if (
                numbering is None
                and next_line
                and NUMBERING_ONLY_RE.match(next_text)
                and (not next_next_line or NUMBERING_ONLY_RE.match(next_next_text))
            ):
                entries.append(
                    _make_entry(
                        f"toc-{next(sequence):04d}",
                        [line, next_line],
                        f"{next_text} {direct_match.group('title')}",
                        direct_match.group("label"),
                        numbering=next_text,
                    )
                )
                index += 2
                continue
            entries.append(
                _make_entry(
                    f"toc-{next(sequence):04d}",
                    [line],
                    direct_match.group("title"),
                    direct_match.group("label"),
                )
            )
            index += 1
            continue

        if NUMBERING_ONLY_RE.match(text):
            title_lines: list[TocLine] = [line]
            title_parts: list[str] = [text]
            cursor = index + 1
            consumed = False
            while cursor < len(filtered_lines):
                candidate = filtered_lines[cursor]
                candidate_text = re.sub(r"\s+", " ", candidate.text).strip()
                direct_candidate = TERMINAL_PAGE_RE.match(candidate_text)
                if direct_candidate and _has_meaningful_title(direct_candidate.group("title")):
                    entries.append(
                        _make_entry(
                            f"toc-{next(sequence):04d}",
                            title_lines + [candidate],
                            f"{text} {direct_candidate.group('title')}",
                            direct_candidate.group("label"),
                            numbering=text,
                        )
                    )
                    index = cursor + 1
                    consumed = True
                    break
                leader_with_page = LEADER_WITH_PAGE_RE.match(candidate_text)
                if leader_with_page and len(title_parts) > 1:
                    entries.append(
                        _make_entry(
                            f"toc-{next(sequence):04d}",
                            title_lines + [candidate],
                            " ".join(title_parts),
                            leader_with_page.group("label"),
                            numbering=text,
                        )
                    )
                    index = cursor + 1
                    consumed = True
                    break
                if PAGE_ONLY_RE.match(candidate_text):
                    if len(title_parts) > 1:
                        entries.append(
                            _make_entry(
                                f"toc-{next(sequence):04d}",
                                title_lines + [candidate],
                                " ".join(title_parts),
                                candidate_text,
                                numbering=text,
                            )
                        )
                        index = cursor + 1
                        consumed = True
                        break
                    break
                if LEADER_ONLY_RE.match(candidate_text):
                    title_lines.append(candidate)
                    cursor += 1
                    continue
                if NUMBERING_ONLY_RE.match(candidate_text):
                    break
                title_lines.append(candidate)
                title_parts.append(candidate_text)
                cursor += 1
            else:
                index += 1
                continue
            if not consumed:
                index += 1
            continue

        if _has_meaningful_title(text) and next_line and PAGE_ONLY_RE.match(next_text):
            entries.append(_make_entry(f"toc-{next(sequence):04d}", [line, next_line], text, next_text))
            index += 2
            continue

        if _has_meaningful_title(text) and next_line and leader_with_page:
            entries.append(_make_entry(f"toc-{next(sequence):04d}", [line, next_line], text, leader_with_page.group("label")))
            index += 2
            continue

        if _has_meaningful_title(text) and next_line and LEADER_ONLY_RE.match(next_text) and next_next_line and PAGE_ONLY_RE.match(next_next_text):
            entries.append(
                _make_entry(
                    f"toc-{next(sequence):04d}",
                    [line, next_line, next_next_line],
                    text,
                    next_next_text,
                )
            )
            index += 3
            continue

        index += 1
    return entries


def infer_hierarchy(entries: list[TocEntry], *, indent_tolerance: float = 10.0) -> list[TocEntry]:
    if not entries:
        return entries
    indent_levels: list[float] = []
    for entry in sorted(entries, key=lambda item: item.indent):
        if not indent_levels or abs(entry.indent - indent_levels[-1]) > indent_tolerance:
            indent_levels.append(entry.indent)

    chapter_like = re.compile(r"^(chapter|part|appendix)\b", re.IGNORECASE)
    for entry in entries:
        number_depth = 0
        if entry.numbering:
            if chapter_like.match(entry.numbering):
                number_depth = 1
            else:
                number_depth = entry.numbering.count(".") + 1
        indent_depth = next(
            (index + 1 for index, value in enumerate(indent_levels) if abs(entry.indent - value) <= indent_tolerance),
            1,
        )
        keyword_depth = 1 if chapter_like.match(entry.title) else 0
        if re.match(r"^\d+\.\d+\.\d+", entry.title):
            keyword_depth = max(keyword_depth, 3)
        elif re.match(r"^\d+\.\d+", entry.title):
            keyword_depth = max(keyword_depth, 2)
        entry.level = max(1, min(6, number_depth or max(indent_depth, keyword_depth or 1)))
    return entries


def extract_toc_entries(pdf_path: str | Path, toc_pages: list[int]) -> list[TocEntry]:
    lines = extract_toc_lines(pdf_path, toc_pages)
    entries: list[TocEntry] = []
    for page_index in toc_pages:
        page_lines = [line for line in lines if line.toc_page_index == page_index]
        entries.extend(parse_toc_lines(page_lines))
    _repair_outlier_page_numbers(entries)
    entries = _deduplicate_entries(entries)
    for sequence, entry in enumerate(entries, start=1):
        entry.entry_id = f"toc-{sequence:04d}"
    return infer_hierarchy(entries)
