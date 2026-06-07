from pathlib import Path

import fitz

from pdf_linker.toc_detect import choose_toc_pages, detect_toc_pages


def test_detect_toc_pages_finds_later_front_matter_toc(tmp_path: Path):
    pdf_path = tmp_path / "late-toc.pdf"
    document = fitz.open()
    for index in range(49):
        page = document.new_page(width=400, height=400)
        page.insert_text((72, 72), f"Front matter {index + 1}", fontsize=12)

    page = document.new_page(width=400, height=400)
    page.insert_text((72, 72), "Table of Contents", fontsize=20)
    for row in range(8):
        page.insert_text((72, 110 + row * 18), f"{row + 1}. Section {row + 1} .......... {row + 3}", fontsize=12)

    document.save(pdf_path)
    document.close()

    detections = detect_toc_pages(pdf_path)

    assert choose_toc_pages(detections) == [49]
