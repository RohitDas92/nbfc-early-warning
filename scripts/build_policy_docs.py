"""Build the internal policy documents from their Markdown source.

    python scripts/build_policy_docs.py

The Markdown section files under resources/policy/<doc_id>/ stand in for a
compliance team writing in Word.  This script produces what that team would
publish - and what ingestion reads.  Ingestion never reads the Markdown.

    docx/<doc_id>.docx                                 the current document
    docx/archive/<doc_id>--<n>--until-<date>.docx      each superseded version
    manifest/<same path>.json                          metadata per document
    pdf/<doc_id>.pdf                                   a printout, for people

A manifest plays the part of a document management system's metadata columns:
owner, access groups, version, effective dates - things a Word document cannot
sensibly carry.  It is written per document, as a DMS holds it, with overrides
only for clauses that genuinely stand apart.

Word files are patched between pandoc and LibreOffice so that no table can
split across a page: a split table is unrecoverable by any parser.

Requires pandoc.  LibreOffice is optional - without it the PDFs are skipped.
"""

import json
import re
import shutil
import subprocess
import zipfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent / "resources" / "policy"
BUILD = ROOT / "_build"
DOCX = ROOT / "docx"
MANIFEST = ROOT / "manifest"
PDF = ROOT / "pdf"

TITLES = {
    "sop-collections": "Collections Standard Operating Procedure",
    "sop-mandate": "Mandate Operations Standard Operating Procedure",
    "policy-settlement": "Settlement Policy",
    "policy-restructuring": "Restructuring Policy",
    "sop-legal-recovery": "Legal Recovery Standard Operating Procedure",
}

ORG = "Vidyanidhi Education Finance Limited"

_FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n(.*)\Z", re.DOTALL)
_DOTTED = re.compile(r"^\d+(\.\d+)+$")

# Metadata a clause may carry in its own right.  Everything else is a property
# of the document, and every clause in it inherits it.
_PER_CLAUSE = ("version", "effective_from", "effective_to", "source_ref")


@dataclass(frozen=True)
class SectionFile:
    number: str          # "2.1"
    title_line: str      # "2.1 Days past due and SMA buckets"
    meta: dict[str, Any]
    body: str


# --- reading the source -------------------------------------------------------


def _iso(value: Any) -> Any:
    """yaml reads 2019-01-01 as a date, and json cannot write one."""
    return value.isoformat() if isinstance(value, date) else value


def _number_key(number: str) -> tuple[int, ...]:
    """Sort 2.1 before 10.1 - as numbers, not as text."""
    return tuple(int(part) for part in number.split("."))


def read_sections(doc_id: str) -> list[SectionFile]:
    sections: list[SectionFile] = []
    for path in (ROOT / doc_id).glob("*.md"):
        match = _FRONTMATTER.match(path.read_text(encoding="utf-8"))
        if match is None:
            raise SystemExit(f"no frontmatter: {path}")
        meta = yaml.safe_load(match.group(1))

        if meta.get("doc_id") != doc_id:
            raise SystemExit(f"{path}: doc_id is {meta.get('doc_id')!r}, expected {doc_id!r}")
        title_line = str(meta["section"])
        number = title_line.split(maxsplit=1)[0]
        if not _DOTTED.match(number):
            raise SystemExit(
                f"{path}: section must start with a number like 2.1, got {title_line!r}"
            )
        sections.append(SectionFile(number, title_line, meta, match.group(2).strip()))

    return sorted(sections, key=lambda s: (_number_key(s.number), s.meta["version"]))


# --- docx table pinning -------------------------------------------------------

_TABLE = re.compile(r"<w:tbl>.*?</w:tbl>", re.DOTALL)
_ROW = re.compile(r"<w:tr(?:\s[^>]*)?>.*?</w:tr>", re.DOTALL)
_ROW_OPEN = re.compile(r"<w:tr(?:\s[^>]*)?>")
_TRPR = re.compile(r"<w:trPr>(.*?)</w:trPr>", re.DOTALL)
_PARA = re.compile(r"<w:p(?:\s[^>]*)?>.*?</w:p>", re.DOTALL)
_PARA_OPEN = re.compile(r"<w:p(?:\s[^>]*)?>")
_PPR = re.compile(r"<w:pPr>(.*?)</w:pPr>", re.DOTALL)
_PSTYLE = re.compile(r"<w:pStyle[^>]*/>")


def _row_props(row: str, *, header: bool) -> str:
    """cantSplit on every row; tblHeader on row 0 so a header repeats if it must."""
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
    out = table
    for index, row in enumerate(rows):
        fixed = _row_props(row, header=index == 0)
        if index < len(rows) - 1:
            fixed = _PARA.sub(lambda m: _keep_next(m.group(0)), fixed)
        out = out.replace(row, fixed, 1)
    return out


