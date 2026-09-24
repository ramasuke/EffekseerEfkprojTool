"""Effekseer のバージョンの扱い: ツールキットがどのエディタ/CUI を対象にするか、
それによって読み書きする ``.efkproj`` の何が変わるか。

対応ファミリー (Windows 版ツールのある全リリースを確認済み - ``README.md`` 参照):
1.5x (1.50RC1-1.51)、1.6x (1.60-1.62e)、1.7x (1.70-1.7.3.0)、
1.80.x (1.80.0-1.80.7)。同じファミリー内の全リリースは列挙の値域が同一
(各 ``EffekseerCore.dll`` からリフレクションで読み取り) で、同じバイナリバージョンを
書くので、:class:`Profile` はファミリーごとに 1 つ。

形式を決めるものは 2 つあり、混同してはいけない:

* **設定された Effekseer バージョン** (``effect_config.json`` の ``effekseer.version``、
  ``$EFFEKSEER_VERSION``、``--effekseer-version``) は :class:`Profile` を選ぶ:
  実行する CUI、エディタが受け付ける列挙の値域 (``enums.py`` 参照)、CUI が出力
  すべきバイナリバージョン。
* **ファイル自身の ``<ToolVersion>``** は Effekseer がそれをどう *読み込む* かを
  決める。どのエディタもバージョンマイグレーション (``Core.LoadFromXml`` +
  ``Utils/ProjectVersionUpdater.cs``) は各マイグレーションのしきい値より古い
  ファイルにしか実行しない。``presets.py`` は最も古い形 (元にした実サンプルが
  使っている形) を作るので、それが正しく読まれるのは全マイグレーションが走るほど
  古いファイルだけ - だから ``new-project`` は常に :data:`LEGACY_TOOL_VERSION` を
  書く。新しいファイルではそのフィールドは黙って無視され、逆 (古いファイルに
  マイグレーション後の「ネイティブ」フィールド) はマイグレーションで上書きされる。
  :data:`MIGRATIONS` はしきい値ごとに両側を列挙し、下のガードがどちらの食い違いも
  拒否する。各形を 1.80.7 の CUI で複数の ToolVersion でコンパイルし、``EDIT``
  チャンクをデコードして確認した (``selftest`` のステージ 11)。エディタは自分より
  新しい ``ToolVersion`` も拒否し、"Version Error" を表示しつつ 0 で終了する。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .model import Elem

FALLBACK_VERSION = "1.7.3.0"
# presets.py の元になった AndrewFM01 サンプルの 1.00 以前の ToolVersion:
# 解析できないので、どのエディタ (1.50RC1 ... 1.80.7) も全マイグレーションを実行する。
LEGACY_TOOL_VERSION = "0.7CTP1"


def _parse_uint(text: str) -> int | None:
    """既定の ``NumberStyles.Integer`` での ``uint.TryParse``。"""
    m = re.fullmatch(r"\s*\+?(\d+)\s*", text)
    if m is None:
        return None
    value = int(m.group(1))
    return value if value <= 0xFFFFFFFF else None


def parse_tool_version(text: str) -> int:
    """Effekseer の ``Core.ParseVersion`` (1.80.7 ``Core.cs``) の移植: エディタの
    ``ToolVersion`` 比較すべてが使う数値。
    ``"1.80"`` -> 180030、``"1.80β2"`` -> 180012、``"1.7.3.0"`` -> 173030、
    ``"0.7CTP1"`` -> 30 (解析不能なので全マイグレーションが走る)。
    """
    minor = 30
    for key, base in (("α", 0), ("β", 10), ("RC", 20)):
        if key in text:
            parts = text.split(key)
            minor = base + (_parse_uint(parts[1]) or 0) if len(parts) >= 2 else base
            break
    for i in range(1, 11):
        text = text.replace(f"α{i}", "")
    for i in range(1, 7):
        text = text.replace(f"β{i}", "")
    for i in range(1, 6):
        text = text.replace(f"RC{i}", "")
    for c in "abcdefghijklmnopqrstu":
        text = text.replace(c, "")
    if len(text) == 2:
        text += "000"
    elif len(text) == 3:
        text += "00"
    elif len(text) == 4:
        text += "0"
    text = text.replace(".", "")
    return (_parse_uint(text) or 0) * 100 + minor


V180_LAYOUT_MIN = parse_tool_version("1.80β2")


@dataclass(frozen=True)
class Profile:
    family: str           # "1.5" | "1.6" | "1.7" | "1.80"
    binary_version: int   # このファミリーの CUI が書く INFO/BIN_ のバージョン


PROFILE_15 = Profile(family="1.5", binary_version=1500)
PROFILE_16 = Profile(family="1.6", binary_version=1610)
PROFILE_17 = Profile(family="1.7", binary_version=1710)
PROFILE_180 = Profile(family="1.80", binary_version=1810)
PROFILES = (PROFILE_15, PROFILE_16, PROFILE_17, PROFILE_180)


def _family(version: str) -> str | None:
    m = re.match(r"\s*1\.(\d)", version)
    if m is None:
        return None
    return {"5": "1.5", "6": "1.6", "7": "1.7", "8": "1.80"}.get(m.group(1))


def profile_for(version: str) -> Profile:
    family = _family(version)
    for profile in PROFILES:
        if profile.family == family:
            return profile
    raise ValueError(f"unsupported Effekseer version {version!r}: this toolkit supports 1.5x (1.50RC1-1.51), "
                     "1.6x (1.60-1.62e), 1.7x (1.70-1.7.3.0) and 1.80.x (1.80.0-1.80.7)")


def runtime_max_binary_version(runtime_version: str) -> int:
    """そのファミリーのランタイムが読み込める最も新しいエフェクトのバイナリバージョン
    (``SupportBinaryVersion``)。"""
    try:
        return profile_for(runtime_version).binary_version
    except ValueError:
        raise ValueError(f"unknown Effekseer runtime version {runtime_version!r} "
                         "(expected 1.5, 1.6, 1.7 or 1.80, e.g. \"1.7\")") from None


def binary_version_label(binary_version: int) -> str:
    for profile in PROFILES:
        if binary_version <= profile.binary_version:
            return profile.family
    return f"newer than {PROFILES[-1].family}"


# ---------------------------------------------------------------------------
# ディスク上の Effekseer ツール
def resolve_cui_exe(exe: Path) -> Path:
    """1.80 の ``Tool/Effekseer.exe`` は ``Tool/bin/Effekseer.exe`` を起動し直す
    ランチャー (しかも ``Finished ...`` 行を出力する) なので、本体があれば
    そちらを直接実行する。"""
    real = exe.parent / "bin" / "Effekseer.exe"
    return real if real.is_file() else exe


_UTF16_RUN_RE = re.compile(rb"(?:[0-9A-Za-z.]\x00|\xb1\x03|\xb2\x03)+")
_VERSION_TOKEN_RE = re.compile(r"(?<![0-9A-Za-z.])1\.\d+(?:\.\d+)*(?:RC\d+|α\d+|β\d+|[a-u])?(?![0-9A-Za-z.])")


def detect_cui_version(exe: Path) -> str | None:
    """``exe`` の隣か、その ``bin/`` にある ``EffekseerCore.dll`` から見つけた
    エディタのバージョン (``Core.Version``。例: ``1.62e``、``1.7.3.0``、``1.80.7``) -
    ``Effekseer.exe`` 自身のファイルバージョンリソースは ``1.0.0.0`` としか
    読めない。DLL の UTF-16 文字列にはマイグレーションのしきい値 (``1.60α9``、
    ``1.80β2``、...) も含まれるが、どれもエディタ自身より古いので
    :func:`parse_tool_version` で最も大きいものを採用する。1.50 のリリース候補
    (``1.50`` と報告される。ファミリーは同じ) 以外の 1.5x-1.80.x の全リリースで
    ``Core.Version`` と一致する。DLL やそれらしい文字列が見つからなければ
    ``None``。"""
    for dll in (exe.parent / "EffekseerCore.dll", exe.parent / "bin" / "EffekseerCore.dll"):
        if not dll.is_file():
            continue
        found: set[str] = set()
        for run in _UTF16_RUN_RE.finditer(dll.read_bytes()):
            for token in _VERSION_TOKEN_RE.finditer(run.group(0).decode("utf-16-le", errors="ignore")):
                if not re.match(r"1\.0(?!\d)", token.group(0)):
                    found.add(token.group(0))
        if found:
            return max(found, key=parse_tool_version)
    return None


def same_family(a: str, b: str) -> bool:
    return _family(a) is not None and _family(a) == _family(b)


# ---------------------------------------------------------------------------
# ファイルごとの ToolVersion ルール
@dataclass(frozen=True)
class Migration:
    """エディタのマイグレーション 1 つ: ToolVersion が ``skipped_from`` 未満の
    ファイルは ``legacy`` のフィールドが ``native`` 側へ移される (そちらを上書き)。
    それ以上のファイルは ``native`` を書かれたまま保ち、``legacy`` は無視される。
    パスは ``/`` 区切りで ``<Node>`` からの相対。末尾の ``/*`` はその要素の任意の子を
    表す。``kinds`` は ``native`` 側を ``DrawingValues/Type`` がそのどれかである
    ノードに限定する (マイグレーションはそれらしか触らない)。``legacy_requires`` は
    ``legacy`` 側を、その要素も持つノードに限定する (それが無ければマイグレーションは
    何もしないので、何も失われない)。"""
    skipped_from: str
    what: str
    legacy: tuple[str, ...]
    native: tuple[str, ...]
    kinds: tuple[int, ...]
    legacy_requires: str | None


_TRACK_RAILS = ("ColorLeft", "ColorLeftMiddle", "ColorCenter", "ColorCenterMiddle", "ColorRight", "ColorRightMiddle")
_COLOR_SUFFIXES = ("", "_Fixed", "_Random", "_Easing", "_FCurve")

MIGRATIONS: tuple[Migration, ...] = (
    Migration("1.50β3", "Distortion/Model lighting/normal texture -> RendererCommonValues Material/NormalTexture",
              legacy=("RendererCommonValues/Distortion", "DrawingValues/Model/Lighting",
                      "DrawingValues/Model/NormalTexture"),
              native=(), kinds=(), legacy_requires="RendererCommonValues"),
    Migration("1.60α1", "flat UVAnimation fields -> UVAnimation/AnimationParams",
              legacy=("RendererCommonValues/UVAnimation/Start", "RendererCommonValues/UVAnimation/Size",
                      "RendererCommonValues/UVAnimation/FrameLength", "RendererCommonValues/UVAnimation/FrameCountX",
                      "RendererCommonValues/UVAnimation/FrameCountY", "RendererCommonValues/UVAnimation/LoopType"),
              native=(), kinds=(), legacy_requires=None),
    Migration("1.60α3", "LocationAbsValues Type/Gravity/AttractiveForce -> LocationAbsValues/LocalForceField4",
              legacy=("LocationAbsValues/Type", "LocationAbsValues/Gravity", "LocationAbsValues/AttractiveForce"),
              native=(), kinds=(), legacy_requires=None),
    Migration("1.70α1", "Sprite ColorAll* / Model Color* -> DrawingValues/ColorAll",
              legacy=tuple(f"DrawingValues/Sprite/ColorAll{s}" for s in _COLOR_SUFFIXES)
              + tuple(f"DrawingValues/Model/Color{s}" for s in _COLOR_SUFFIXES),
              native=("DrawingValues/ColorAll",), kinds=(2, 5), legacy_requires=None),
    Migration("1.70α2", "Track Color* rails -> DrawingValues/TrailColor*",
              legacy=tuple(f"DrawingValues/Track/{r}{s}" for r in _TRACK_RAILS for s in _COLOR_SUFFIXES),
              native=tuple(f"DrawingValues/Trail{r}" for r in _TRACK_RAILS), kinds=(6,), legacy_requires=None),
    Migration("1.80β2", "CommonValues GenerationTime*/RemoveWhen*/TriggerParam -> CommonValues/Generation+Removal",
              legacy=("CommonValues/RemoveWhenLifeIsExtinct", "CommonValues/RemoveWhenParentIsRemoved",
                      "CommonValues/RemoveWhenAllChildrenAreRemoved", "CommonValues/GenerationTime",
                      "CommonValues/GenerationTimeOffset", "CommonValues/TriggerParam"),
              native=("CommonValues/Generation", "CommonValues/Removal"), kinds=(), legacy_requires=None),
)

