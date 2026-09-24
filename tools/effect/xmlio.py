"""``.efkproj`` の XML コーデック - バイト単位で往復一致、標準ライブラリのみ。

ファイルの規則 (手作業で作られた実サンプル 14 個に対して ``xxd`` で確認):
UTF-8 **BOM 付き**、**CRLF** 改行、``<?xml version="1.0"
encoding="utf-8"?>`` 宣言、2 スペースのインデント、属性は一切無し、
空のコンテナは ``<Children />`` と自己終了、``</EffekseerProject>`` の後に
末尾改行無し。

解析では元の空白/書式をすべて捨てる (どのみち expat は XML 仕様どおり文字データ中の
CRLF を LF に正規化するし、この形式ではタグ間のインデント空白は意味のある内容で
ない - 各要素は純粋なテキストリーフか純粋なコンテナのどちらかで、混在しない)。
ライターは正規の書式を一から作り直す。Effekseer 自身のエディタが出力したファイルなら
``serialize(parse(text)) == text`` が成り立ち、それがこのモジュールが保証するための
往復の忠実性 (``tools/effect/selftest.py`` 参照)。
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
# ファイル用ヘルパー
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
    """``serialize(parse(text)) == text`` を確認する (書式の忠実性)。"""
    text = read_text(path)
    got = serialize(parse(text))
    if got != text:
        n = min(len(got), len(text))
        i = next((j for j in range(n) if got[j] != text[j]), n)
        raise AssertionError(
            f"round-trip differs at offset {i}: "
            f"exp {text[max(0, i - 40):i + 40]!r} got {got[max(0, i - 40):i + 40]!r}"
        )
