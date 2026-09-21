"""What does Docling actually return for our PDFs? Look before writing a reader."""

import sys
from collections import Counter
from pathlib import Path

from docling.document_converter import DocumentConverter

src = Path(sys.argv[1] if len(sys.argv) > 1 else "resources/policy/pdf/sop-collections.pdf")
print(f"converting {src} ...")

doc = DocumentConverter().convert(src).document

labels = Counter()
rows = []
for item, level in doc.iterate_items():
    label = getattr(item, "label", None)
    label = getattr(label, "value", str(label))
    text = (getattr(item, "text", "") or "").strip()
    labels[label] += 1
    rows.append((label, level, text, type(item).__name__))

print()
print("LABEL COUNTS")
for label, n in labels.most_common():
    print(f"  {label:20} {n}")

print()
print("FIRST 20 ITEMS")
for label, level, text, cls in rows[:20]:
    print(f"  [{label:18}] lvl={level} <{cls}> {text[:70]}")

print()
print("TABLES")
for item, _ in doc.iterate_items():
    if type(item).__name__ == "TableItem":
        print("  found a TableItem, markdown export:")
        print(item.export_to_markdown(doc))
        break
else:
    print("  none found")

print()
print("LIST MARKERS")
shown = 0
for item, _ in doc.iterate_items():
    if type(item).__name__ == "ListItem":
        print(f"  marker={item.marker!r}  enumerated={item.enumerated}  {item.text[:50]}")
        shown += 1
        if shown == 10:
            break