"""Any document Docling can open - Word, HTML or PDF - as RawDoc.

A thin adapter. It turns Docling's output into plain items and hands them to
build_structure, which holds every rule. Docling is imported only when a 
reader is first used, so importing this module never needs it: CI does not
install Docling, which pulls in PyTorch."""

from pathlib import Path
from typing import Any

from nbfc_ews.retrieval.read import RawDoc, ReaderError
from nbfc_ews.retrieval.structure import Item, ItemKind, build_structure

SUPPORTED = {".docx", ".html", ".htm", ".pdf"}

# Heading levels are real only where the format stores them as styles. A PDF
# has no styles - Docling reports every PDF heading as level 1 - so for PDFs
# no level is passed, and the numbering shape decides.
_REAL_LEVELS = {".docx", ".html", ".htm"}

# Labels with no content of their own: the letterhead, page furniture, the
# table of contents. Dropped before build_structure ever sees them.
_DROP = {"picture", "document_index", "page_header", "page_footer"}

_KIND: dict[str, ItemKind] = {
    "title": "title",
    "section_header": "heading",
    "text": "text",
    "paragraph": "text",
    "caption": "text",
    "formula": "text",
    "code": "text",
    "list_item": "list_item",
    "table": "table",
    "footnote": "footnote",
}

def _label(node: Any) -> str:
    label = getattr(node, "label", "")
    return str(getattr(label, "value", label))

def _items(doc: Any, real_levels: bool) -> list[Item]:
    """Docling's tree as a flat list of items, in reading order.
    
    A sentence with italic or bols in it arrives as a several pieces under one
    inline group. The pieces are gluded back into one sentence here, so a
    formatting change never becomes a paragraph break.
    """

    items: list[Item] = []
    pieces: list[str] = []
    pieces_parent: str | None = None

    def flush() -> None:
        nonlocal pieces, pieces_parent
        if pieces:
            items.append(Item("text", "".join(pieces)))
        pieces, pieces_parent = [], None

    for node, _depth in doc.iterate_items():
        label = _label(node)
        parent = node.parent.resolve(doc) if node.parent is not None else None
        inline_parent = node.parent.cref if parent is not None and _label(parent) == "inline" else None

        if inline_parent != pieces_parent:
            flush()

        if label in _DROP:
            continue
        kind = _KIND.get(label)
        if kind is None:
            continue

        if kind == "text" and inline_parent is not None:
            pieces.append(node.text)
            pieces_parent = inline_parent
        elif kind == "table":
            items.append(Item("table", node.export_to_markdown(doc=doc)))
        elif kind == "heading":
            level = getattr(node, "level", None) if real_levels else None
            items.append(Item("heading", node.text, level=level))
        elif kind == "list_item":
            items.append(Item("heading", node.text, marker=getattr(node, "marker", "") or ""))
        else:
            items.append(Item(kind, node.text))

    flush()
    return items

class DoclingReader:
    """Word, HTML or PDF in;" sections, title and parse quality out."""

    def __init__(self, *, ocr: bool = False) -> None:
        # OCR off by default: our documents are digital,OCR is a delibrate
        # choice for scanned ones, never a silent cost on every file.
        self._ocr = ocr
        self._converter: Any = None

    def _get_converter(self) -> Any:
        """Built once and reused - it loads layout models, which is slow."""
        if self._converter is None:
            from docling.datamodel.base_models import InputFormat
            from docling.datamodel.pipeline_options import PdfPipelineOptions
            from docling.document_converter import DocumentConverter, PdfFormatOption

            options = PdfPipelineOptions(do_ocr=self._ocr)
            self._converter = DocumentConverter(
                format_options = {InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
            )

        return self._converter

    def read(self, path: Path) -> RawDoc:
        suffix = path.suffix.lower()
        if suffix not in SUPPORTED:
            raise ReaderError(f"unsupported file type: {path.name}")
        try:
            doc = self._get_converter().convert(path).document
        except Exception as exc:
            raise ReaderError(f"could not read {path.name}: {exc}") from exc

        structure = build_structure(_items(doc, real_levels=suffix in _REAL_LEVELS))
        meta = {"title": structure.title, "reader": "docling", "quality": structure.quality}
        return RawDoc(path=path, meta=meta, sections=structure.sections)



