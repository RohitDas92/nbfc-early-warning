"""The general structure rules, on hand-written items.  No parser needed."""

from nbfc_ews.retrieval.structure import Item, build_structure, parse_enumerator


def h(text: str, level: int | None = None) -> Item:
    return Item("heading", text, level=level)


def p(text: str) -> Item:
    return Item("text", text)


def li(marker: str, text: str) -> Item:
    return Item("list_item", text, marker=marker)


# --- shapes of numbering ------------------------------------------------------


def test_regulator_shape_chapter_part_paragraph() -> None:
    doc = build_structure([
        h("Chapter I - Preliminary"),
        h("A. Short title and commencement"),
        li("1.", "These Directions shall be called the Directions."),
        li("2.", "These Directions come into force at once."),
        h("B. Applicability"),
        li("3.", "These Directions apply to:"),
        li("(1)", "NBFC-D"),
        li("(2)", "NBFC-ICC"),
        h("Chapter II - Prudential Norms"),
        h("A. Asset Classification"),
        li("4.", "An asset becomes non-performing when..."),
    ])

    assert [s.number for s in doc.sections] == ["1", "2", "3", "4"]
    assert [s.level for s in doc.sections] == [3, 3, 3, 3]
    assert doc.sections[2].heading == "Chapter I - Preliminary > B. Applicability"
    assert doc.sections[3].heading == "Chapter II - Prudential Norms > A. Asset Classification"
    assert doc.quality.passed  # "A." twice is fine: different chapters


def test_sub_clauses_stay_inside_their_paragraph() -> None:
    doc = build_structure([
        h("B. Applicability"),
        li("3.", "These Directions apply to:"),
        li("(1)", "NBFC-D"),
        li("(2)", "NBFC-ICC"),
    ])

    assert len(doc.sections) == 1
    assert "(1) NBFC-D" in doc.sections[0].body
    assert "(2) NBFC-ICC" in doc.sections[0].body


def test_a_numbered_paragraph_labelled_as_a_heading_is_still_a_paragraph() -> None:
    doc = build_structure([
        h("Chapter II - Norms"),
        h("C. Provisioning"),
        li("29.", "Provisions are made..."),
        h("30. Project Finance"),
        p("Project loans are classified..."),
        li("31.", "Further provisions..."),
    ])

    assert [s.number for s in doc.sections] == ["29", "30", "31"]
    assert {s.level for s in doc.sections} == {3}
    assert doc.sections[2].heading == "Chapter II - Norms > C. Provisioning"


def test_dotted_numbering_takes_its_depth_from_the_dots() -> None:
    doc = build_structure([
        h("1. Scope"), p("a"),
        h("1.1 Purpose"), p("b"),
        h("1.2 Coverage"), p("c"),
        h("2. Buckets"), p("d"),
    ])

    assert [s.number for s in doc.sections] == ["1", "1.1", "1.2", "2"]
    assert [s.level for s in doc.sections] == [1, 2, 2, 1]
    assert doc.sections[2].heading == "1. Scope > 1.2 Coverage"


def test_contract_shape_keeps_lettered_and_roman_clauses_inline() -> None:
    doc = build_structure([
        h("1. Definitions"),
        li("(a)", "Borrower means..."),
        li("(b)", "Lender means..."),
        li("(i)", "for the avoidance of doubt..."),
    ])

    assert len(doc.sections) == 1
    assert "(i) for the avoidance of doubt" in doc.sections[0].body


def test_i_after_h_is_a_letter_and_i_alone_is_roman() -> None:
    assert parse_enumerator("(i) x", {"paren-alpha-lower": "h"}).style == "paren-alpha-lower"
    assert parse_enumerator("(i) x", {}).style == "paren-roman-lower"
    assert parse_enumerator("C. Definitions", {"dot-alpha-upper": "B"}).style == "dot-alpha-upper"
    assert parse_enumerator("C1. Default loss", {}).style == "dot-alpha-upper"
    assert parse_enumerator("I. Introduction", {}).style == "dot-roman-upper"


# --- real heading levels (Word, HTML) -----------------------------------------


