"""Load the policy corpus into the database.

    python scripts/ingest_policy.py

Run as the database owner: ingestion deletes, and app_rw may not.
"""

from pathlib import Path

from nbfc_ews.db.engine import connect
from nbfc_ews.retrieval.docling_reader import DoclingReader
from nbfc_ews.retrieval.embed import AzureEmbedder
from nbfc_ews.retrieval.ingest import ingest

ROOT = Path(__file__).resolve().parent.parent / "resources" / "policy"

conn = connect()
report = ingest(conn, ROOT, reader=DoclingReader(), embedder=AzureEmbedder())
conn.commit()

print(f"documents : {report.documents}")
print(f"chunks    : {report.chunks}")
print(f"version   : {report.corpus_version}")
for doc_id, reason in report.rejected:
    print(f"rejected  : {doc_id} - {reason}")