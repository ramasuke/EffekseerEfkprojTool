"""cereal JSON 方言: NanamiEngine が Windows 上で書き出す
``cereal::JSONOutputArchive`` (RapidJSON PrettyWriter, 4スペースインデント) の出力を
バイト単位で再現するリーダー/プリンタ。

設計メモ (コミット済みの ``*.enemyBehaviourData`` フィクスチャ、および
兄弟キーが重複するオブジェクトについては ``*.scene``/``*.prefab`` で検証済み):

* ファイルは UTF-8、**BOM なし**、**CRLF** 改行、**末尾改行なし**。
* インデント: 4スペース。``"key": value``。配列要素は1行に1つ。空の
  object/array は1行の ``{}`` / ``[]`` に畳む。
* 文字列エスケープは RapidJSON の既定に合わせる: ``" \\ \b \f \n \r \t`` と
  0x20 未満の制御文字 (``\\uXXXX`` として) のみ。それ以外 (非 ASCII 含む) はそのまま。
* 数値: RapidJSON は Grisu2 を使う。*通常は* 最短の往復表現だが、Python の
  ``repr`` が出さない余分な (異なる) 最下位桁をまれに1つ出力する。既存ファイルを
  バイト単位で往復させるため、ファイルからパースした数値はすべて
  **元の数値リテラル文字列** を保持する (:class:`Num`)。ツールキットが生成した数値は
  :func:`format_number` で描画する (``repr`` ベース、整数値なら ``.0`` を付加)。
* 一部のエンジン型 (例: ``Transform::children_``) はコレクションを、件数の後に
  **同じ NVP 名を繰り返した** 兄弟キーとしてシリアライズする。例:
  ``{"childCount": 3, "child": {...}, "child": {...}, "child": {...}}`` - JSON 文法上
  有効 (キーの一意性は必須ではない) で、cereal の RapidJSON ベースのアーカイブが
  まさにこの形で読み書きする。:class:`OrderedObj` はすべての出現を保持し、
  ``obj["key"] = value`` (明示的な単一キー変更) のときだけその場で重複を除く。
  パース (:func:`loads`) は決して重複除去しない - :meth:`OrderedObj.__init__` を参照。
"""

from __future__ import annotations

import json
from typing import Any, Iterable, Iterator


