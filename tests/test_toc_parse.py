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