def pin_tables(docx: Path) -> int:
    """Rewrite a docx in place so no table splits across a page. Returns table count."""
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


# --- writing the outputs ------------------------------------------------------


def write_docx(target: Path, title: str, subtitle: str, sections: list[SectionFile]) -> int:
    """One Word file.  Each section becomes a real Heading 2.  Returns tables pinned."""
    numbers = [s.number for s in sections]
    repeated = sorted({n for n in numbers if numbers.count(n) > 1})
    if repeated:
        raise SystemExit(f"{target.name}: section numbers appear twice: {repeated}")

    parts = [f"% {title}\n% {ORG}\n% {subtitle}\n"]
    parts += [f"\n## {s.title_line}\n\n{s.body}\n" for s in sections]

    source = BUILD / f"{target.stem}.md.gen"
    source.write_text("".join(parts), encoding="utf-8")
    subprocess.run(
        ["pandoc", str(source), "--from", "markdown", "-o", str(target), "--toc"],
        check=True,
    )
    return pin_tables(target)


def write_manifest(
    target: Path, doc_id: str, title: str, docx_file: str, sections: list[SectionFile]
) -> None:
    """Document-level metadata, plus per-clause overrides only where they differ.

    A document management system carries one row of metadata per document, not
    per clause, so that is the shape ingestion is given.  Where a clause
    genuinely stands apart - substituted on its own date, or citing a different
    authority - the difference is written out as an override.  This function
    works those out by comparing sections; nobody maintains a list by hand.
    """
    first = sections[0].meta
    manifest: dict[str, Any] = {
        "doc_id": doc_id,
        "title": title,
        "file": docx_file,
        "department": first["department"],
        "sensitivity": first["sensitivity"],
        "acl_groups": list(first["acl_groups"] or []),
        "version": first["version"],
        "effective_from": _iso(first["effective_from"]),
        "effective_to": _iso(first["effective_to"]),
        "source_ref": first["source_ref"],
    }

    defaults = {key: manifest[key] for key in _PER_CLAUSE}
    overrides: dict[str, dict[str, Any]] = {}
    for section in sections:
        values = {
            "version": section.meta["version"],
            "effective_from": _iso(section.meta["effective_from"]),
            "effective_to": _iso(section.meta["effective_to"]),
            "source_ref": section.meta["source_ref"],
        }
        if values != defaults:
            overrides[section.number] = values

    if overrides:
        manifest["overrides"] = overrides

    target.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build() -> None:
    if shutil.which("pandoc") is None:
        raise SystemExit("pandoc is not on PATH - install it from https://pandoc.org")

    # Start clean: a removed section must not leave its old Word file behind.
    for folder in (DOCX, MANIFEST):
        shutil.rmtree(folder, ignore_errors=True)
    for folder in (BUILD, PDF, DOCX / "archive", MANIFEST / "archive"):
        folder.mkdir(parents=True, exist_ok=True)

    current_files: list[Path] = []

    for doc_id, title in TITLES.items():
        sections = read_sections(doc_id)
        current = [s for s in sections if s.meta["effective_to"] is None]
        superseded = [s for s in sections if s.meta["effective_to"] is not None]

        docx = DOCX / f"{doc_id}.docx"
        pinned = write_docx(docx, title, "Current version", current)
        write_manifest(MANIFEST / f"{doc_id}.json", doc_id, title, docx.name, current)
        current_files.append(docx)
        print(f"{doc_id}: {len(current)} sections, {pinned} tables pinned")

        for s in superseded:
            until = _iso(s.meta["effective_to"])
            stem = f"{doc_id}--{s.number}--until-{until}"
            archived = DOCX / "archive" / f"{stem}.docx"
            write_docx(archived, title, f"Superseded on {until}. Kept for reference.", [s])
            write_manifest(
                MANIFEST / "archive" / f"{stem}.json", doc_id, title, f"archive/{archived.name}", [s]
            )
            print(f"  archived {s.number} v{s.meta['version']} (until {until})")

    office = shutil.which("libreoffice") or shutil.which("soffice")
    if office is None:
        print("LibreOffice not found - PDFs skipped. Word files and manifests are complete.")
        return

    subprocess.run(
        [office, "--headless", "--convert-to", "pdf", "--outdir", str(PDF)]
        + [str(p) for p in current_files],
        check=True,
    )
    print(f"printed {len(current_files)} PDFs")


if __name__ == "__main__":
    build()