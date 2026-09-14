"""cereal JSON dialect: a reader/printer that byte-reproduces the output of
``cereal::JSONOutputArchive`` (RapidJSON PrettyWriter, 4-space indent) as written
by NanamiEngine on Windows.

Design notes (verified against the committed ``*.enemyBehaviourData`` fixtures,
and - for repeated-sibling-key objects - against ``*.scene``/``*.prefab``):

* Files are UTF-8, **no BOM**, **CRLF** line endings, **no trailing newline**.
* Indent: 4 spaces. ``"key": value``. One array element per line. Empty
  object/array collapse to ``{}`` / ``[]`` on one line.
* String escaping matches RapidJSON's default: only ``" \\ \b \f \n \r \t`` and
  control chars < 0x20 (as ``\\uXXXX``); everything else (incl. non-ASCII) verbatim.
* Numbers: RapidJSON uses Grisu2, which is *usually* shortest-round-trip but
  occasionally emits one extra (differing) least-significant digit that Python's
  ``repr`` does not. To round-trip existing files byte-for-byte we therefore keep
  the **original numeric literal text** for every number parsed from a file
  (:class:`Num`). Numbers synthesised by the toolkit are rendered with
  :func:`format_number` (``repr``-based, ``.0`` appended when integral).
* Some engine types (e.g. ``Transform::children_``) serialise a collection as a
  count followed by the **same NVP name repeated** as sibling keys, e.g.
  ``{"childCount": 3, "child": {...}, "child": {...}, "child": {...}}`` - valid
  per the JSON grammar (key uniqueness is not required) and exactly what cereal's
  RapidJSON-backed archives read/write. :class:`OrderedObj` preserves every
  occurrence; only ``obj["key"] = value`` (explicit single-key mutation) dedups
  in place. Parsing (:func:`loads`) never dedups - see :meth:`OrderedObj.__init__`.
"""

from __future__ import annotations

import json
from typing import Any, Iterable, Iterator


# ---------------------------------------------------------------------------
# ordered object
# ---------------------------------------------------------------------------
class OrderedObj:
    """An insertion-ordered string-keyed mapping (JSON object).

    Behaves enough like a dict for our needs; preserves order and *preserves
    duplicate keys exactly as given* (a JSON object is a list of member pairs,
    not a set of unique keys - see module docstring). Bulk construction (from
    :func:`loads`, or from another object's ``.items()``) keeps every pair
    unconditionally. ``obj[key] = value`` (single-key mutation, used throughout
    the editors) still replaces the first match in place for convenience.
    """

    __slots__ = ("_pairs",)

    def __init__(self, pairs: Iterable[tuple[str, Any]] | None = None) -> None:
        # Bulk construction must never dedup - a source object (a freshly
        # parsed file, or another OrderedObj's .items()) may legitimately
        # contain the same key more than once (see module docstring).
        self._pairs: list[list] = [[k, v] for k, v in pairs] if pairs is not None else []

    # -- mapping protocol ---------------------------------------------------
    def __getitem__(self, key: str) -> Any:
        for k, v in self._pairs:
            if k == key:
                return v
        raise KeyError(key)

    def __setitem__(self, key: str, value: Any) -> None:
        for pair in self._pairs:
            if pair[0] == key:
                pair[1] = value
                return
        self._pairs.append([key, value])

    def __contains__(self, key: object) -> bool:
        return any(k == key for k, _ in self._pairs)

    def __len__(self) -> int:
        return len(self._pairs)

    def __iter__(self) -> Iterator[str]:
        return (k for k, _ in self._pairs)

    def get(self, key: str, default: Any = None) -> Any:
        for k, v in self._pairs:
            if k == key:
                return v
        return default

    def values_for(self, key: str) -> list[Any]:
        """Every value stored under ``key``, in file order (may be empty)."""
        return [v for k, v in self._pairs if k == key]

    def keys(self) -> list[str]:
        return [k for k, _ in self._pairs]

    def values(self) -> list[Any]:
        return [v for _, v in self._pairs]

    def items(self) -> list[tuple[str, Any]]:
        return [(k, v) for k, v in self._pairs]

    def append(self, key: str, value: Any) -> None:
        """Append a pair unconditionally (allows intentional duplicates)."""
        self._pairs.append([key, value])

    def insert(self, index: int, key: str, value: Any) -> None:
        self._pairs.insert(index, [key, value])

    def pop(self, key: str, *default: Any) -> Any:
        for i, (k, _) in enumerate(self._pairs):
            if k == key:
                return self._pairs.pop(i)[1]
        if default:
            return default[0]
        raise KeyError(key)

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"OrderedObj({self._pairs!r})"


# ---------------------------------------------------------------------------
# numbers
# ---------------------------------------------------------------------------
class Num:
    """A JSON number that remembers the literal text it was parsed from.

    ``value`` is the Python ``int``/``float``. ``is_int`` records whether the
    literal had no ``.`` / exponent (cereal distinguishes ``0`` from ``0.0``).
    ``raw`` is the verbatim source token, or ``None`` for synthesised numbers.
    Equality is by ``(is_int, value)`` - text form is irrelevant to meaning.
    """

    __slots__ = ("value", "is_int", "raw")

    def __init__(self, value: Any, is_int: bool, raw: str | None = None) -> None:
        self.value = int(value) if is_int else float(value)
        self.is_int = is_int
        self.raw = raw

    # -- constructors -----------------------------------------------------
    @staticmethod
    def of_int(value: int, raw: str | None = None) -> "Num":
        return Num(int(value), True, raw)

    @staticmethod
    def of_float(value: float, raw: str | None = None) -> "Num":
        return Num(float(value), False, raw)

    # -- rendering ------------------------------------------------------------
    def render(self) -> str:
        if self.raw is not None:
            return self.raw
        return format_number(self.value, self.is_int)

    # -- equality ----------------------------------------------------------
    def __eq__(self, other: object) -> bool:
        if isinstance(other, Num):
            return self.is_int == other.is_int and self.value == other.value
        if isinstance(other, bool):
            return False
        if isinstance(other, int):
            return self.is_int and self.value == other
        if isinstance(other, float):
            return (not self.is_int) and self.value == other
        return NotImplemented

    def __hash__(self) -> int:
        return hash((self.is_int, self.value))

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"Num({self.render()})"


