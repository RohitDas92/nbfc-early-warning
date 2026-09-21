"""Files to structured documents.

A reader only extracts. It never validates, never splits, never embeds - so
adding a PDFReader later changes nothing downstream"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import yaml

_FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n(.*)\Z", re.DOTALL)
_HEADING = re.compile(r"^(#{2,6})\s+(.*?)\s*$", re.MULTILINE)

class ReaderError(Exception):
    """The file could not be read as a policy document."""

@dataclass(frozen=True)
class Section:
    """One headed part of a document body."""

    level: int
    number: str
    heading: str
    body: str


@dataclass(frozen=True)
class RawDoc:
    """A document as it came off disk. Nothing validated, nothing inferred."""

    path: Path
    meta: dict[str, Any]
    sections: tuple[Section, ...]

class Reader(Protocol):
    """Anything that can turn a file into a RawDoc."""

    def read(self, path: Path) -> RawDoc: ...

class MarkdownReader:
    """YAML frontmatter, then a body optionally split by ##headings."""

    def read(self, path:Path) -> RawDoc:
        text = path.read_text(encoding="utf-8")

        match = _FRONTMATTER.match(text)
        if match is None:
            raise ReaderError(f"no YAML frontmatter: {path}")

        try:
            meta = yaml.safe_load(match.group(1))
        except yaml.YAMLError as exc:
            raise ReaderError(f" bad frontmatter in {path}: {exc}") from exc

        if not isinstance(meta, dict):
            raise ReaderError(f"frontmatter is not a mapping: {path}")

        return RawDoc(path=path, meta=meta, sections=self._sections(match.group(2)))

    def _sections(self, body: str) -> tuple[Section, ...]:
        headings = list(_HEADING.finditer(body))

        #No heading: the whole body is one section, and the frontmatter
        # carries its name. That is the normal shape for our corpus.

        if not headings:
            return (Section(level=2, number="", heading="", body=body.strip()),)

        sections: list[Section] = []

        # Text before the first heading beloangs to no heading, but must not be
        # lost - a preambleis still policy.

        preamble = body[: headings[0].start()].strip()
        if preamble:
            sections.append(Section(level=2, number="", heading="", body=preamble))

        for index, heading in enumerate(headings):
            start = heading.end()
            end = headings[index + 1].start() if index + 1 < len(headings) else len(body)
            sections.append(
                Section(
                    level=len(heading.group(1)),
                    number="",
                    heading=heading.group(2),
                    body=body[start:end].strip(),
                )
            ) 

        return tuple(sections)