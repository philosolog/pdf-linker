from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

import fitz
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from pdf_linker.cli import run_pipeline


def _build_fixture(path: Path) -> None:
    width, height = letter
    doc = canvas.Canvas(str(path), pagesize=letter)

    doc.setFont("Helvetica-Bold", 22)
    doc.drawString(72, height - 96, "Synthetic Probability Notes")
    doc.showPage()

    doc.setFont("Helvetica-Bold", 20)
    doc.drawString(72, height - 96, "Contents")
    doc.setFont("Helvetica", 12)
    doc.drawString(72, height - 132, "Chapter 1 Probability .................... 3")
    doc.drawString(96, height - 150, "1.1 Sample Spaces ....................... 4")
    doc.drawString(72, height - 168, "Chapter 2 Random Variables .............. 5")
    doc.showPage()

    doc.setFont("Helvetica-Bold", 18)
    doc.drawString(72, height - 96, "Chapter 1 Probability")
    doc.setFont("Helvetica", 11)
    doc.drawString(72, 48, "1")
    doc.showPage()

    doc.setFont("Helvetica-Bold", 16)
    doc.drawString(72, height - 96, "1.1 Sample Spaces")
    doc.setFont("Helvetica", 11)
    doc.drawString(72, 48, "2")
    doc.showPage()

    doc.setFont("Helvetica-Bold", 18)
    doc.drawString(72, height - 96, "Chapter 2 Random Variables")
    doc.setFont("Helvetica", 11)
    doc.drawString(72, 48, "3")
    doc.showPage()

    doc.save()


def test_pipeline_links_synthetic_pdf(tmp_path: Path):
    input_pdf = tmp_path / "fixture.pdf"
    output_pdf = tmp_path / "fixture.linked.pdf"
    report_json = tmp_path / "fixture.report.json"
    _build_fixture(input_pdf)

    args = Namespace(
        input=str(input_pdf),
        output=str(output_pdf),
        report=str(report_json),
        toc_pages=[2],
        auto_detect_toc=False,
        artifacts_dir=str(tmp_path / "artifacts"),
        verbose=False,
    )
    report = run_pipeline(args)

    assert output_pdf.exists()
    assert report_json.exists()
    payload = json.loads(report_json.read_text())
    assert payload["toc_pages"] == [1]
    assert any(item["status"] == "resolved" for item in payload["destinations"])

    with fitz.open(output_pdf) as document:
        toc = document.get_toc()
        assert len(toc) >= 2
        links = document[1].get_links()
        assert links


def test_pipeline_preserves_existing_outline_when_pdf_has_no_toc_page(tmp_path: Path):
    input_pdf = tmp_path / "outlined-paper.pdf"
    output_pdf = tmp_path / "outlined-paper.linked.pdf"
    report_json = tmp_path / "outlined-paper.report.json"
    document = fitz.open()
    document.new_page().insert_text((72, 72), "Paper title", fontsize=18)
    document.new_page().insert_text((72, 72), "1 Introduction", fontsize=15)
    document.set_toc([[1, "Paper title", 1], [2, "Introduction", 2]])
    document.save(input_pdf)
    document.close()

    report = run_pipeline(
        Namespace(
            input=str(input_pdf),
            output=str(output_pdf),
            report=str(report_json),
            toc_pages=None,
            auto_detect_toc=True,
            artifacts_dir=str(tmp_path / "outlined-artifacts"),
            verbose=False,
        )
    )

    assert report.toc_pages == []
    assert len(report.entries) == 1
    with fitz.open(output_pdf) as linked:
        assert linked.get_toc() == [[1, "Introduction", 2]]


def test_pipeline_builds_outline_from_paper_headings(tmp_path: Path):
    input_pdf = tmp_path / "paper.pdf"
    output_pdf = tmp_path / "paper.linked.pdf"
    report_json = tmp_path / "paper.report.json"
    document = fitz.open()
    page = document.new_page(width=400, height=400)
    page.insert_text((72, 50), "Paper title", fontsize=18)
    page.insert_text((72, 90), "1 Introduction", fontsize=16)
    page.insert_text((72, 130), "Body text " * 8, fontsize=10)
    page = document.new_page(width=400, height=400)
    page.insert_text((72, 72), "1.1 Prior work", fontsize=13)
    page.insert_text((72, 110), "More body text " * 8, fontsize=10)
    page = document.new_page(width=400, height=400)
    page.insert_text((72, 72), "2 Results", fontsize=16)
    page.insert_text((72, 110), "Final body text " * 8, fontsize=10)
    document.save(input_pdf)
    document.close()

    report = run_pipeline(
        Namespace(
            input=str(input_pdf),
            output=str(output_pdf),
            report=str(report_json),
            toc_pages=None,
            auto_detect_toc=True,
            artifacts_dir=str(tmp_path / "paper-artifacts"),
            verbose=False,
        )
    )

    assert [entry.title for entry in report.entries] == ["1 Introduction", "1.1 Prior work", "2 Results"]
    with fitz.open(output_pdf) as linked:
        assert linked.get_toc() == [
            [1, "1 Introduction", 1],
            [2, "1.1 Prior work", 2],
            [1, "2 Results", 3],
        ]
        assert sum(len(page.get_links()) for page in linked) == 0
