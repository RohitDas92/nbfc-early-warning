"""The reader on real files.  Slow - Docling loads layout models - so opt-in:

    $env:EWS_DOCLING="1"; pytest tests/integration/test_docling_reader.py -v

Skipped when Docling is not installed or a file is missing (CI has neither).
"""

import json
import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("EWS_DOCLING") != "1", reason="set EWS_DOCLING=1 to run Docling"
)

pytest.importorskip("docling")

from nbfc_ews.retrieval.docling_reader import DoclingReader

POLICY = Path(__file__).resolve().parents[2] / "resources" / "policy"
SOP = POLICY / "docx" / "sop-collections.docx"
ARCHIVE = POLICY / "docx" / "archive" / "sop-collections--7.1--until-2026-07-01.docx"
RBI = POLICY / "rbi-source" / "MD-NBFC-IRACP-2025.pdf"


def read(path: Path):
    if not path.exists():
        pytest.skip(f"{path.name} is not here")
    return DoclingReader().read(path)


@pytest.fixture(scope="module")
def sop():
    return read(SOP)


@pytest.fixture(scope="module")
def rbi():
    return read(RBI)


def section(doc, number: str):
    return next(s for s in doc.sections if s.number == number)


# --- the Word document ---------------------------------------------------------


def test_every_numbered_section_matches_the_manifest_both_ways(sop) -> None:
    manifest = json.loads((POLICY / "manifest" / "sop-collections.json").read_text(encoding="utf-8"))
    assert {s.number for s in sop.sections if s.number} == set(manifest["sections"])


def test_word_headings_give_exact_levels(sop) -> None:
    assert {s.level for s in sop.sections if s.number} == {2}


def test_section_2_1_holds_the_whole_sma_table(sop) -> None:
    body = section(sop, "2.1").body
    for row in ("SMA-0", "SMA-1", "SMA-2"):
        assert row in body


def test_italic_text_does_not_break_a_sentence(sop) -> None:
    body = section(sop, "2.1").body
    assert "for the due date, irrespective" in body


def test_the_word_document_passes_quality(sop) -> None:
    assert sop.meta["title"] == "Collections Standard Operating Procedure"
    assert sop.meta["quality"].passed, sop.meta["quality"]


def test_the_archived_version_reads_on_its_own() -> None:
    doc = read(ARCHIVE)
    assert [s.number for s in doc.sections if s.number] == ["7.1"]
    assert "fortnightly" in section(doc, "7.1").body


# --- the regulator's PDF ------------------------------------------------------


def test_rbi_paragraphs_are_numbered_and_unique(rbi) -> None:
    paragraphs = [s.number for s in rbi.sections if s.number.isdigit()]
    assert len(paragraphs) >= 50
    assert rbi.meta["quality"].duplicate_numbers == ()


def test_rbi_paragraphs_carry_their_chapter_and_part(rbi) -> None:
    first = section(rbi, "1")
    assert first.heading.startswith("Chapter I")
    assert first.level == 3


def test_the_rbi_pdf_passes_quality(rbi) -> None:
    assert rbi.meta["quality"].passed, rbi.meta["quality"]

