"""Chunk one document and look for problems.

    python scripts/debug_chunks.py resources/policy/rbi-source/MD-NBFC-IRACP-2025.pdf

Nothing here is a test.  It is a way to look at a document the index has never
seen, before deciding whether it belongs there.
"""

import re
import statistics
import sys
from pathlib import Path

from nbfc_ews.retrieval.docling_reader import DoclingReader
from nbfc_ews.retrieval.read import RawDoc
from nbfc_ews.retrieval.split import MAX_TOKENS, MIN_TOKENS, count_tokens, split

path = Path(sys.argv[1])
doc = DoclingReader().read(path)
pieces = split(RawDoc(path=path, meta={"section": path.stem}, sections=doc.sections))

print("QUALITY", doc.meta["quality"])
print(f"sections {len(doc.sections)}   chunks {len(pieces)}")

tokens = [count_tokens(piece.text) for piece in pieces]
print(f"tokens  min/median/max : {min(tokens)} / {int(statistics.median(tokens))} / {max(tokens)}")
print(
    f"over {MAX_TOKENS}: {sum(1 for t in tokens if t > MAX_TOKENS)}"
    f"   under {MIN_TOKENS}: {sum(1 for t in tokens if t < MIN_TOKENS)}"
)

unnumbered = [piece for piece in pieces if not piece.number]
print(f"unnumbered chunks: {len(unnumbered)}")

print("\nUNNUMBERED (first 5) - these can never be cited")
for piece in unnumbered[:5]:
    print(f"  {piece.heading_path[:60]!r}  {piece.text[:70]!r}")

print("\nSECTIONS THAT NEEDED SPLITTING")
for piece in pieces:
    if piece.chunk_count > 1 and piece.chunk_index == 0:
        print(f"  {piece.number:8} into {piece.chunk_count}   {piece.heading_path[:60]}")

print("\nTOKENISER-HOSTILE TERMS")
candidate = re.compile(r"[\w./-]*[A-Za-z]-?\d[\w./-]*")
terms = sorted({m.group(0) for piece in pieces for m in candidate.finditer(piece.text)})
print("  " + ", ".join(terms[:40]))

print("\nFIRST 3 CHUNKS")
for piece in pieces[:3]:
    print(f"  [{piece.number}] {piece.heading_path[:70]}")
    print(f"      {piece.text[:200]!r}")
