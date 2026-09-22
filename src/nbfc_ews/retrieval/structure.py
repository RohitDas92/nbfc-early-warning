"""Document structure from a flat list of parsed items - for any document.

No document types are named here.  Levels come from one of two places:

1. The file itself, when it has them.  Word and HTML mark headings as
   Heading 1, Heading 2... - exact, nothing to infer.
2. Otherwise, the shape of the numbering.  The first numbering style seen is
   level 1; a new style nested under it is one deeper; a style seen before
   returns to its level.  Chapter I > A. > 1. and 1. > 1.1 > 1.1.1 and
   1. > (a) > (i) all come out right without the code knowing which is which.

Bracketed items - (1), (a), (i) - are sub-clauses in almost every kind of
document, so they stay inside their parent: a proviso is never cut away from
the clause it qualifies.

This module never imports a parser.  A reader turns a parser's output into
Items; everything here can be tested with hand-written ones.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

from nbfc_ews.retrieval.read import Section

ItemKind = Literal["title", "heading", "text", "list_item", "table", "footnote"]

# Below this share of text inside numbered sections, a document is held for
# review rather than indexed: its citations would be unreliable.
MIN_NUMBERED_SHARE = 0.6


@dataclass(frozen=True)
class Item:
    """One block as a parser saw it, before any structure is imposed."""

    kind: ItemKind
    text: str
    level: int | None = None  # a real heading level, when the file has one
    marker: str = ""          # a list marker exactly as parsed: "18.", "(a)"


@dataclass(frozen=True)
class Enumerator:
    """The number at the start of a heading or list item, and its shape."""

    style: str   # the numbering shape, e.g. "dot-num", "paren-roman-lower"
    number: str  # the value alone: "18", "iv", "2.1", "Chapter II"
    rest: str    # the text after it

    @property
    def inline(self) -> bool:
        """Bracketed styles are sub-clauses: they stay inside their parent."""
        return self.style.startswith(("paren-", "close-"))


@dataclass(frozen=True)
class ParseQuality:
    numbered_share: float
    duplicate_numbers: tuple[str, ...]
    level_jumps: int

    @property
    def passed(self) -> bool:
        return (
            self.numbered_share >= MIN_NUMBERED_SHARE
            and not self.duplicate_numbers
            and self.level_jumps == 0
        )


@dataclass(frozen=True)
class Structure:
    title: str
    sections: tuple[Section, ...]
    quality: ParseQuality


# --- recognising numbering, by shape ------------------------------------------

_WORD = re.compile(
    r"^(chapter|part|section|article|schedule|annex|annexure|appendix)\s+"
    r"([ivxlcdm]+|\d+|[a-z])\b[\s.:\-\u2013]*(.*)$",
    re.IGNORECASE,
)
_DOTTED = re.compile(r"^(\d+(?:\.\d+)+)\.?\s+(.*)$")
_PAREN = re.compile(r"^\(([0-9]+|[A-Za-z]{1,6})\)\s*(.*)$")
_CLOSE = re.compile(r"^([0-9]+|[a-z]|[ivxlcdm]{2,6})\)\s+(.*)$")
_DOT = re.compile(r"^([0-9]+|[A-Za-z]\d{1,2}|[A-Za-z]|[ivxlcdm]{2,6}|[IVXLCDM]{2,6})\.(?:\s+(.*))?$")
_ROMAN = re.compile(r"^[ivxlcdm]+$", re.IGNORECASE)

# "3 [" at the start of an amended heading is a footnote reference, not text.
_FOOTNOTE_MARK = re.compile(r"(?<=\s)\d+\s*\[")


def _kind(token: str, form: str, last: dict[str, str]) -> str:
    """num, alpha or roman.  (i) after (h) is a letter; (i) on its own is Roman."""
    if token.isdigit():
        return "num"
    if any(ch.isdigit() for ch in token):
        return "alpha"  # C1, C2
    if len(token) == 1:
        case = "upper" if token.isupper() else "lower"
        previous = last.get(f"{form}-alpha-{case}")
        if previous is not None and previous.isalpha() and ord(token.lower()) == ord(previous[-1].lower()) + 1:
            return "alpha"
        return "roman" if token.lower() in "ivx" else "alpha"
    return "roman" if _ROMAN.match(token) else "alpha"


def parse_enumerator(line: str, last: dict[str, str]) -> Enumerator | None:
    """The numbering at the start of a line, or None.  `last` is read, never changed."""
    text = " ".join(line.split())

    if match := _WORD.match(text):
        word, value, rest = match.groups()
        value = value if value.isdigit() else value.upper()
        return Enumerator(f"word-{word.lower()}", f"{word.title()} {value}", rest)

    if match := _DOTTED.match(text):
        number, rest = match.groups()
        return Enumerator(f"dotted-{number.count('.') + 1}", number, rest)

    for form, pattern in (("paren", _PAREN), ("close", _CLOSE), ("dot", _DOT)):
        if match := pattern.match(text):
            token, rest = match.group(1), match.group(2) or ""
            kind = _kind(token, form, last)
            if kind == "num":
                style = f"{form}-num"
            else:
                letters = "".join(ch for ch in token if ch.isalpha())
                style = f"{form}-{kind}-{'upper' if letters.isupper() else 'lower'}"
            return Enumerator(style, token, rest)

    return None


def _clean_heading(text: str) -> str:
    text = _FOOTNOTE_MARK.sub("", " ".join(text.split()))
    return " ".join(text.replace("]", "").split())

_SENTENCE_END = (".", ";", ":", "?", "!")
_TITLE_MAX = 80


def _is_paragraph(text: str) -> bool:
    """A title is short and unpunctuated; anything longer is body text."""
    return text.endswith(_SENTENCE_END) or len(text) > _TITLE_MAX

# --- building the structure ---------------------------------------------------


@dataclass
class _Open:
    level: int
    number: str
    labels: tuple[str, ...]  # the heading chain shown for this section
    body: list[str] = field(default_factory=list)


class _Builder:
    def __init__(self, has_levels: bool) -> None:
        self.has_levels = has_levels
        self.title = ""
        self.sections: list[Section] = []
        self.footnotes: list[str] = []
        self.styles: list[str] = []             # numbering stack; index = level - 1
        self.last: dict[str, str] = {}          # last value seen per style
        self.chain: list[tuple[int, str]] = []  # open (level, label), outermost first
        self.seen: set[tuple[tuple[str, ...], str]] = set()
        self.duplicates: list[str] = []
        self.previous_heading_level: int | None = None
        self.level_jumps = 0
        self.numbered_chars = 0
        self.total_chars = 0
        self.current = _Open(level=1, number="", labels=())

    def add(self, item: Item) -> None:
        text = item.text.strip() if item.kind == "table" else " ".join(item.text.split())
        if not text and not item.marker:
            return
        if item.kind == "footnote":
            self.footnotes.append(text)
        elif item.kind == "title":
            if not self.title:
                self.title = text
        elif item.kind in ("text", "table"):
            self.current.body.append(text)
        elif item.kind == "list_item":
            self._list_item(item, text)
        else:
            self._heading(item, text)

    def _list_item(self, item: Item, text: str) -> None:
        line = f"{item.marker} {text}".strip()
        enum = parse_enumerator(line, self.last)
        if enum is not None:
            self.last[enum.style] = enum.number
        # With real heading levels, headings decide the structure and lists
        # stay in the body.  Without them, a numbered paragraph is a section.
        if enum is None or enum.inline or self.has_levels:
            self.current.body.append(line)
            return
        self._open(self._level_for(enum.style), enum.number, label="", first=line)

    def _heading(self, item: Item, text: str) -> None:
        label = _clean_heading(text)
        line = f"{item.marker} {label}".strip() if item.marker else label
        enum = parse_enumerator(line, self.last)
        if enum is not None:
            self.last[enum.style] = enum.number

        # A bracketed heading is a sub-clause: it belongs to the open section.
        if enum is not None and enum.inline:
            self.current.body.append(line)
            return

        # A Chapter/Part/Annex enumerator names a container, never a paragraph,
        # however long its title runs.
        structural = enum is not None and enum.style.startswith("word-")
        prose = not structural and _is_paragraph(enum.rest if enum is not None else label)

        if enum is None and prose:
            self.current.body.append(line)  # unnumbered prose: keep it with its clause
            return

        if item.level is not None:
            level = item.level
            if self.previous_heading_level is not None and level > self.previous_heading_level + 1:
                self.level_jumps += 1
            self.previous_heading_level = level
        elif enum is not None:
            level = self._level_for(enum.style)
        else:
            level = len(self.styles) + 1

        number = enum.number if enum is not None else ""
        self._open(level, number, label="" if prose else line, first=line if prose else None)

    def _level_for(self, style: str) -> int:
        """Seen before: back to its level.  New: one deeper than the deepest open."""
        if style in self.styles:
            index = self.styles.index(style)
            del self.styles[index + 1:]
        else:
            self.styles.append(style)
            index = len(self.styles) - 1
        return index + 1

    def _open(self, level: int, number: str, label: str, first: str | None) -> None:
        self._close()
        while self.chain and self.chain[-1][0] >= level:
            self.chain.pop()
        parent = tuple(lbl for _, lbl in self.chain if lbl)
        self.chain.append((level, label))

        if number:
            key = (parent, number)  # numbers are unique within their parent
            if key in self.seen:
                self.duplicates.append(number)
            self.seen.add(key)
            # a new numbered block restarts any (a), (i) counting beneath it
            for style in [s for s in self.last if s.startswith(("paren-", "close-"))]:
                del self.last[style]

        labels = tuple(lbl for _, lbl in self.chain if lbl)
        self.current = _Open(level, number, labels, [first] if first else [])

    def _close(self) -> None:
        body = "\n\n".join(self.current.body).strip()
        if not body:
            return  # a heading with nothing under it is context, not a section
        self.sections.append(
            Section(
                level=self.current.level,
                number=self.current.number,
                heading=" > ".join(self.current.labels),
                body=body,
            )
        )
        self.total_chars += len(body)
        if self.current.number:
            self.numbered_chars += len(body)

    def finish(self) -> Structure:
        self._close()
        self.current = _Open(level=1, number="", labels=())
        if self.footnotes:
            body = "\n\n".join(self.footnotes)
            self.sections.append(Section(level=1, number="", heading="Footnotes", body=body))
            self.total_chars += len(body)
        share = self.numbered_chars / self.total_chars if self.total_chars else 0.0
        quality = ParseQuality(round(share, 3), tuple(self.duplicates), self.level_jumps)
        return Structure(self.title, tuple(self.sections), quality)


def build_structure(items: Sequence[Item]) -> Structure:
    """Sections for any document, plus how well its structure was recovered."""
    has_levels = any(i.kind == "heading" and i.level is not None for i in items)
    builder = _Builder(has_levels)
    for item in items:
        builder.add(item)
    return builder.finish()