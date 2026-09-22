"""What the reader sees in one file, before and after structure.

    python scripts/debug_reader.py resources/policy/rbi-source/MD-NBFC-IRACP-2025.pdf
"""

import sys
from collections import Counter
from pathlib import Path

from nbfc_ews.retrieval.docling_reader import DoclingReader, _items

path = Path(sys.argv[1])
reader = DoclingReader()
doc = reader._get_converter().convert(path).document
items = _items(doc, real_levels=path.suffix.lower() in {".docx", ".html", ".htm"})

print("ITEM KINDS", dict(Counter(i.kind for i in items)))
print()
print("FIRST 40 ITEMS")
for item in items[:40]:
    print(f"  {item.kind:<10} marker={item.marker!r:<7} level={item.level}  {item.text[:60]!r}")

result = reader.read(path)
print()
print("QUALITY", result.meta["quality"])
print()
print("FIRST 15 SECTIONS")
for s in result.sections[:15]:
    print(f"  L{s.level} number={s.number!r:<10} heading={s.heading[:50]!r}  body={s.body[:40]!r}")
print()
print("SECTIONS WHOSE NUMBER IS NOT A PLAIN NUMBER")
print("(the heading column is the parent chain - the other half of the dedupe key)")
for i, s in enumerate(result.sections):
    if s.number and not s.number.isdigit():
        print(f"  #{i:<4} L{s.level} number={s.number!r:<12} heading={s.heading[:70]!r}")
