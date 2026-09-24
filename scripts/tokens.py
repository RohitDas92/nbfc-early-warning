"""Which real corpus terms tokenise badly?"""

import re

from nbfc_ews.db.engine import connect

# The shapes that tripped us up: a letter next to a digit, with or without a
# hyphen, slash or dot between them.  Plain words tokenise fine.
CANDIDATE = re.compile(r"[\w./-]*(?:[A-Za-z][-/.]?\d|\d[-/.]?[A-Za-z])[\w./-]*")

conn = connect()
text = " ".join(row[0] for row in conn.execute("select text from policy_chunk"))
terms = sorted({m.group(0) for m in CANDIDATE.finditer(text)})

print(f"{len(terms)} candidate terms\n")

for term in terms:
    tsv = conn.execute("select to_tsvector('english', %s)", (term,)).fetchone()[0]
    lexemes = re.findall(r"'([^']*)'", tsv)
    broken = any(lex.startswith("-") for lex in lexemes) or any(
        re.search(r"[A-Za-z]", lex) and re.search(r"\d", lex) for lex in lexemes
    )
    if broken:
        print(f"  {term:24} -> {tsv}")