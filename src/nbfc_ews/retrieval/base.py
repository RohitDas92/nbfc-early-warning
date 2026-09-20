
"""Types and interface for policy retrival.

Implement live beside this file: pg vector.py is the default.
azure_search.py is benchmark comarison."""


from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Protocol

# A fused RRF score below this means nothing relevant was found.
# Empty is valid answer: gussing is not.

MIN_SCORE = 0.015

@dataclass(frozen=True)
class Scope:
    """Who may see a chunk.
    
    Carried by every chunk, and supplied by the caller. For a human it comes 
    from their Principal; for an agent it is declared at registration and is 
    the same on every run, so a finding is a property of the case and not of 
    whoever rab it."""

    department: str
    sensitivity: int
    acl_group: tuple[str, ...] = ()


@dataclass(frozen=True)
class Piece:
    """One cut of text from a section. The splitter's output, not yet embedded."""

    heading_path: str
    chunk_index: int
    chunk_count: int
    text: str

@dataclass(frozen=True)
class Chunk:
    """A piece plus its metadata, ready to be stored. Ingestion side."""

    id: str
    doc_id: str
    section: str
    heading_path: str
    chunk_index: int
    chunk_count: int
    rule_key: str|None
    source_ref: str|None
    version: int
    effective_from: date
    effective_to: date|None
    scope: Scope
    text: str

@dataclass(frozen=True)
class Passage:
    """A chunk that came back from a search. Retrieval side."""

    id: str
    doc_id: str
    section: str
    heading_path: str
    rule_key: str | None
    source_ref: str | None
    text: str
    score: float
    rank: int

@dataclass(frozen= True)
class Timing:
    """How long one retrieval took, by stage. Observability only.
    
    Never assert on these. They exits so we can tell when an index is needed
    instead of guessing."""

    embed_ms: float
    vector_ms: float
    keyword_ms: float
    total_ms: float

class Retriever(Protocol):
    """Anything that can find policy passage. Real or fake."""
    @property
    def name(self) -> str: ...

    def retrieve(
            self, 
            conn, 
            query: str,
            as_of: date,
            scope: Scope,
            *,
            canditates: int = 50,
            limit: int = 5,
            min_score: float = MIN_SCORE,
    ) -> tuple[Sequence[Passage], Timing]: ...
