"""The policy corpus on disk into database rows - all of it, or none of it."""

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from nbfc_ews.retrieval.base import Chunk, Piece, Scope
from nbfc_ews.retrieval.embed import Embedder
from nbfc_ews.retrieval.read import RawDoc, Reader
from nbfc_ews.retrieval.split import split

# One request per batch, not one per chunk.  The corpus is small; this keeps
# it that way when it is not.
EMBED_BATCH = 64

class IngestError(Exception):
    """The corpus could not be ingested. nothing was written."""

class _Rejected(Exception):
    """One document could not be indexed. the others still can."""

@dataclass(frozen=True)
class IngestReport:
    documents: int
    chunks: int
    rejected: tuple[tuple[str, str], ...]  #(doc_id, reason)
    corpus_version: int

_REQUIRED = ("doc_id", "file", "department", "sensitivity", "version", "effective_from")

_INSERT = """
insert into policy_chunk (
    id, doc_id, section, heading_path, chunk_index, chunk_count,
    rule_key, source_ref, version, effective_from, effective_to,
    department, sensitivity, acl_groups, text, embedding, embed_model
) values (
    %(id)s, %(doc_id)s, %(section)s, %(heading_path)s, %(chunk_index)s, %(chunk_count)s,
    %(rule_key)s, %(source_ref)s, %(version)s, %(effective_from)s, %(effective_to)s,
    %(department)s, %(sensitivity)s, %(acl_groups)s, %(text)s, %(embedding)s, %(embed_model)s
)
"""

def ingest(conn, root, *, reader, embedder) -> IngestReport:
    """Rebuild the index from the corpus under 'root'."""

    manifests = _manifests(root)
    if not manifests:
        raise IngestError(f"no manifest found under {root/ 'manifest'}")

    #2. for each one: read the document, check it, cut in chunks
    chunks: list[Chunk] = []
    rejected: list[tuple[str, str]] = []
    documents = 0

    for path in manifests:
        manifest = _load_manifest(path)
        doc_id = str(manifest.get("doc_id") or path.stem)
        try:
            chunks.extend(_chunks_for(manifest, root, reader))
        except _Rejected as exc:
            rejected.append((doc_id, str(exc)))
            continue
        documents += 1

    if not chunks:
        raise IngestError("no document survived the gates, the index was not touched")
    
    #3. turn every chunk's text into number
    #Embedding is a network call: do it before the transaction opens, never
    #while holding locks on the table readers are searching.
    vectors = _embed_all(embedder, [chunk.text for chunk in chunks])

    with conn.transaction():
        conn.execute("delete from policy_chunk")
        _insert(conn, chunks, vectors, embedder.name)
        row = conn.execute(
            "update corpus_meta set version = version + 1 where id = 1 returning version"
        ).fetchone()

        return IngestReport(documents, len(chunks), tuple(rejected), int(row[0]))
    

def _manifests(root: Path) -> list[Path]:
    """Current Document first, them archived ones."""
    manifest = root / "manifest"
    return sorted(manifest.glob("*.json")) + sorted((manifest / "archive").glob("*.json"))

