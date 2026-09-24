import pytest

from nbfc_ews.retrieval.read import MarkdownReader, ReaderError


@pytest.fixture
def reader():
    return MarkdownReader()


def write(tmp_path, text):
    path = tmp_path / "section.md"
    path.write_text(text, encoding="utf-8")
    return path


def test_frontmatter_becomes_meta(reader, tmp_path):
    path = write(tmp_path, """---
doc_id: sop-collections
section: "5.2 Field visit"
sensitivity: 2
---

Field visits may be initiated once an account has crossed 45 days past due.
""")
    doc = reader.read(path)

    assert doc.meta["doc_id"] == "sop-collections"
    assert doc.meta["section"] == "5.2 Field visit"
    assert doc.meta["sensitivity"] == 2


def test_the_body_excludes_the_frontmatter(reader, tmp_path):
    path = write(tmp_path, """---
doc_id: x
---

The body.
""")
    doc = reader.read(path)

    assert doc.sections[0].body == "The body."
    assert "doc_id" not in doc.sections[0].body


def test_a_body_with_no_headings_is_one_section(reader, tmp_path):
    """The normal shape for our corpus - the section name lives in frontmatter."""
    path = write(tmp_path, """---
doc_id: x
---

One subject, no headings.
""")
    doc = reader.read(path)

    assert len(doc.sections) == 1
    assert doc.sections[0].heading == ""
    assert doc.sections[0].level == 2


def test_two_headings_give_two_sections(reader, tmp_path):
    path = write(tmp_path, """---
doc_id: x
---

## First

Text one.

## Second

Text two.
""")
    doc = reader.read(path)

    assert [s.heading for s in doc.sections] == ["First", "Second"]
    assert [s.body for s in doc.sections] == ["Text one.", "Text two."]


def test_heading_level_is_captured(reader, tmp_path):
    path = write(tmp_path, """---
doc_id: x
---

## Two

a

### Three

b
""")
    doc = reader.read(path)

    assert [s.level for s in doc.sections] == [2, 3]


def test_text_before_the_first_heading_is_kept(reader, tmp_path):
    """A preamble has no heading but is still policy. Losing it is silent."""
    path = write(tmp_path, """---
doc_id: x
---

Preamble that belongs to no heading.

## A heading

Under the heading.
""")
    doc = reader.read(path)

    assert len(doc.sections) == 2
    assert doc.sections[0].heading == ""
    assert doc.sections[0].body == "Preamble that belongs to no heading."
    assert doc.sections[1].heading == "A heading"


def test_a_file_without_frontmatter_is_refused(reader, tmp_path):
    path = write(tmp_path, "Just a body, no frontmatter.\n")

    with pytest.raises(ReaderError, match="no YAML frontmatter"):
        reader.read(path)


def test_broken_frontmatter_is_refused(reader, tmp_path):
    path = write(tmp_path, """---
doc_id: [unclosed
---

Body.
""")
    with pytest.raises(ReaderError):
        reader.read(path)


def test_frontmatter_that_is_not_a_mapping_is_refused(reader, tmp_path):
    path = write(tmp_path, """---
- one
- two
---

Body.
""")
    with pytest.raises(ReaderError, match="not a mapping"):
        reader.read(path)


def test_a_dash_line_inside_the_body_is_not_frontmatter(reader, tmp_path):
    """The frontmatter pattern is anchored to the start of the file, not any line."""
    path = write(tmp_path, """---
doc_id: x
---

Before.

---

After.
""")
    doc = reader.read(path)

    assert doc.meta == {"doc_id": "x"}
    assert "After." in doc.sections[0].body

# --- gluing formatting runs ---------------------------------------------------


def test_formatting_runs_are_glued_back_with_their_spaces() -> None:
    """Word splits a run at every bold or italic change, losing the space."""
    from nbfc_ews.retrieval.docling_reader import _glue

    assert _glue(["SOP 5.1.", "It is forbidden"]) == "SOP 5.1. It is forbidden"
    assert _glue(["as on the", "9th, 16th", "of the month"]) == "as on the 9th, 16th of the month"
    assert _glue(["Cure is not upgrade", "."]) == "Cure is not upgrade."
    assert _glue(["one", "  ", "two"]) == "one two"
