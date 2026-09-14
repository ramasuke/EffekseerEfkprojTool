"""``.efkproj`` XML codec - byte-exact round trip, stdlib only.

File convention (verified against 14 real, hand-authored samples with ``xxd``):
UTF-8 **with BOM**, **CRLF** line endings, ``<?xml version="1.0"
encoding="utf-8"?>`` declaration, 2-space indent, zero attributes anywhere,
empty containers self-close as ``<Children />``, no trailing newline after
``</EffekseerProject>``.

Parsing discards all original whitespace/formatting (expat normalizes
CRLF->LF in character data per the XML spec anyway, and inter-tag indentation
whitespace is not meaningful content in this format - every element is either
a pure text leaf or a pure container, never mixed). The writer regenerates
canonical formatting from scratch. ``serialize(parse(text)) == text`` holds
for any file Effekseer's own editor produced, which is the round-trip
fidelity this module exists to guarantee (see ``tools/effect/selftest.py``).
"""

from __future__ import annotations

import xml.parsers.expat
from pathlib import Path

from .model import Elem

_BOM = b"\xef\xbb\xbf"
_DECL = '<?xml version="1.0" encoding="utf-8"?>'


def parse(text: str) -> Elem:
    stack: list[Elem] = []
    buf: list[str] = []
    root: list[Elem] = []

    def start(tag: str, _attrs: dict) -> None:
        e = Elem(tag)
        if stack:
            stack[-1].children.append(e)
        else:
            root.append(e)
        stack.append(e)
        buf.append("")

    def end(_tag: str) -> None:
        text_piece = buf.pop()
        e = stack.pop()
        if not e.children:
            e.text = text_piece

    def chardata(data: str) -> None:
        buf[-1] += data

    p = xml.parsers.expat.ParserCreate("utf-8")
    p.StartElementHandler = start
    p.EndElementHandler = end
    p.CharacterDataHandler = chardata
    p.Parse(text, True)

    if len(root) != 1:
        raise ValueError(f"expected exactly one root element, found {len(root)}")
    return root[0]


def serialize(root: Elem) -> str:
    lines = [_DECL]
    _write_elem(root, 0, lines)
    return "\r\n".join(lines)


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _write_elem(e: Elem, depth: int, out: list[str]) -> None:
    pad = "  " * depth
    if not e.children:
        text = e.text or ""
        if text == "":
            out.append(f"{pad}<{e.tag} />")
        else:
            out.append(f"{pad}<{e.tag}>{_escape(text)}</{e.tag}>")
        return
    out.append(f"{pad}<{e.tag}>")
    for c in e.children:
        _write_elem(c, depth + 1, out)
    out.append(f"{pad}</{e.tag}>")


# ---------------------------------------------------------------------------
# file helpers
def read_text(path) -> str:
    raw = Path(path).read_bytes()
    if raw[:3] == _BOM:
        raw = raw[3:]
    return raw.decode("utf-8")


def read(path) -> Elem:
    return parse(read_text(path))


def to_file_bytes(text: str) -> bytes:
    return _BOM + text.encode("utf-8")


def write(path, root: Elem) -> None:
    Path(path).write_bytes(to_file_bytes(serialize(root)))


def self_check_roundtrip(path) -> None:
    """Assert ``serialize(parse(text)) == text`` (formatting fidelity)."""
    text = read_text(path)
    got = serialize(parse(text))
    if got != text:
        n = min(len(got), len(text))
        i = next((j for j in range(n) if got[j] != text[j]), n)
        raise AssertionError(
            f"round-trip differs at offset {i}: "
            f"exp {text[max(0, i - 40):i + 40]!r} got {got[max(0, i - 40):i + 40]!r}"
        )