# ツールキットが知っている <Node> 相対のブロックのうち古いファミリーには無いもの
# (その EffekseerCore.dll に存在しない) と、それを追加したファミリー。
_ADDED_IN = {"GpuParticles": "1.80", "CollisionsValues": "1.80", "KillRulesValues": "1.7",
             "CommonValues/TriggerParam": "1.7"}


def tool_version_of(project: Elem) -> str:
    tv = project.child("ToolVersion")
    return (tv.text or "") if tv is not None else ""


def uses_v180_layout(project: Elem) -> bool:
    return parse_tool_version(tool_version_of(project)) >= V180_LAYOUT_MIN


def layout_of(project: Elem) -> str:
    """``presets.common_values`` 用の ``CommonValues`` レイアウト: Effekseer 1.80 が
    ネイティブに読むファイルなら ``"v180"``、それ以外は ``"legacy"``。"""
    return "v180" if uses_v180_layout(project) else "legacy"


def drawing_type(node: Elem) -> int:
    """Effekseer が読むとおりの ``DrawingValues/Type``: ``Type`` (または
    ``DrawingValues``) が無ければ 1.5x-1.80.x のどのエディタでも Sprite (2)。
    テキストが整数でなければ -1。"""
    t = node.get("DrawingValues.Type")
    try:
        return int((t.text or "").strip()) if t is not None else 2
    except ValueError:
        return -1


