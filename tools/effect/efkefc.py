"""コンパイル済み ``.efkefc`` コンテナのリーダー (標準ライブラリのみ)。

レイアウト (Effekseer ``Dev/Editor/EffekseerCore/IO/EfkEfc.cs``。1.7.3 と
1.80.x で同一): ``b"EFKE"`` + ``int32 0``、その後に ``4 バイトのタグ`` +
``uint32 size`` + ペイロードのチャンクが続く:

* ``INFO`` - ``int32 version`` + ランタイムが ``.efkefc`` からの相対で解決する
  アセットリスト (:func:`asset_paths` 参照)。
* ``EDIT`` - エディタのプロジェクト XML。キー/値テーブル方式でエンコードして
  zlib 圧縮したもの (:func:`edit_project` 参照)。エディタはコンパイルした
  ``.efkproj`` をこの形で保存する。*そのエディタの* バージョンマイグレーション後の
  ものなので、その Effekseer バージョンが実際に何を読んだかの正解になる。
* ``BIN_`` - ランタイム用バイナリ: ``b"SKFE"`` + ``int32 version``。ランタイムは
  自身の ``SupportBinaryVersion`` より新しいバージョンのエフェクトを拒否する
  (``Effekseer.Effect.cpp``)。
"""

from __future__ import annotations

import re
import struct
import zlib
from pathlib import Path

from . import assets
from .model import Elem

# INFO チャンクがまだ素の文字列リストだった最後の ExporterVersion
# (Binary/Exporter.cs Ver1600)。それ以降はすべて型付きの依存リストを書く。
_INFO_STRING_LISTS_MAX_VERSION = 1610
_ASSET_EXT_RE = re.compile(r"[^\x00]+?\.(?:" + "|".join(assets.ASSET_EXTS) + ")", re.IGNORECASE)


class EfkefcError(ValueError):
    pass


def read_chunks(data: bytes) -> dict[str, bytes]:
    """全チャンクの ``{tag: payload}`` (同じタグは最初のものを採用)。"""
    if data[:4] != b"EFKE" or len(data) < 8:
        raise EfkefcError("not a .efkefc (no EFKE header)")
    chunks: dict[str, bytes] = {}
    off = 8
    while off + 8 <= len(data):
        tag = data[off:off + 4].decode("latin-1")
        size = struct.unpack_from("<I", data, off + 4)[0]
        off += 8
        if off + size > len(data):
            raise EfkefcError(f"chunk {tag!r} runs past the end of the file")
        chunks.setdefault(tag, data[off:off + size])
        off += size
    return chunks


def _chunk(data: bytes, tag: str) -> bytes:
    chunk = read_chunks(data).get(tag)
    if chunk is None:
        raise EfkefcError(f"no {tag} chunk")
    return chunk


def info_version(data: bytes) -> int:
    info = _chunk(data, "INFO")
    if len(info) < 4:
        raise EfkefcError("INFO chunk too short")
    return struct.unpack_from("<i", info, 0)[0]


def bin_version(data: bytes) -> int:
    """ランタイム用バイナリのバージョン (``BIN_`` チャンクの ``SKFE`` ヘッダ)。"""
    body = _chunk(data, "BIN_")
    if body[:4] != b"SKFE" or len(body) < 8:
        raise EfkefcError("BIN_ chunk has no SKFE header")
    return struct.unpack_from("<i", body, 4)[0]


def _read_utf16(chunk: bytes, off: int) -> tuple[str, int]:
    n = struct.unpack_from("<i", chunk, off)[0]
    off += 4
    if not 0 <= n <= 4096 or off + n * 2 > len(chunk):
        raise ValueError("implausible string length")
    return chunk[off:off + n * 2].decode("utf-16-le").rstrip("\x00"), off + n * 2


