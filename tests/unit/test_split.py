"""Contracts for the chunker.

Every test builds its own synthetic document.  The real corpus never trips
either size backstop - the shortest section is 238 tokens and the longest 459,
against a 120/800 window - so the only way to test the backstops is to make
input that fires them on purpose.
"""

from pathlib import Path

from nbfc_ews.retrieval.base import Piece
from nbfc_ews.retrieval.read import RawDoc, Section
from nbfc_ews.retrieval.split import count_tokens, split

# Small budgets keep the fixtures readable.  The production numbers live in
# split.py as MAX_TOKENS / MIN_TOKENS / OVERLAP_TOKENS and are not under test
# here - the behaviour is, at whatever budget.
MAX = 50
MIN = 10
OVERLAP = 10


def words(count: int) -> str:
    """A body of roughly `count` tokens.  'alpha' is one token in cl100k_base."""
    return " ".join(["alpha"] * count)


def sentences(count: int) -> str:
    """One paragraph of short sentences, so _split_sentences is the path taken."""
    return " ".join(["Alpha beta gamma delta epsilon."] * count)


def section(
    body: str, *, level: int = 2, number: str = "", heading: str = ""
) -> Section:
    return Section(level=level, number=number, heading=heading, body=body)


def make_doc(*parts: Section, base: str = "sop") -> RawDoc:
    return RawDoc(
        path=Path("resources/policy/sop-collections/2.1.md"),
        meta={"section": base},
        sections=parts,
    )


def chunk(doc: RawDoc) -> list[Piece]:
    return split(doc, max_tokens=MAX, min_tokens=MIN, overlap=OVERLAP)


# --- structure --------------------------------------------------------------


def test_a_short_document_is_one_piece() -> None:
    pieces = chunk(make_doc(section(words(20))))

    assert len(pieces) == 1
    assert pieces[0].chunk_index == 0
    assert pieces[0].chunk_count == 1
    assert pieces[0].heading_path == "sop"


def test_heading_path_is_base_then_heading_then_para() -> None:
    doc = make_doc(section(words(20), number="18", heading="2.1 Buckets"))

    assert chunk(doc)[0].heading_path == "sop > 2.1 Buckets > para 18"


def test_heading_path_omits_the_parts_that_are_absent() -> None:
    assert chunk(make_doc(section(words(20), heading="2.1 Buckets")))[
        0
    ].heading_path == "sop > 2.1 Buckets"
    assert chunk(make_doc(section(words(20), number="18")))[
        0
    ].heading_path == "sop > para 18"


def test_chunk_count_is_per_section_not_per_document() -> None:
    """Two sections, one piece each.  Both must say 'piece 1 of 1'.

    If chunk_count were document-wide they would both say 'of 2', and a
    retrieved passage could not tell an analyst which siblings complete it.
    """
    doc = make_doc(
        section(words(20), heading="A", number="1"),
        section(words(20), heading="B", number="2"),
    )
    pieces = split(doc, max_tokens=MAX, min_tokens=1, overlap=OVERLAP)

    assert len(pieces) == 2
    assert [p.chunk_count for p in pieces] == [1, 1]
    assert [p.chunk_index for p in pieces] == [0, 0]


# --- merging ----------------------------------------------------------------


def test_a_short_section_merges_into_the_next() -> None:
    doc = make_doc(
        section(words(3), heading="A"),
        section(words(20), heading="B"),
    )
    pieces = chunk(doc)

    assert len(pieces) == 1
    assert "alpha" in pieces[0].text


def test_a_short_section_does_not_merge_across_a_higher_level_heading() -> None:
    """A ### may merge into a ###.  It may never be swallowed into a ##.

    Merging upward would glue the tail of one policy onto the head of another,
    and the resulting chunk would cite whichever heading won.
    """
    doc = make_doc(
        section(words(3), level=3, heading="2.1.1 Detail"),
        section(words(20), level=2, heading="2.2 Cure"),
    )

    assert len(chunk(doc)) == 2


# --- splitting --------------------------------------------------------------


def test_a_long_section_splits_into_several_pieces() -> None:
    body = "\n\n".join(words(30) for _ in range(6))
    pieces = chunk(make_doc(section(body)))

    assert len(pieces) > 1
    assert [p.chunk_index for p in pieces] == list(range(len(pieces)))
    assert all(p.chunk_count == len(pieces) for p in pieces)


def test_no_piece_exceeds_max_tokens() -> None:
    """The hard invariant.  Over budget is a failed embedding call in prod.

    The second section has no sentence break at all, which forces the last
    resort path - cutting the token list itself.
    """
    doc = make_doc(
        section("\n\n".join(sentences(4) for _ in range(5))),
        section(words(300), heading="No seams anywhere"),
    )

    for piece in split(doc, max_tokens=MAX, min_tokens=1, overlap=OVERLAP):
        assert count_tokens(piece.text) <= MAX


def test_consecutive_pieces_overlap() -> None:
    """With overlap on, the pieces together hold more tokens than the source.

    Asserted as a total rather than by string matching, because which unit
    carries over depends on where the seams fall.
    """
    body = sentences(30)
    pieces = chunk(make_doc(section(body)))

    assert len(pieces) > 1
    assert sum(count_tokens(p.text) for p in pieces) > count_tokens(body)


def test_overlap_of_zero_duplicates_nothing() -> None:
    body = sentences(30)
    pieces = split(make_doc(section(body)), max_tokens=MAX, min_tokens=MIN, overlap=0)

    assert sum(count_tokens(p.text) for p in pieces) <= count_tokens(body)


# --- contract ---------------------------------------------------------------


def test_the_citation_anchor_survives_every_piece() -> None:
    """Piece 3 of 3 of paragraph 18 is still paragraph 18.

    If the number only landed on the first piece, two thirds of every long
    RBI paragraph would retrieve with nothing to cite.
    """
    body = "\n\n".join(words(30) for _ in range(6))
    pieces = chunk(make_doc(section(body, number="18", heading="B. Asset")))

    assert len(pieces) > 1
    assert all(p.number == "18" for p in pieces)
    assert all(p.heading_path.endswith("para 18") for p in pieces)


def test_splitting_is_deterministic() -> None:
    doc = make_doc(
        section(words(200), number="18"),
        section(sentences(20), number="19"),
    )

    assert chunk(doc) == chunk(doc)


def test_empty_sections_produce_no_pieces() -> None:
    assert chunk(make_doc(section("   "), section("\n\n"))) == []

# --- citation integrity -----------------------------------------------------


def test_two_numbered_sections_never_merge() -> None:
    pieces = chunk(make_doc(
        section(words(5), number="12", heading="B. Applicability"),
        section(words(5), number="13", heading="B. Applicability"),
    ))

    assert [p.number for p in pieces] == ["12", "13"]


def test_a_short_unnumbered_section_still_merges() -> None:
    pieces = chunk(make_doc(
        section(words(5), heading="Overview"),
        section(words(20), heading="Process"),
    ))

    assert len(pieces) == 1


def test_a_numbered_heading_is_not_repeated_as_para() -> None:
    pieces = chunk(make_doc(section(words(20), number="2.1", heading="2.1 Days past due")))

    assert pieces[0].heading_path == "sop > 2.1 Days past due"


def test_a_paragraph_number_is_added_when_the_heading_lacks_it() -> None:
    pieces = chunk(make_doc(
        section(words(20), number="4", heading="Chapter I - Preliminary > B. Applicability")
    ))

    assert pieces[0].heading_path == "sop > Chapter I - Preliminary > B. Applicability > para 4"