def node_migration_problems(node: Elem, tool_version: str) -> list[str]:
    """``tool_version`` を宣言したファイルにおいて、``node`` 直下のフィールドのうち
    Effekseer が捨てるもの (マイグレーションには新しすぎるファイル中の legacy 形) や
    上書きするもの (マイグレーションされるほど古いファイル中の native 形)。"""
    number = parse_tool_version(tool_version)
    shown = tool_version or "(none)"
    problems: list[str] = []
    for m in MIGRATIONS:
        skipped = number >= parse_tool_version(m.skipped_from)
        if skipped:
            if m.legacy_requires is not None and node.get(m.legacy_requires.replace("/", ".")) is None:
                continue
            for path in m.legacy:
                if node.get(path.replace("/", ".")) is not None:
                    problems.append(f"{path} is ignored in a file with ToolVersion {shown}: Effekseer only reads it "
                                    f"from files older than {m.skipped_from} ({m.what})")
        elif not m.kinds or drawing_type(node) in m.kinds:
            for path in m.native:
                if node.get(path.replace("/", ".")) is not None:
                    problems.append(f"{path} is overwritten in a file with ToolVersion {shown}: Effekseer migrates "
                                    f"files older than {m.skipped_from} into it ({m.what})")
    return problems


def node_unsupported_blocks(node: Elem, profile: Profile) -> list[str]:
    order = [p.family for p in PROFILES]
    return [f"{path} only exists in Effekseer {family}+; Effekseer {profile.family} ignores it"
            for path, family in _ADDED_IN.items()
            if order.index(profile.family) < order.index(family) and node.get(path.replace("/", ".")) is not None]


