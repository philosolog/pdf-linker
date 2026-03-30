from __future__ import annotations

from pathlib import Path

import fitz

from pdf_linker import link_pdf_folder
from pdf_linker.convert import run_converter_script


def _build_input_pdf(path: Path) -> None:
    document = fitz.open()
    document.new_page(width=200, height=200)
    document.save(path)
    document.close()


def test_run_converter_script_executes_user_converter(tmp_path: Path):
    input_pdf = tmp_path / "input.pdf"
    output_pdf = tmp_path / "output.pdf"
    work_dir = tmp_path / "work"
    script_path = tmp_path / "converter.py"

    _build_input_pdf(input_pdf)
    script_path.write_text(
        "\n".join(
            [
                "from __future__ import annotations",
                "",
                "import fitz",
                "",
                "def convert(context):",
                "    context.work_dir.mkdir(parents=True, exist_ok=True)",
                "    (context.work_dir / 'ran.txt').write_text(context.input_path.name, encoding='utf-8')",
                "    with fitz.open(context.input_path) as document:",
                "        document.save(context.output_path)",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    written = run_converter_script(script_path, input_pdf, output_pdf, work_dir)

    assert written == output_pdf.resolve()
    assert output_pdf.exists()
    assert (work_dir / "ran.txt").read_text(encoding="utf-8") == "input.pdf"


def _build_toc_fixture(path: Path) -> None:
    document = fitz.open()

    toc_page = document.new_page(width=400, height=400)
    toc_page.insert_text((72, 72), "Contents", fontsize=20)
    toc_page.insert_text((72, 108), "Chapter 1 Probability .................... 1", fontsize=12)
    toc_page.insert_text((96, 128), "1.1 Sample Spaces ....................... 2", fontsize=12)
    toc_page.insert_text((72, 148), "Chapter 2 Random Variables .............. 3", fontsize=12)

    page = document.new_page(width=400, height=400)
    page.insert_text((72, 72), "Chapter 1 Probability", fontsize=18)
    page.insert_text((72, 380), "1", fontsize=11)

    page = document.new_page(width=400, height=400)
    page.insert_text((72, 72), "1.1 Sample Spaces", fontsize=16)
    page.insert_text((72, 380), "2", fontsize=11)

    page = document.new_page(width=400, height=400)
    page.insert_text((72, 72), "Chapter 2 Random Variables", fontsize=18)
    page.insert_text((72, 380), "3", fontsize=11)

    document.save(path)
    document.close()


def test_link_pdf_folder_processes_raw_directory(tmp_path: Path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    input_pdf = raw_dir / "book.pdf"
    _build_toc_fixture(input_pdf)

    reports = link_pdf_folder(raw_dir)

    assert len(reports) == 1
    assert Path(reports[0].input_path) == input_pdf.resolve()
    assert Path(reports[0].output_path) == (tmp_path / "linked" / "book.linked.pdf")
    assert Path(reports[0].report_path) == (tmp_path / "reports" / "book.report.json")
    assert (tmp_path / "linked" / "book.linked.pdf").exists()
    assert (tmp_path / "reports" / "book.report.json").exists()

