from pdf_linker.mapping import infer_dominant_offset, map_printed_pages_to_pdf_indices
from pdf_linker.models import InspectionReport, PageEvidence, TocEntry


def _inspection() -> InspectionReport:
    evidence = [
        PageEvidence(page_index=0, page_label="i", word_count=10, text_extractable=True, footer_labels=["i"], heading_candidates=["Preface"], heading_boxes=[[0, 72, 100, 90]]),
        PageEvidence(page_index=1, page_label="ii", word_count=10, text_extractable=True, footer_labels=["ii"], heading_candidates=["Contents"], heading_boxes=[[0, 72, 100, 90]]),
        PageEvidence(page_index=2, page_label="1", word_count=200, text_extractable=True, footer_labels=["1"], heading_candidates=["Chapter 1 Probability"], heading_boxes=[[0, 72, 100, 90]]),
        PageEvidence(page_index=3, page_label="2", word_count=200, text_extractable=True, footer_labels=["2"], heading_candidates=["1.1 Sample Spaces"], heading_boxes=[[0, 72, 100, 90]]),
    ]
    return InspectionReport(
        input_path="fixture.pdf",
        page_count=4,
        existing_outline_count=0,
        existing_page_labels=["i", "ii", "1", "2"],
        page_label_mismatch_count=4,
        sampled_pages=4,
        extractable_pages=4,
        average_words_per_page=105.0,
        born_digital_confidence=0.98,
        scanned_confidence=0.02,
        is_scanned=False,
        page_evidence=evidence,
    )


def _entries() -> list[TocEntry]:
    return [
        TocEntry(
            entry_id="toc-0001",
            title="Chapter 1 Probability",
            level=1,
            printed_page_label="1",
            printed_page_number=1,
            page_number_style="arabic",
            toc_page_index=1,
            bbox=[0, 0, 100, 10],
            source_lines=["Chapter 1 Probability .... 1"],
            numbering="Chapter 1",
        ),
        TocEntry(
            entry_id="toc-0002",
            title="1.1 Sample Spaces",
            level=2,
            printed_page_label="2",
            printed_page_number=2,
            page_number_style="arabic",
            toc_page_index=1,
            bbox=[0, 20, 100, 30],
            source_lines=["1.1 Sample Spaces .... 2"],
            numbering="1.1",
            indent=24,
        ),
    ]


def test_infer_dominant_offset_prefers_consistent_evidence():
    assert infer_dominant_offset(_entries(), _inspection()) == 2


def test_map_printed_pages_to_pdf_indices_uses_manual_offset():
    inspection = _inspection()
    result = map_printed_pages_to_pdf_indices(_entries(), inspection, page_offset=2)
    assert [item.selected_page_index for item in result] == [2, 3]
    assert all(item.candidates for item in result)


def test_infer_dominant_offset_can_use_heading_evidence():
    entries = [
        TocEntry(
            entry_id="toc-0001",
            title="Chapter 1 Curves",
            level=1,
            printed_page_label="1",
            printed_page_number=1,
            page_number_style="arabic",
            toc_page_index=1,
            bbox=[0, 0, 100, 10],
            source_lines=["Chapter 1 Curves .... 1"],
            numbering="Chapter 1",
        ),
        TocEntry(
            entry_id="toc-0002",
            title="2.1 Tangents",
            level=2,
            printed_page_label="3",
            printed_page_number=3,
            page_number_style="arabic",
            toc_page_index=1,
            bbox=[0, 20, 100, 30],
            source_lines=["2.1 Tangents .... 3"],
            numbering="2.1",
            indent=24,
        ),
    ]
    evidence = [
        PageEvidence(page_index=10, page_label="", word_count=200, text_extractable=True, heading_candidates=["Chapter 1 Curves"], heading_boxes=[[0, 72, 100, 90]]),
        PageEvidence(page_index=12, page_label="", word_count=200, text_extractable=True, heading_candidates=["2.1 Tangents"], heading_boxes=[[0, 72, 100, 90]]),
    ]
    inspection = InspectionReport(
        input_path="fixture.pdf",
        page_count=20,
        existing_outline_count=0,
        existing_page_labels=[""] * 20,
        page_label_mismatch_count=0,
        sampled_pages=20,
        extractable_pages=20,
        average_words_per_page=100.0,
        born_digital_confidence=0.95,
        scanned_confidence=0.05,
        is_scanned=False,
        page_evidence=evidence,
    )

    assert infer_dominant_offset(entries, inspection) == 10


def test_default_pdf_page_labels_do_not_force_zero_offset():
    entries = [
        TocEntry(
            entry_id="toc-0001",
            title="Chapter 1 Curves",
            level=1,
            printed_page_label="1",
            printed_page_number=1,
            page_number_style="arabic",
            toc_page_index=1,
            bbox=[0, 0, 100, 10],
            source_lines=["Chapter 1 Curves .... 1"],
            numbering="Chapter 1",
        ),
        TocEntry(
            entry_id="toc-0002",
            title="2.1 Tangents",
            level=2,
            printed_page_label="3",
            printed_page_number=3,
            page_number_style="arabic",
            toc_page_index=1,
            bbox=[0, 20, 100, 30],
            source_lines=["2.1 Tangents .... 3"],
            numbering="2.1",
            indent=24,
        ),
    ]
    evidence = [
        PageEvidence(page_index=0, page_label="1", word_count=100, text_extractable=True, heading_candidates=["Cover"], heading_boxes=[[0, 72, 100, 90]]),
        PageEvidence(page_index=2, page_label="3", word_count=100, text_extractable=True, heading_candidates=["Contents"], heading_boxes=[[0, 72, 100, 90]]),
        PageEvidence(page_index=10, page_label="11", word_count=200, text_extractable=True, heading_candidates=["Chapter 1 Curves"], heading_boxes=[[0, 72, 100, 90]]),
        PageEvidence(page_index=12, page_label="13", word_count=200, text_extractable=True, heading_candidates=["2.1 Tangents"], heading_boxes=[[0, 72, 100, 90]]),
    ]
    inspection = InspectionReport(
        input_path="fixture.pdf",
        page_count=20,
        existing_outline_count=0,
        existing_page_labels=[str(i + 1) for i in range(20)],
        page_label_mismatch_count=0,
        sampled_pages=20,
        extractable_pages=20,
        average_words_per_page=100.0,
        born_digital_confidence=0.95,
        scanned_confidence=0.05,
        is_scanned=False,
        page_evidence=evidence,
    )

    assert infer_dominant_offset(entries, inspection) == 10