def test_real_heading_levels_are_used_and_lists_stay_in_the_body() -> None:
    doc = build_structure([
        Item("title", "Collections Standard Operating Procedure"),
        h("2.1 Days past due", level=2),
        p("DPD is the number of days..."),
        li("1.", "Check the due date."),
        h("2.2 Cure and upgrade", level=2),
        p("Cure is not upgrade."),
    ])

    assert doc.title == "Collections Standard Operating Procedure"
    assert [s.number for s in doc.sections] == ["2.1", "2.2"]
    assert [s.level for s in doc.sections] == [2, 2]
    assert "1. Check the due date." in doc.sections[0].body
    assert doc.quality.passed


def test_a_skipped_heading_level_is_counted() -> None:
    doc = build_structure([h("Intro", level=1), p("a"), h("Deep", level=3), p("b")])

    assert doc.quality.level_jumps == 1
    assert not doc.quality.passed


# --- degrading, and knowing it --------------------------------------------------


def test_an_unnumbered_document_still_splits_on_headings_but_fails_quality() -> None:
    doc = build_structure([h("Overview"), p("x" * 50), h("Process"), p("y" * 50)])

    assert [s.heading for s in doc.sections] == ["Overview", "Process"]
    assert doc.quality.numbered_share == 0
    assert not doc.quality.passed


def test_a_repeated_number_under_one_parent_is_reported() -> None:
    doc = build_structure([h("A. Part"), li("5.", "one"), li("5.", "again")])

    assert doc.quality.duplicate_numbers == ("5",)
    assert not doc.quality.passed


# --- housekeeping ---------------------------------------------------------------


def test_a_heading_with_nothing_under_it_is_not_a_section() -> None:
    doc = build_structure([
        h("Table of Contents"),
        h("1. Scope"),
        Item("table", "| a | b |\n|---|---|\n| 1 | 2 |"),
    ])

    assert [s.number for s in doc.sections] == ["1"]
    assert "| 1 | 2 |" in doc.sections[0].body


def test_footnotes_are_collected_at_the_end() -> None:
    doc = build_structure([h("1. Scope"), p("body"), Item("footnote", "3 Inserted vide circular")])

    assert doc.sections[-1].heading == "Footnotes"
    assert "Inserted vide circular" in doc.sections[-1].body


def test_footnote_noise_is_stripped_from_headings() -> None:
    doc = build_structure([h("C1. 3 [Provisioning for portfolios]"), p("text")])

    assert doc.sections[0].heading == "C1. Provisioning for portfolios"


def test_text_before_any_heading_is_the_preamble() -> None:
    doc = build_structure([p("RBI/2025-26/356"), h("1. Scope"), p("x")])

    assert (doc.sections[0].heading, doc.sections[0].number) == ("", "")
    assert doc.sections[0].body == "RBI/2025-26/356"


def test_runs_of_spaces_are_collapsed() -> None:
    doc = build_structure([h("1.  Scope   of  work"), p("x")])

    assert doc.sections[0].heading == "1. Scope of work"


# --- a parser that labels paragraphs as headings ---------------------------------


def test_heading_number_can_come_from_marker() -> None:
    doc = build_structure([
        Item("heading", "Chapter I - Preliminary"),
        Item("heading", "These Directions shall be called the RBI Directions.", marker="1."),
        Item("heading", "They shall come into force on April 1, 2025.", marker="2."),
    ])

    assert [s.number for s in doc.sections] == ["1", "2"]
    assert doc.quality.numbered_share == 1.0


def test_inline_marked_heading_is_a_subclause() -> None:
    doc = build_structure([
        Item("heading", "Applicability", marker="3."),
        Item("heading", "NBFC-D registered with the RBI.", marker="(1)"),
        Item("heading", "NBFC-ND above the threshold.", marker="(2)"),
    ])

    assert len(doc.sections) == 1
    assert doc.sections[0].number == "3"
    assert "(1) NBFC-D registered" in doc.sections[0].body
    assert "(2) NBFC-ND above" in doc.sections[0].body