def parse_asset_paths(data: bytes) -> list[str]:
    """``INFO`` チャンク内の全アセットパス (テクスチャ、モデル、サウンド、マテリアル、
    カーブ) をチャンク内の順で返す。チャンクが末尾まできれいに解析できなければ
    :class:`EfkefcError` を投げる。

    バージョン 1610 まではチャンクが文字列リスト (``int32 count`` + 文字列) で、
    それ以降 (1.7.x = 1710、1.80.x = 1810) は依存リストを 1 つ書く
    (``int32 count`` + ``int32 type``、``int32 flags``、文字列)。文字列は
    ``int32 length`` + NUL を含む UTF-16LE 文字。
    """
    chunk = _chunk(data, "INFO")
    if len(chunk) < 4:
        raise EfkefcError("INFO chunk too short")
    version = struct.unpack_from("<i", chunk, 0)[0]
    paths: list[str] = []
    off = 4
    try:
        if version <= _INFO_STRING_LISTS_MAX_VERSION:
            while off < len(chunk):
                count = struct.unpack_from("<i", chunk, off)[0]
                off += 4
                if not 0 <= count <= 4096:
                    raise ValueError("implausible list count")
                for _ in range(count):
                    s, off = _read_utf16(chunk, off)
                    paths.append(s)
        else:
            count = struct.unpack_from("<i", chunk, off)[0]
            off += 4
            if not 0 <= count <= 4096:
                raise ValueError("implausible dependency count")
            for _ in range(count):
                off += 8  # ファイル種別、フラグ
                s, off = _read_utf16(chunk, off)
                paths.append(s)
            if off != len(chunk):
                raise ValueError("trailing bytes after the dependency list")
    except (ValueError, struct.error) as e:
        raise EfkefcError(f"INFO chunk (version {version}) doesn't parse: {e}") from e
    return paths


def asset_paths(data: bytes) -> list[str]:
    """:func:`parse_asset_paths`。解析できなければ INFO チャンクの UTF-16 テキストから
    アセットらしいパスを拾う方式にフォールバックする (見慣れないレイアウトでも
    エラーにせず、できる範囲のリストに落とす)。"""
    try:
        return parse_asset_paths(data)
    except EfkefcError:
        text = _chunk(data, "INFO")[4:].decode("utf-16-le", errors="ignore")
        return [m.group(0).strip() for m in _ASSET_EXT_RE.finditer(text)]


def edit_project(data: bytes) -> Elem:
    """``EDIT`` チャンクに保存された ``<EffekseerProject>`` ツリー
    (``EfkEfcXml.Decompress``): zlib 展開、次に int16 のキーテーブルと int16 の
    値テーブル (それぞれ ``int16 count`` + ``uint16 length``/UTF-8/``int16 id``)、
    その後に要素ツリー (``int16 count`` + 要素ごとに ``int16 key``、
    ``int32 has-value`` [+ ``int16 value``]、``int32 has-children`` [+ サブツリー])。
    """
    try:
        raw = zlib.decompress(_chunk(data, "EDIT"))
    except zlib.error as e:
        raise EfkefcError(f"EDIT chunk is not zlib data: {e}") from e
    off = 0

    def i16() -> int:
        nonlocal off
        v = struct.unpack_from("<h", raw, off)[0]
        off += 2
        return v

    def flag() -> bool:
        nonlocal off
        v = struct.unpack_from("<i", raw, off)[0]
        off += 4
        return v > 0

    def table() -> dict[int, str]:
        nonlocal off
        out: dict[int, str] = {}
        for _ in range(i16()):
            n = struct.unpack_from("<H", raw, off)[0]
            off += 2
            s = raw[off:off + n].decode("utf-8")
            off += n
            out[i16()] = s
        return out

    try:
        keys = table()
        values = table()

        def elements() -> list[Elem]:
            out = []
            for _ in range(i16()):
                e = Elem(keys[i16()])
                if flag():
                    e.text = values[i16()]
                if flag():
                    e.children = elements()
                out.append(e)
            return out

        top = elements()
    except (KeyError, struct.error, UnicodeDecodeError) as e:
        raise EfkefcError(f"EDIT chunk is malformed: {e}") from e
    if len(top) != 1:
        raise EfkefcError(f"EDIT chunk holds {len(top)} top-level elements, expected 1")
    return top[0]


def read(path) -> bytes:
    return Path(path).read_bytes()
