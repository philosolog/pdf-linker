from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from pdf_linker.models import PipelineReport, dataclass_to_dict
from pdf_linker.outline_detect import extract_document_outline, read_existing_outline
from pdf_linker.text_match import map_toc_entries_by_printed_page_numbers
from pdf_linker.toc_detect import choose_toc_pages, detect_toc_pages
from pdf_linker.toc_parse import extract_toc_entries
from pdf_linker.write_pdf import write_links_and_bookmarks

LOGGER = logging.getLogger("pdf_linker")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Add clickable TOC links and bookmarks to a PDF.")
    parser.add_argument("--input", required=True, help="Input PDF path.")
    parser.add_argument("--output", required=True, help="Output PDF path.")
    parser.add_argument("--report", required=True, help="JSON report path.")
    parser.add_argument("--toc-pages", nargs="*", type=int, help="1-based PDF page numbers that contain the TOC.")
    parser.add_argument("--auto-detect-toc", action="store_true", help="Detect TOC pages automatically.")
    parser.add_argument("--artifacts-dir", help="Directory for intermediate JSON artifacts.")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging.")
    return parser.parse_args(argv)


def _json_dump(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dataclass_to_dict(payload), indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def run_pipeline(args: argparse.Namespace) -> PipelineReport:
    input_path = Path(args.input).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    report_path = Path(args.report).expanduser().resolve()
    artifacts_dir = (
        Path(args.artifacts_dir).expanduser().resolve()
        if args.artifacts_dir
        else report_path.parent / f"{report_path.stem}_artifacts"
    )
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    toc_detections = detect_toc_pages(input_path)
    _json_dump(artifacts_dir / "toc_detection.json", toc_detections)
    if args.toc_pages:
        toc_pages = [value - 1 for value in args.toc_pages]
    else:
        toc_pages = choose_toc_pages(toc_detections) if (args.auto_detect_toc or not args.toc_pages) else []
    if not toc_pages:
        inspection, _ = map_toc_entries_by_printed_page_numbers(input_path, [], [])
        entries, validated = read_existing_outline(input_path)
        warnings = [
            warning
            for warning in inspection.warnings
            if warning != "Input PDF already contains an outline."
        ]
        if entries:
            _, written_bookmarks = write_links_and_bookmarks(
                input_path,
                output_path,
                entries,
                validated,
                add_page_links=False,
            )
            warnings.append(
                f"No explicit TOC pages found; normalized existing outline with {written_bookmarks} entries."
            )
        else:
            entries, validated = extract_document_outline(input_path)
            if not entries:
                raise SystemExit("Unable to find TOC pages or document section headings.")
            _, written_bookmarks = write_links_and_bookmarks(
                input_path,
                output_path,
                entries,
                validated,
                add_page_links=False,
            )
            warnings.append(
                f"No explicit TOC pages found; created an outline from {written_bookmarks} document headings."
            )
        report = PipelineReport(
            input_path=str(input_path),
            output_path=str(output_path),
            report_path=str(report_path),
            toc_pages=[],
            inspection=inspection,
            toc_detections=toc_detections,
            entries=entries,
            destinations=validated,
            warnings=warnings,
        )
        _json_dump(artifacts_dir / "toc_entries.json", entries)
        _json_dump(artifacts_dir / "inspect.json", inspection)
        _json_dump(artifacts_dir / "destinations.json", validated)
        _json_dump(report_path, report)
        return report

    entries = extract_toc_entries(input_path, toc_pages)
    _json_dump(artifacts_dir / "toc_entries.json", entries)
    if not entries:
        raise SystemExit("No TOC entries were extracted from the chosen TOC pages.")

    inspection, validated = map_toc_entries_by_printed_page_numbers(input_path, entries, toc_pages)
    warnings = list(inspection.warnings)
    _json_dump(artifacts_dir / "inspect.json", inspection)
    _json_dump(artifacts_dir / "destinations.json", validated)

    written_links, written_bookmarks = write_links_and_bookmarks(input_path, output_path, entries, validated)
    resolved = sum(1 for item in validated if item.status == "resolved")
    ambiguous = sum(1 for item in validated if item.status == "ambiguous")
    unresolved = sum(1 for item in validated if item.status == "unresolved")
    if ambiguous:
        warnings.append(f"{ambiguous} TOC entries remained ambiguous and were not linked.")
    if unresolved:
        warnings.append(f"{unresolved} TOC entries remained unresolved.")
    if written_links != resolved:
        warnings.append("Resolved destination count did not match written links; inspect destination artifacts.")
    if written_bookmarks != resolved:
        warnings.append("Bookmark count differs from resolved entry count.")

    report = PipelineReport(
        input_path=str(input_path),
        output_path=str(output_path),
        report_path=str(report_path),
        toc_pages=toc_pages,
        inspection=inspection,
        toc_detections=toc_detections,
        entries=entries,
        destinations=validated,
        warnings=warnings,
    )
    _json_dump(report_path, report)
    return report


def _print_summary(report: PipelineReport) -> None:
    resolved = sum(1 for item in report.destinations if item.status == "resolved")
    ambiguous = sum(1 for item in report.destinations if item.status == "ambiguous")
    unresolved = sum(1 for item in report.destinations if item.status == "unresolved")
    summary = {
        "input": report.input_path,
        "output": report.output_path,
        "report": report.report_path,
        "toc_pages": [page + 1 for page in report.toc_pages],
        "entries": len(report.entries),
        "resolved": resolved,
        "ambiguous": ambiguous,
        "unresolved": unresolved,
        "is_scanned": report.inspection.is_scanned,
    }
    print(json.dumps(summary, indent=2))
    if report.warnings:
        print("Warnings:")
        for warning in report.warnings:
            print(f"- {warning}")


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )
    report = run_pipeline(args)
    _print_summary(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
