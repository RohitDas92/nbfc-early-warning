"""Probe Azure Document Intelligence on a real PDF. Prints its inputs first."""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import (
    AnalyzeDocumentRequest,
    DocumentContentFormat,
)
from azure.core.credentials import AzureKeyCredential

from nbfc_ews.config import AZURE_DOCINT_ENDPOINT, AZURE_DOCINT_KEY


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python scripts/probe_docint.py <path-to-pdf>")

    path = Path(sys.argv[1])

    # Echo the inputs. This is what found the wrong deployment name last time.
    print(f"endpoint : {AZURE_DOCINT_ENDPOINT!r}")
    print(f"key      : {AZURE_DOCINT_KEY[:6]}... ({len(AZURE_DOCINT_KEY)} chars)")
    print(f"file     : {path}  ({path.stat().st_size:,} bytes)")
    print()

    client = DocumentIntelligenceClient(
        endpoint=AZURE_DOCINT_ENDPOINT,
        credential=AzureKeyCredential(AZURE_DOCINT_KEY),
    )

    poller = client.begin_analyze_document(
        "prebuilt-layout",
        AnalyzeDocumentRequest(bytes_source=path.read_bytes()),
        output_content_format=DocumentContentFormat.MARKDOWN,
    )
    result = poller.result()

    print(f"pages    : {len(result.pages or [])}")
    print(f"markdown : {len(result.content or '')} chars")
    print()

    # Q3: which role do headings get?
    roles = Counter(p.role or "(none)" for p in (result.paragraphs or []))
    print("paragraph roles:")
    for role, n in roles.most_common():
        print(f"  {role:<20} {n}")
    print()

    print("first 15 non-body paragraphs:")
    shown = 0
    for para in result.paragraphs or []:
        if para.role is None:
            continue
        print(f"  [{para.role}] {para.content[:90]}")
        shown += 1
        if shown == 15:
            break
    print()

    # Q2: does the SMA table come back whole?
    tables = result.tables or []
    print(f"tables   : {len(tables)}")
    for i, table in enumerate(tables):
        print(f"\n--- table {i}: {table.row_count} rows x {table.column_count} cols")
        grid: dict[tuple[int, int], str] = {}
        for cell in table.cells:
            grid[(cell.row_index, cell.column_index)] = cell.content.replace("\n", " ")
        for r in range(table.row_count):
            cells = [grid.get((r, c), "") for c in range(table.column_count)]
            print("    | " + " | ".join(cells))


if __name__ == "__main__":
    main()