from pdf_linker.toc_parse import infer_hierarchy, parse_toc_lines
from pdf_linker.models import TocLine


def test_parse_toc_lines_handles_dot_leaders_and_wrapped_titles():
    lines = [
        TocLine(text="Chapter 1 Probability", bbox=[72, 100, 320, 114], indent=72, toc_page_index=4, font_size=14),
        TocLine(text="Spaces ........................ 1", bbox=[72, 116, 320, 130], indent=72, toc_page_index=4, font_size=14),
        TocLine(text="1.1 Random Variables .......... 9", bbox=[96, 140, 330, 152], indent=96, toc_page_index=4, font_size=12),
    ]
    entries = parse_toc_lines(lines)
    assert [entry.title for entry in entries] == ["Chapter 1 Probability Spaces", "1.1 Random Variables"]
    assert entries[0].printed_page_label == "1"
    assert entries[0].bbox == [72, 100, 320, 130]


def test_infer_hierarchy_uses_numbering_and_indent():
    lines = [
        TocLine(text="Chapter 1 Probability ........ 1", bbox=[72, 100, 320, 114], indent=72, toc_page_index=4, font_size=14),
        TocLine(text="1.1 Sample Spaces ............ 5", bbox=[96, 118, 320, 130], indent=96, toc_page_index=4, font_size=12),
        TocLine(text="1.1.1 Events ................. 8", bbox=[120, 132, 320, 144], indent=120, toc_page_index=4, font_size=11),
    ]
    entries = infer_hierarchy(parse_toc_lines(lines))
    assert [entry.level for entry in entries] == [1, 2, 3]


def test_parse_toc_lines_handles_split_numbering_and_leader_pages():
    lines = [
        TocLine(text="3.10 Limit Theorems in R d", bbox=[72, 100, 340, 114], indent=72, toc_page_index=5, font_size=12),
        TocLine(text=". . . . . . . . . . . . . . . . . . . . 196", bbox=[220, 100, 360, 114], indent=220, toc_page_index=5, font_size=12),
        TocLine(text="Doob's Inequality, Convergence in L p , p > 1", bbox=[72, 130, 360, 144], indent=72, toc_page_index=5, font_size=12),
        TocLine(text="4.4", bbox=[72, 146, 94, 158], indent=72, toc_page_index=5, font_size=12),
        TocLine(text=". . . . . . . . 235", bbox=[220, 146, 320, 158], indent=220, toc_page_index=5, font_size=12),
    ]
    entries = parse_toc_lines(lines)
    assert entries[0].title == "3.10 Limit Theorems in R d"
    assert entries[0].printed_page_label == "196"
    assert entries[1].title == "4.4 Doob's Inequality, Convergence in L p , p > 1"
    assert entries[1].printed_page_label == "235"


def test_parse_toc_lines_handles_split_chapter_number_and_wrapped_title():
    lines = [
        TocLine(text="4.", bbox=[72, 100, 82, 112], indent=72, toc_page_index=4, font_size=12),
        TocLine(
            text="The Ito Formula and the Martingale Representation Theo-",
            bbox=[96, 100, 320, 112],
            indent=96,
            toc_page_index=4,
            font_size=12,
        ),
        TocLine(
            text="rem . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .",
            bbox=[96, 116, 320, 128],
            indent=96,
            toc_page_index=4,
            font_size=12,
        ),
        TocLine(text="43", bbox=[330, 116, 345, 128], indent=330, toc_page_index=4, font_size=12),
        TocLine(text="4.1", bbox=[96, 140, 116, 152], indent=96, toc_page_index=4, font_size=12),
        TocLine(
            text="The 1-dimensional Ito formula . . . . . . . . . . . . . . . .",
            bbox=[120, 140, 320, 152],
            indent=120,
            toc_page_index=4,
            font_size=12,
        ),
        TocLine(text="43", bbox=[330, 140, 345, 152], indent=330, toc_page_index=4, font_size=12),
    ]

    entries = infer_hierarchy(parse_toc_lines(lines))

    assert [entry.title for entry in entries] == [
        "4. The Ito Formula and the Martingale Representation Theorem",
        "4.1 The 1-dimensional Ito formula",
    ]
    assert [entry.level for entry in entries] == [1, 2]


def test_parse_toc_lines_ignores_roman_running_header():
    lines = [
        TocLine(text="XIX", bbox=[360, 70, 380, 82], indent=360, toc_page_index=4, font_size=10),
        TocLine(
            text="12. Application to Mathematical Finance . . . . . . . . . . . . . . . . . 249",
            bbox=[72, 100, 350, 112],
            indent=72,
            toc_page_index=4,
            font_size=12,
        ),
    ]

    entries = parse_toc_lines(lines)

    assert entries[0].title == "12. Application to Mathematical Finance"


def test_parse_toc_lines_normalizes_extracted_circumflex_titles():
    lines = [
        TocLine(text="3. Itˆo Integrals ........ 21", bbox=[72, 100, 320, 114], indent=72, toc_page_index=4, font_size=12),
        TocLine(text="4. It^o Formula .......... 43", bbox=[72, 120, 320, 134], indent=72, toc_page_index=4, font_size=12),
    ]

    entries = parse_toc_lines(lines)

    assert [entry.title for entry in entries] == ["3. Itô Integrals", "4. Itô Formula"]