# ---------------------------------------------------------------------------
# 順序付きオブジェクト
# ---------------------------------------------------------------------------
class OrderedObj:
    """挿入順を保つ文字列キーのマッピング (JSON オブジェクト)。

    必要な範囲で dict のように振る舞う。順序を保ち、*重複キーも与えられたとおりに
    保持する* (JSON オブジェクトはメンバーペアのリストであって一意キーの集合ではない
    - モジュールの docstring を参照)。一括構築 (:func:`loads` から、または別の
    オブジェクトの ``.items()`` から) はすべてのペアを無条件に保持する。
    ``obj[key] = value`` (エディタ全体で使う単一キー変更) は利便性のため、
    従来どおり最初に一致したものをその場で置き換える。
    """

    __slots__ = ("_pairs",)

    def __init__(self, pairs: Iterable[tuple[str, Any]] | None = None) -> None:
        # 一括構築では決して重複除去しない - 元のオブジェクト (パースしたての
        # ファイルや別の OrderedObj の .items()) は正当に同じキーを複数回
        # 含みうる (モジュールの docstring を参照)。
        self._pairs: list[list] = [[k, v] for k, v in pairs] if pairs is not None else []

    # -- マッピングプロトコル -----------------------------------------------
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
        """``key`` に格納されたすべての値をファイル順で返す (空の場合もある)。"""
        return [v for k, v in self._pairs if k == key]

    def keys(self) -> list[str]:
        return [k for k, _ in self._pairs]

    def values(self) -> list[Any]:
        return [v for _, v in self._pairs]

    def items(self) -> list[tuple[str, Any]]:
        return [(k, v) for k, v in self._pairs]

    def append(self, key: str, value: Any) -> None:
        """ペアを無条件に追加する (意図的な重複を許す)。"""
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
# 数値
# ---------------------------------------------------------------------------
class Num:
    """パース元のリテラル文字列を覚えている JSON 数値。

    ``value`` は Python の ``int``/``float``。``is_int`` はリテラルに ``.`` や
    指数部がなかったかを記録する (cereal は ``0`` と ``0.0`` を区別する)。
    ``raw`` は元のトークンそのもので、合成した数値では ``None``。
    等価性は ``(is_int, value)`` で判定する - 文字列表現は意味に関係しない。
    """

    __slots__ = ("value", "is_int", "raw")

    def __init__(self, value: Any, is_int: bool, raw: str | None = None) -> None:
        self.value = int(value) if is_int else float(value)
        self.is_int = is_int
        self.raw = raw

    # -- コンストラクタ ---------------------------------------------------
    @staticmethod
    def of_int(value: int, raw: str | None = None) -> "Num":
        return Num(int(value), True, raw)

    @staticmethod
    def of_float(value: float, raw: str | None = None) -> "Num":
        return Num(float(value), False, raw)

    # -- 描画 ----------------------------------------------------------------
    def render(self) -> str:
        if self.raw is not None:
            return self.raw
        return format_number(self.value, self.is_int)

    # -- 等価性 ------------------------------------------------------------
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
    """合成した数値を cereal/RapidJSON と同じように描画する (ほぼ同等)。

    既存ファイルの数値は :class:`Num` でそのまま往復させる。これはツールキットが
    作る値 (位置、スカラーパラメータ、重みなど) 専用で、それらは ``repr`` が
    Grisu2 とまったく同じに描画する単純な小数である。
    """
    if is_int:
        return str(int(value))
    f = float(value)
    if f != f:  # NaN - cereal はこれを出力しないが、念のため防御する
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
# パース
# ---------------------------------------------------------------------------
def _pairs_hook(pairs: list[tuple[str, Any]]) -> OrderedObj:
    return OrderedObj(pairs)


def loads(text: str) -> Any:
    """cereal-JSON テキストをパースする。キー順、重複キー、数値リテラルを
    保持する。"""
    return json.loads(
        text,
        object_pairs_hook=_pairs_hook,
        parse_float=lambda s: Num.of_float(float(s), s),
        parse_int=lambda s: Num.of_int(int(s), s),
    )


# ---------------------------------------------------------------------------
# 出力
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
    """cereal-JSON テキストにシリアライズする (既定は LF、BOM なし、末尾改行なし)。"""
    out: list[str] = []
    _render(obj, 0, out)
    text = "".join(out)
    if newline != "\n":
        text = text.replace("\n", newline)
    return text


# ---------------------------------------------------------------------------
# ファイルヘルパー
# ---------------------------------------------------------------------------
def read_text(path) -> str:
    """cereal-JSON ファイルを LF 改行のテキストとして読む (CRLF は畳む)。"""
    raw = open(path, "rb").read()
    if raw[:3] == b"\xef\xbb\xbf":
        raw = raw[3:]
    return raw.decode("utf-8").replace("\r\n", "\n")


def to_file_bytes(text: str) -> bytes:
    """ツールキットの出力をエンジンと同じ形式でエンコードする: UTF-8、CRLF、BOM なし。"""
    return text.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8")


def write_file(path, obj: Any) -> None:
    open(path, "wb").write(to_file_bytes(dumps(obj)))


def self_check_roundtrip(path) -> None:
    """ファイルについて ``dumps(loads(text)) == text`` を検証する (書式の忠実性)。"""
    text = read_text(path)
    got = dumps(loads(text))
    if got != text:
        # 分かりやすいメッセージのため最初の相違箇所を探す
        n = min(len(got), len(text))
        i = next((j for j in range(n) if got[j] != text[j]), n)
        raise AssertionError(
            f"round-trip mismatch in {path} at offset {i}:\n"
            f"  expected ...{text[max(0, i - 40):i + 40]!r}\n"
            f"  got      ...{got[max(0, i - 40):i + 40]!r}"
        )
