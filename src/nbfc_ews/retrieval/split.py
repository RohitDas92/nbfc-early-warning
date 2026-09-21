"""Hybrid chucking: structure first, size as a backstop.

Heading decide the boundries where they exits. SIze only intervens when a
section is too long for the embedder or too short to stand alone."""

import functools
import re

import tiktoken

from nbfc_ews.retrieval.base import Piece
from nbfc_ews.retrieval.read import RawDoc, Section

# Regulatory text wants largeer chunks than general pros - clauses reference
# each other, and cutting a proviso away from its clause can reverse it.

MAX_TOKENS = 800
MIN_TOKENS = 120
OVERLAP_TOKENS = 80

#cl100k_base is what text-embedding-3-small uses.
ENCODING = "cl100k_base"

_PARAGRAPH = re.compile(r"\n\s*\n")
_SENTENCE = re.compile(r"(?<=[.!?])\s+")

@functools.lru_cache(maxsize=1)
def _encoding() -> tiktoken.Encoding:
    """Loaded on the first use, not at import.
    tiktoken downloads its table the first time and caches it on the disk. Doing
    that at import would mean this module cannot ever be imported on a machine
    with no network - including CI"""
    return tiktoken.get_encoding(ENCODING)

def count_tokens(text: str) -> int:
    """Exact, using the tokenizer the embedding model actually uses.
    
    Not words, 'SMA-2' is one word and 4 tokens; 'RBI/2022-23/108' is one
    word and about nine tokens. A word-based extimator uner-counts this corpus badly."""

    return len(_encoding().encode(text))

def split(
        doc: RawDoc,
        *,
        max_tokens: int = MAX_TOKENS,
        min_tokens: int =  MIN_TOKENS,
        overlap: int = OVERLAP_TOKENS
) -> list[Piece]:
    """One document into pices. Pure - same document, same pieces, every time."""
    base = str(doc.meta.get("section") or doc.path.stem)
    pieces: list[Piece] = []

    for section in _merge_short(doc.sections, min_tokens):
        parts = [base]
        if section.heading:
            parts.append(section.heading)
        if section.number:
            parts.append(f"para {section.number}")
        path = " > ".join(parts)

        texts = [
            text.strip()
            for text in _split_long(section.body, max_tokens, overlap)
            if text.strip()
        ] 
        pieces.extend(
            Piece(
                heading_path=path,
                number=section.number,
                chunk_index=index,
                chunk_count=len(texts),
                text=text
            )
            for index, text in enumerate(texts)
        )

    return pieces

def _merge_short(sections: tuple[Section, ...], min_tokens: int) -> list[Section]:
    """Absorb a too-short section into the next one - but never across a 
    higher-level heading. A ### may merge with next ###; it may not be 
    swallowed into a different ##."""
    merged: list[Section] = []

    for section in sections:
        previous = merged[-1] if merged else None
        if (
            previous is not None
            and count_tokens(previous.body) < min_tokens
            and section.level >= previous.level
        ):
            merged[-1] = Section(
                level= previous.level,
                number=previous.number or section.number,
                heading= previous.heading or section.heading,
                body = f"{previous.body}\n\n{section.body}".strip(),
            )
        else:
            merged.append(section)

    return merged

def _split_long(text: str, max_tokens: int, overlap: int) -> list[str]:
    """Paragraphs first. Only descend to sentences, then tokens, when forced."""
    if count_tokens(text) <= max_tokens:
        return [text]

    paragraphs = [p.strip() for p in _PARAGRAPH.split(text) if p.strip()]
    if len(paragraphs) <= 1:
        return _split_sentences(text, max_tokens, overlap)

    out: list[str] = []
    for piece in _pack(paragraphs, "\n\n", max_tokens, overlap):
        if count_tokens(piece) <= max_tokens:
            out.append(piece)
        else:
            out.extend(_split_sentences(piece, max_tokens, overlap))
    return out

def _split_sentences(text: str, max_tokens: int, overlap: int) -> list[str]:
    sentences = [s.strip() for s in _SENTENCE.split(text) if s.strip()]
    if len(sentences) <= 1:
        return _split_tokens(text, max_tokens, overlap)

    out: list[str] = []
    for piece in _pack(sentences, " ", max_tokens, overlap):
        if count_tokens(piece) <= max_tokens:
            out.append(piece)
        else:
            out.extend(_split_tokens(piece, max_tokens, overlap))
    return out

def _split_tokens(text: str, max_tokens: int, overlap: int) -> list[str]:
    """Last resort = one sentence longer than the budget has no natural seam.
    
    Cuts the token itself and decodes each slice back to text, so the 
    pieces are exactly at budget rather than approximately."""

    encoding = _encoding()
    tokens = encoding.encode(text)
    if not tokens:
        return []

    step = max(1, max_tokens - overlap)

    out: list[str] = []
    start = 0
    while start < len(tokens):
        out.append(encoding.decode(tokens[start : start + max_tokens]). strip())
        start += step
    return out

def _pack(units: list[str], joiner: str, max_tokens: int, overlap: int) -> list[str]:
    """Fill a piece unitll the next unit would owerflow it, then start a new one
    carrying the tail of the last as overlap."""
    pieces: list[str] = []
    current: list[str] = []

    for unit in units:
        if current and count_tokens(joiner.join([*current, unit])) > max_tokens:
            pieces.append(joiner.join(current))
            current = _tail(current, joiner, overlap)
        current.append(unit)

    if current:
        pieces.append(joiner.join(current))

    return pieces

def _tail(units: list[str], joiner: str, overlap: int) -> list[str]:
    """The last few units, up to overlap budget."""
    if overlap <= 0:
        return []

    kept: list[str] = []
    for unit in reversed(units):
        if count_tokens(joiner.join([unit, *kept])) > overlap:
            break
        kept.insert(0, unit)
    return kept