def format_number(value: Any, is_int: bool) -> str:
    """Render a synthesised number the way cereal/RapidJSON would (close enough).

    Existing-file numbers are round-tripped verbatim via :class:`Num`; this is
    only for values the toolkit creates (positions, scalar params, weights...),
    which are simple decimals that ``repr`` renders exactly as Grisu2 does.
    """
    if is_int:
        return str(int(value))
    f = float(value)
    if f != f:  # NaN - cereal would not emit this; guard anyway
        raise ValueError("cannot serialise NaN")
    r = repr(f)
    if "e" in r or "E" in r:
        mant, _, exp = r.replace("E", "e").partition("e")
        if "." not in mant:
            mant += ".0"
        exp_i = int(exp)
        return f"{mant}e{exp_i:+03d}"
    if "." not in r:
        r += ".0"
    return r


# ---------------------------------------------------------------------------
# parsing
# ---------------------------------------------------------------------------
def _pairs_hook(pairs: list[tuple[str, Any]]) -> OrderedObj:
    return OrderedObj(pairs)


def loads(text: str) -> Any:
    """Parse cereal-JSON text, preserving key order, duplicate keys, and
    numeric literals."""
    return json.loads(
        text,
        object_pairs_hook=_pairs_hook,
        parse_float=lambda s: Num.of_float(float(s), s),
        parse_int=lambda s: Num.of_int(int(s), s),
    )


# ---------------------------------------------------------------------------
# printing
# ---------------------------------------------------------------------------
_ESCAPES = {
    '"': '\\"',
    "\\": "\\\\",
    "\b": "\\b",
    "\f": "\\f",
    "\n": "\\n",
    "\r": "\\r",
    "\t": "\\t",
}


def _escape_string(s: str) -> str:
    out = ['"']
    for ch in s:
        esc = _ESCAPES.get(ch)
        if esc is not None:
            out.append(esc)
        elif ord(ch) < 0x20:
            out.append(f"\\u{ord(ch):04x}")
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def _render(value: Any, indent: int, out: list[str]) -> None:
    pad = "    " * indent
    child_pad = "    " * (indent + 1)

    if isinstance(value, OrderedObj):
        if len(value) == 0:
            out.append("{}")
            return
        out.append("{\n")
        items = value.items()
        for i, (k, v) in enumerate(items):
            out.append(child_pad)
            out.append(_escape_string(k))
            out.append(": ")
            _render(v, indent + 1, out)
            out.append(",\n" if i < len(items) - 1 else "\n")
        out.append(pad + "}")
        return

    if isinstance(value, list):
        if len(value) == 0:
            out.append("[]")
            return
        out.append("[\n")
        for i, v in enumerate(value):
            out.append(child_pad)
            _render(v, indent + 1, out)
            out.append(",\n" if i < len(value) - 1 else "\n")
        out.append(pad + "]")
        return

    if isinstance(value, bool):
        out.append("true" if value else "false")
        return
    if value is None:
        out.append("null")
        return
    if isinstance(value, Num):
        out.append(value.render())
        return
    if isinstance(value, int):
        out.append(str(value))
        return
    if isinstance(value, float):
        out.append(format_number(value, False))
        return
    if isinstance(value, str):
        out.append(_escape_string(value))
        return
    raise TypeError(f"cannot serialise {type(value).__name__}: {value!r}")


def dumps(obj: Any, newline: str = "\n") -> str:
    """Serialise to cereal-JSON text (LF by default; no BOM, no trailing newline)."""
    out: list[str] = []
    _render(obj, 0, out)
    text = "".join(out)
    if newline != "\n":
        text = text.replace("\n", newline)
    return text


# ---------------------------------------------------------------------------
# file helpers
# ---------------------------------------------------------------------------
def read_text(path) -> str:
    """Read a cereal-JSON file as text with LF newlines (CRLF collapsed)."""
    raw = open(path, "rb").read()
    if raw[:3] == b"\xef\xbb\xbf":
        raw = raw[3:]
    return raw.decode("utf-8").replace("\r\n", "\n")


def to_file_bytes(text: str) -> bytes:
    """Encode toolkit output the way the engine writes it: UTF-8, CRLF, no BOM."""
    return text.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8")


def write_file(path, obj: Any) -> None:
    open(path, "wb").write(to_file_bytes(dumps(obj)))


def self_check_roundtrip(path) -> None:
    """Assert ``dumps(loads(text)) == text`` for a file (formatting fidelity)."""
    text = read_text(path)
    got = dumps(loads(text))
    if got != text:
        # find first divergence for a useful message
        n = min(len(got), len(text))
        i = next((j for j in range(n) if got[j] != text[j]), n)
        raise AssertionError(
            f"round-trip mismatch in {path} at offset {i}:\n"
            f"  expected ...{text[max(0, i - 40):i + 40]!r}\n"
            f"  got      ...{got[max(0, i - 40):i + 40]!r}"
        )
