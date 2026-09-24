"""Exact token counts for the policy corpus, using the embedder's own tokenizer."""

import glob
import re
import statistics
from pathlib import Path

import tiktoken

ROOT = Path(__file__).resolve().parent.parent / "resources" / "policy"
enc = tiktoken.get_encoding("cl100k_base")

rows = []
for path in sorted(glob.glob(str(ROOT / "*" / "*.md"))):
    if path.endswith("README.md"):
        continue
    raw = Path(path).read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n\n(.*)$", raw, re.DOTALL)
    body = match.group(2)
    words = len(body.split())
    tokens = len(enc.encode(body))
    rows.append((Path(path).name, words, tokens, tokens / words))

tokens = [r[2] for r in rows]
ratios = [r[3] for r in rows]

print(f"sections             : {len(rows)}")
print(f"tokens  min/med/max  : {min(tokens)} / {int(statistics.median(tokens))} / {max(tokens)}")
print(f"ratio   min/mean/max : {min(ratios):.3f} / {statistics.mean(ratios):.3f} / {max(ratios):.3f}")
print(f"total tokens         : {sum(tokens)}")
print()
print("longest five:")
for name, w, t, r in sorted(rows, key=lambda x: -x[2])[:5]:
    print(f"  {t:4}t {w:4}w  ratio {r:.2f}  {name}")