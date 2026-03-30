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
    doc.drawString(72, height - 132, "Chapter 1 Probability .................... 1")
    doc.drawString(96, height - 150, "1.1 Sample Spaces ....................... 2")
    doc.drawString(72, height - 168, "Chapter 2 Random Variables .............. 3")
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
        page_offset=None,
        auto_detect_toc=False,
        auto_offset=True,
        ocr=False,
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