def _load_manifest(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise IngestError(f"unreadable manifest {path} : {exc}") from exc
    if not isinstance(data, dict):
        raise IngestError(f"manifest is not a mapping: {path}")
    missing = [key for key in _REQUIRED if key not in data]
    if missing:
        raise IngestError(f"manifest {path} is missing {', '.join(missing)}")
    return data

def _metadata_for(manifest: dict[str, Any], number: str) -> dict[str, Any]:
    """The document's clause metadata, with the clause;s overrides applied."""
    merged = {
        "version": manifest["version"],
        "effective_from": manifest["effective_from"],
        "effective_to": manifest.get("effective_to"),
        "source_ref": manifest.get("source_ref"),
    }

    merged.update(manifest.get("overrides", {}).get(number, {}))
    return merged

def _chunk_id(doc_id: str, piece: Piece, meta: dict[str, Any]) -> str:
    """Stable across runs, so re-ingesting replaces rather than duplicates."""
    key = "|".join(
        (
            doc_id,
            piece.heading_path,
            piece.number,
            str(meta["version"]),
            str(meta["effective_from"]),
            str(meta["effective_to"]),
            str(piece.chunk_index),
        )
    )
    return hashlib.sha256(key.encode()).hexdigest()[:32]

def _chunk(manifest: dict[str, Any], piece: Piece) -> Chunk:
    """One piece of text, carrying its clause's governance metadata."""
    meta = _metadata_for(manifest, piece.number)
    doc_id = str(manifest["doc_id"])
    return Chunk(
        id=_chunk_id(doc_id, piece, meta),
        doc_id=doc_id,
        section=piece.number,
        heading_path=piece.heading_path,
        chunk_index=piece.chunk_index,
        chunk_count=piece.chunk_count,
        rule_key=None,
        source_ref=meta["source_ref"],
        version=int(meta["version"]),
        effective_from=date.fromisoformat(meta["effective_from"]),
        effective_to=date.fromisoformat(meta["effective_to"]) if meta["effective_to"] else None,
        scope=Scope(
            department=manifest["department"],
            sensitivity=int(manifest["sensitivity"]),
            acl_group=tuple(manifest.get("acl_groups") or ()),
        ),
        text=piece.text,
    )

def _chunks_for(manifest: dict[str, Any], root: Path, reader: Reader) ->list[Chunk]:
    """One document, read and cut into rows. Raises _Rejected if untrustworthy."""

    path = root / "docx" / manifest["file"]
    if not path.exists():
        raise _Rejected(f"document missing {path}")

    doc = reader.read(path)

    quality = doc.meta.get("quality")
    if quality is None:
        raise _Rejected("the reader reported no parse quality")
    if not quality.passed:
        raise _Rejected(f"parsed quality failed: {quality}")

    pieces = split(RawDoc(path=path, meta={"section": manifest["doc_id"]}, sections= doc.sections))
    return  [_chunk(manifest,piece) for piece in pieces]

def _vector_literal(values: Sequence) -> str:
    """pgvector's text input form. Registering psycopg's vector adapter would be a 
    neater; this keeps the module free of that dependency."""
    return "[" + ",".join(f"{value: .6f}" for value in values) + "]"

def _embed_all(embedder: Embedder, texts: Sequence) -> list[list[float]]:
    """Every chunk's text as a vector, one request per batch."""
    vectors: list[list[float]] = []
    for start in range(0, len(texts), EMBED_BATCH):
        vectors.extend(embedder.embed_documents(texts[start : start + EMBED_BATCH]))

    if len(vectors) != len(texts):
        raise IngestError(f"embedder returned {len(vectors)} vectors for {len(texts)} chunks")
    return vectors

def _insert(conn, chunks: Sequence[Chunk], vectors: Sequence[list[float]], model: str) -> None:
    """Every row in one statement.  The caller holds the transaction."""
    rows = [
        {
            "id": chunk.id,
            "doc_id": chunk.doc_id,
            "section": chunk.section,
            "heading_path": chunk.heading_path,
            "chunk_index": chunk.chunk_index,
            "chunk_count": chunk.chunk_count,
            "rule_key": chunk.rule_key,
            "source_ref": chunk.source_ref,
            "version": chunk.version,
            "effective_from": chunk.effective_from,
            "effective_to": chunk.effective_to,
            "department": chunk.scope.department,
            "sensitivity": chunk.scope.sensitivity,
            "acl_groups": list(chunk.scope.acl_group),
            "text": chunk.text,
            "embedding": _vector_literal(vector),
            "embed_model": model,
        }
        for chunk, vector in zip(chunks, vectors, strict=True)
    ]
    with conn.cursor() as cur:
        cur.executemany(_INSERT, rows)


