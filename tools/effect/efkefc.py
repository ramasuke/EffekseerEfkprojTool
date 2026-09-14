"""Reader for the compiled ``.efkefc`` container (stdlib only).

Layout (Effekseer ``Dev/Editor/EffekseerCore/IO/EfkEfc.cs``, identical in
1.7.3 and 1.80.x): ``b"EFKE"`` + ``int32 0``, then chunks of ``4-byte tag`` +
``uint32 size`` + payload:

* ``INFO`` - ``int32 version`` + the asset list the runtime resolves relative
  to the ``.efkefc`` (see :func:`asset_paths`).
* ``EDIT`` - the editor's project XML, zlib-compressed in a key/value-table
  encoding (see :func:`edit_project`). This is how the editor stores the
  ``.efkproj`` it compiled - after *its* version migrations, so it is the
  ground truth for what that Effekseer version actually read.
* ``BIN_`` - the runtime binary: ``b"SKFE"`` + ``int32 version``. A runtime
  refuses any effect whose version is above its own ``SupportBinaryVersion``
  (``Effekseer.Effect.cpp``).
"""

from __future__ import annotations

import re
import struct
import zlib
from pathlib import Path

from . import assets
from .model import Elem

# Last ExporterVersion whose INFO chunk still holds plain string lists
# (Binary/Exporter.cs Ver1600); every later one writes a typed dependency list.
_INFO_STRING_LISTS_MAX_VERSION = 1610
_ASSET_EXT_RE = re.compile(r"[^\x00]+?\.(?:" + "|".join(assets.ASSET_EXTS) + ")", re.IGNORECASE)


class EfkefcError(ValueError):
    pass


def read_chunks(data: bytes) -> dict[str, bytes]:
    """``{tag: payload}`` for every chunk (first occurrence wins)."""
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
    """The runtime binary version (``BIN_`` chunk's ``SKFE`` header)."""
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
    """Every asset path (textures, models, sounds, materials, curves) in the
    ``INFO`` chunk, in chunk order; raises :class:`EfkefcError` when the chunk
    doesn't parse cleanly to its end.

    Up to version 1610 the chunk is string lists (``int32 count`` + strings);
    later versions (1.7.x = 1710, 1.80.x = 1810) write one dependency list
    (``int32 count`` + ``int32 type``, ``int32 flags``, string). Strings are
    ``int32 length`` + UTF-16LE chars incl. NUL.
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
                off += 8  # file type, flags
                s, off = _read_utf16(chunk, off)
                paths.append(s)
            if off != len(chunk):
                raise ValueError("trailing bytes after the dependency list")
    except (ValueError, struct.error) as e:
        raise EfkefcError(f"INFO chunk (version {version}) doesn't parse: {e}") from e
    return paths


def asset_paths(data: bytes) -> list[str]:
    """:func:`parse_asset_paths`, falling back to scanning the INFO chunk's
    UTF-16 text for asset-looking paths when it doesn't parse (so an
    unfamiliar layout degrades to a best-effort list rather than an error)."""
    try:
        return parse_asset_paths(data)
    except EfkefcError:
        text = _chunk(data, "INFO")[4:].decode("utf-16-le", errors="ignore")
        return [m.group(0).strip() for m in _ASSET_EXT_RE.finditer(text)]


def edit_project(data: bytes) -> Elem:
    """The ``<EffekseerProject>`` tree stored in the ``EDIT`` chunk
    (``EfkEfcXml.Decompress``): zlib, then an int16 key table and an int16
    value table (each ``int16 count`` + ``uint16 length``/UTF-8/``int16 id``),
    then the element tree (``int16 count`` + per element ``int16 key``,
    ``int32 has-value`` [+ ``int16 value``], ``int32 has-children`` [+ subtree]).
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
