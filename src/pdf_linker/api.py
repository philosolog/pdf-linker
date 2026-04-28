from __future__ import annotations

from argparse import Namespace
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from pdf_linker.cli import run_pipeline
from pdf_linker.models import PipelineReport

def link_pdf(
    pdf_path: str | Path,
    *,
    output_path: str | Path | None = None,
    report_path: str | Path | None = None,
    artifacts_dir: str | Path | None = None,
    toc_pages: list[int] | None = None,
    page_offset: int | None = None,
    auto_detect_toc: bool = True,
    auto_offset: bool = True,
    ocr: bool = False,
    verbose: bool = False,
) -> PipelineReport:
    input_path = Path(pdf_path).expanduser().resolve()
    if output_path is None:
        output = input_path.with_name(f"{input_path.stem}.linked.pdf")
    else:
        output = Path(output_path).expanduser().resolve()
    if report_path is None:
        report = input_path.with_name(f"{input_path.stem}.report.json")
    else:
        report = Path(report_path).expanduser().resolve()

    args = Namespace(
        input=str(input_path),
        output=str(output),
        report=str(report),
        toc_pages=toc_pages,
        page_offset=page_offset,
        auto_detect_toc=auto_detect_toc,
        auto_offset=auto_offset,
        ocr=ocr,
        artifacts_dir=str(Path(artifacts_dir).expanduser().resolve()) if artifacts_dir is not None else None,
        verbose=verbose,
    )
    return run_pipeline(args)


def link_pdf_folder(
    raw_dir: str | Path,
    *,
    output_dir: str | Path | None = None,
    report_dir: str | Path | None = None,
    artifacts_root: str | Path | None = None,
    glob: str = "*.pdf",
    recursive: bool = False,
    toc_pages: list[int] | None = None,
    page_offset: int | None = None,
    auto_detect_toc: bool = True,
    auto_offset: bool = True,
    ocr: bool = False,
    verbose: bool = False,
    workers: int = 1,
) -> list[PipelineReport]:
    raw_path = Path(raw_dir).expanduser().resolve()
    if not raw_path.is_dir():
        raise FileNotFoundError(f"Raw PDF directory does not exist: {raw_path}")

    output_base = Path(output_dir).expanduser().resolve() if output_dir is not None else raw_path.parent / "linked"
    report_base = Path(report_dir).expanduser().resolve() if report_dir is not None else raw_path.parent / "reports"
    artifacts_base = Path(artifacts_root).expanduser().resolve() if artifacts_root is not None else report_base / "artifacts"

    output_base.mkdir(parents=True, exist_ok=True)
    report_base.mkdir(parents=True, exist_ok=True)
    artifacts_base.mkdir(parents=True, exist_ok=True)

    iterator = raw_path.rglob(glob) if recursive else raw_path.glob(glob)
    pdf_paths = sorted(path.resolve() for path in iterator if path.is_file())

    def process(pdf_path: Path) -> PipelineReport:
        return link_pdf(
            pdf_path,
            output_path=output_base / f"{pdf_path.stem}.linked.pdf",
            report_path=report_base / f"{pdf_path.stem}.report.json",
            artifacts_dir=artifacts_base / pdf_path.stem,
            toc_pages=toc_pages,
            page_offset=page_offset,
            auto_detect_toc=auto_detect_toc,
            auto_offset=auto_offset,
            ocr=ocr,
            verbose=verbose,
        )

    if workers <= 1 or len(pdf_paths) <= 1:
        return [process(pdf_path) for pdf_path in pdf_paths]

    with ThreadPoolExecutor(max_workers=workers) as executor:
        return list(executor.map(process, pdf_paths))