def walk_nodes(project: Elem):
    """全ノードの ``(path, label, node)``。指定方式は ``show`` と同じ。"""
    root = project.child("Root")
    kids = root.child("Children") if root is not None else None
    if kids is None:
        return

    def walk(children: Elem, prefix: str):
        for i, node in enumerate(children.children):
            path = f"{prefix}{i}" if prefix == "" else f"{prefix}.{i}"
            name = node.child("Name")
            yield path, f"[{path}] {name.text if name is not None else '?'}", node
            sub = node.child("Children")
            if sub is not None and sub.children:
                yield from walk(sub, path)

    yield from walk(kids, "")


def project_migration_problems(project: Elem) -> list[str]:
    tool_version = tool_version_of(project)
    return [f"{label}: {msg}" for _, label, node in walk_nodes(project)
            for msg in node_migration_problems(node, tool_version)]


def project_unsupported_blocks(project: Elem, profile: Profile) -> list[str]:
    return [f"{label}: {msg}" for _, label, node in walk_nodes(project)
            for msg in node_unsupported_blocks(node, profile)]


def too_new_problem(project: Elem, editor_version: str) -> str | None:
    tool_version = tool_version_of(project)
    if tool_version and parse_tool_version(tool_version) > parse_tool_version(editor_version):
        return (f"ToolVersion {tool_version!r} is newer than Effekseer {editor_version}; that editor/CUI "
                "refuses to load the file (\"Version Error\", and the CUI still exits 0 with no output)")
    return None
