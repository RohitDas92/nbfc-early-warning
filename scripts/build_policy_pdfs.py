"""Rebuild the policy PDFs from the section files.

    python scripts/build_policy_pdfs.py

Each doc_id folder under resources/policy/ becomes one PDF in resources/policy/pdf/.
The .md.gen intermediates are throwaway; the section files are the source of truth.

Between pandoc and LibreOffice the .docx is patched so that tables cannot be
split across a page break.  A split table is unrecoverable downstream: both
Docling and Azure Document Intelligence read the continuation rows as loose
text, so an SMA table that runs over a page loses SMA-1 and SMA-2 silently.

Requires pandoc and libreoffice on PATH.
"""
import glob
import io
import re
import subprocess
import zipfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent / "resources" / "policy"

TITLES = {
    "sop-collections": "Collections Standard Operating Procedure",
    "sop-mandate": "Mandate Operations Standard Operating Procedure",
    "policy-settlement": "Settlement Policy",
    "policy-restructuring": "Restructuring Policy",
    "sop-legal-recovery": "Legal Recovery Standard Operating Procedure",
}

ORG = "Vidyanidhi Education Finance Limited"

# --- docx table pinning -----------------------------------------------------

_TABLE = re.compile(r"<w:tbl>.*?</w:tbl>", re.S)
_ROW = re.compile(r"<w:tr(?:\s[^>]*)?>.*?</w:tr>", re.S)
_ROW_OPEN = re.compile(r"<w:tr(?:\s[^>]*)?>")
_TRPR = re.compile(r"<w:trPr>(.*?)</w:trPr>", re.S)
_PARA = re.compile(r"<w:p(?:\s[^>]*)?>.*?</w:p>", re.S)
_PARA_OPEN = re.compile(r"<w:p(?:\s[^>]*)?>")
_PPR = re.compile(r"<w:pPr>(.*?)</w:pPr>", re.S)
_PSTYLE = re.compile(r"<w:pStyle[^>]*/>")


def _row_props(row: str, *, header: bool) -> str:
    """Add cantSplit (never break inside a row) and, on row 0, tblHeader."""
    extra = "<w:cantSplit/>" + ("<w:tblHeader/>" if header else "")
    found = _TRPR.search(row)
    if found is not None:
        at = found.end(1)  # append: CT_TrPr wants cnfStyle before cantSplit
        return row[:at] + extra + row[at:]
    open_tag = _ROW_OPEN.match(row).group(0)
    return f"{open_tag}<w:trPr>{extra}</w:trPr>{row[len(open_tag):]}"


def _keep_next(para: str) -> str:
    """keepNext on every paragraph but the last row is how Word pins a table."""
    if "<w:keepNext" in para:
        return para
    found = _PPR.search(para)
    if found is not None:
        style = _PSTYLE.search(found.group(1))
        at = found.start(1) + (style.end() if style is not None else 0)
        return para[:at] + "<w:keepNext/>" + para[at:]
    open_tag = _PARA_OPEN.match(para).group(0)
    return f"{open_tag}<w:pPr><w:keepNext/></w:pPr>{para[len(open_tag):]}"


def _pin_table(match: re.Match[str]) -> str:
    table = match.group(0)
    rows = _ROW.findall(table)
    if not rows:
        return table
    out = table
    for index, row in enumerate(rows):
        fixed = _row_props(row, header=index == 0)
        if index < len(rows) - 1:
            fixed = _PARA.sub(lambda m: _keep_next(m.group(0)), fixed)
        out = out.replace(row, fixed, 1)
    return out


def pin_tables(docx: Path) -> int:
    """Rewrite docx in place so no table splits across a page. Returns table count."""
    with zipfile.ZipFile(docx) as archive:
        items = [(i.filename, archive.read(i.filename)) for i in archive.infolist()]

    count = 0
    with zipfile.ZipFile(docx, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in items:
            if name == "word/document.xml":
                xml = data.decode("utf-8")
                count = len(_TABLE.findall(xml))
                data = _TABLE.sub(_pin_table, xml).encode("utf-8")
            archive.writestr(name, data)
    return count


# --- build ------------------------------------------------------------------


def build() -> None:
    out = ROOT / "_build"
    pdf = ROOT / "pdf"
    out.mkdir(exist_ok=True)
    pdf.mkdir(exist_ok=True)

    for doc, title in TITLES.items():
        parts = [f"% {title}\n% {ORG}\n% Effective 1 January 2019\n"]
        for path in sorted(glob.glob(str(ROOT / doc / "*.md"))):
            raw = io.open(path, encoding="utf-8").read()
            m = re.match(r"^---\n(.*?)\n---\n\n(.*)$", raw, re.S)
            if m is None:
                raise SystemExit(f"no frontmatter: {path}")
            meta = yaml.safe_load(m.group(1))
            if meta.get("effective_to") is not None:
                continue  # superseded: it stays in the corpus, not in the handbook
            parts.append(f"\n## {meta['section']}\n\n{m.group(2)}")

        src = out / f"{doc}.md.gen"
        io.open(src, "w", encoding="utf-8").write("\n".join(parts))
        docx = out / f"{doc}.docx"
        subprocess.run(["pandoc", str(src), "-o", str(docx), "--toc"], check=True)
        print(f"{doc}: pinned {pin_tables(docx)} tables")

    subprocess.run(
        ["libreoffice", "--headless", "--convert-to", "pdf", "--outdir", str(pdf)]
        + [str(p) for p in out.glob("*.docx")],
        check=True,
    )
    print(f"built {len(TITLES)} PDFs in {pdf}")


if __name__ == "__main__":
    build()
