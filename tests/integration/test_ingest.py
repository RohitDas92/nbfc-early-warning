"""Ingestion, against the real database, with a fake reader and embedder."""

import json
from pathlib import Path

import pytest

from nbfc_ews.retrieval.embed import FakeEmbedder
from nbfc_ews.retrieval.ingest import IngestError, ingest
from nbfc_ews.retrieval.read import RawDoc, Section
from nbfc_ews.retrieval.structure import ParseQuality


class FakeReader:
    """Hands back the sections the test asked for, with a quality verdict."""

    def __init__(self, sections, *, passed: bool = True) -> None:
        self._sections = sections
        self._quality = ParseQuality(1.0 if passed else 0.0, (), 0)

    def read(self, path: Path) -> RawDoc:
        return RawDoc(path=path, meta={"quality": self._quality}, sections=self._sections)


SECTIONS = (
    Section(level=2, number="1.1", heading="1.1 Scope", body="Scope body. " * 30),
    Section(level=2, number="1.2", heading="1.2 Contact", body="Contact body. " * 30),
)


def corpus(tmp_path: Path) -> Path:
    """A one-document corpus on disk: a manifest and an empty Word file."""
    root = tmp_path / "policy"
    (root / "manifest" / "archive").mkdir(parents=True)
    (root / "docx").mkdir()
    (root / "docx" / "sop-test.docx").write_bytes(b"")

    manifest = {
        "doc_id": "sop-test",
        "file": "sop-test.docx",
        "title": "Test SOP",
        "department": "collections",
        "sensitivity": 2,
        "acl_groups": [],
        "version": 1,
        "effective_from": "2019-01-01",
        "effective_to": None,
        "source_ref": "Internal",
    }
    (root / "manifest" / "sop-test.json").write_text(json.dumps(manifest), encoding="utf-8")
    return root


def test_a_clean_corpus_loads_and_bumps_the_version(conn, tmp_path) -> None:
    before = conn.execute("select version from corpus_meta where id = 1").fetchone()[0]

    report = ingest(conn, corpus(tmp_path), reader=FakeReader(SECTIONS), embedder=FakeEmbedder())

    stored = conn.execute("select count(*) from policy_chunk").fetchone()[0]
    assert report.documents == 1
    assert report.chunks == stored
    assert report.rejected == ()
    assert report.corpus_version == before + 1


def test_a_badly_parsed_document_is_rejected_and_nothing_is_written(conn, tmp_path) -> None:
    with pytest.raises(IngestError, match="no document survived"):
        ingest(
            conn,
            corpus(tmp_path),
            reader=FakeReader(SECTIONS, passed=False),
            embedder=FakeEmbedder(),
        )


def test_re_running_produces_the_same_ids(conn, tmp_path) -> None:
    root = corpus(tmp_path)
    ingest(conn, root, reader=FakeReader(SECTIONS), embedder=FakeEmbedder())
    first = [r[0] for r in conn.execute("select id from policy_chunk order by id")]

    ingest(conn, root, reader=FakeReader(SECTIONS), embedder=FakeEmbedder())
    second = [r[0] for r in conn.execute("select id from policy_chunk order by id")]

    assert first == second


def test_an_empty_corpus_is_refused(conn, tmp_path) -> None:
    root = tmp_path / "policy"
    (root / "manifest" / "archive").mkdir(parents=True)

    with pytest.raises(IngestError, match="no manifest"):
        ingest(conn, root, reader=FakeReader(SECTIONS), embedder=FakeEmbedder())