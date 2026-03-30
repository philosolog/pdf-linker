from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


def dataclass_to_dict(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, list):
        return [dataclass_to_dict(item) for item in value]
    if isinstance(value, dict):
        return {key: dataclass_to_dict(item) for key, item in value.items()}
    return value


@dataclass(slots=True)
class TocLine:
    text: str
    bbox: list[float]
    indent: float
    toc_page_index: int
    font_size: float | None = None
    source_page_number: int | None = None


@dataclass(slots=True)
class TocDetection:
    page_index: int
    score: float
    reasons: list[str] = field(default_factory=list)
    line_count: int = 0


@dataclass(slots=True)
class TocEntry:
    entry_id: str
    title: str
    level: int
    printed_page_label: str
    printed_page_number: int | None
    page_number_style: str
    toc_page_index: int
    bbox: list[float]
    source_lines: list[str]
    numbering: str | None = None
    indent: float = 0.0
    font_size: float | None = None
    parse_confidence: float = 0.0


@dataclass(slots=True)
class PageEvidence:
    page_index: int
    page_label: str
    word_count: int
    text_extractable: bool
    header_labels: list[str] = field(default_factory=list)
    footer_labels: list[str] = field(default_factory=list)
    heading_candidates: list[str] = field(default_factory=list)
    heading_boxes: list[list[float]] = field(default_factory=list)
    sample_text: str = ""
    has_large_image: bool = False
    image_area_ratio: float = 0.0


@dataclass(slots=True)
class InspectionReport:
    input_path: str
    page_count: int
    existing_outline_count: int
    existing_page_labels: list[str]
    page_label_mismatch_count: int
    sampled_pages: int
    extractable_pages: int
    average_words_per_page: float
    born_digital_confidence: float
    scanned_confidence: float
    is_scanned: bool
    warnings: list[str] = field(default_factory=list)
    page_evidence: list[PageEvidence] = field(default_factory=list)


@dataclass(slots=True)
class MappingCandidate:
    page_index: int
    mapping_score: float
    evidence: list[str] = field(default_factory=list)
    matched_label: str | None = None
    offset: int | None = None
    heading_score: float = 0.0
    matched_heading: str | None = None
    destination_y: float | None = None


@dataclass(slots=True)
class DestinationResult:
    entry_id: str
    status: str
    selected_page_index: int | None
    confidence: float
    selected_heading: str | None = None
    destination_y: float | None = None
    warning: str | None = None
    candidates: list[MappingCandidate] = field(default_factory=list)


@dataclass(slots=True)
class PipelineReport:
    input_path: str
    output_path: str
    report_path: str
    toc_pages: list[int]
    inspection: InspectionReport
    toc_detections: list[TocDetection]
    entries: list[TocEntry]
    destinations: list[DestinationResult]
    warnings: list[str] = field(default_factory=list)

