"""Effekseer version handling: which editor/CUI the toolkit targets, and what
that changes about the ``.efkproj`` it reads and writes.

Supported families (every release with a Windows tool was checked - see
``README.md``): 1.5x (1.50RC1-1.51), 1.6x (1.60-1.62e), 1.7x (1.70-1.7.3.0)
and 1.80.x (1.80.0-1.80.7). Within a family every release has identical enum
domains (read by reflection from each ``EffekseerCore.dll``) and writes the
same binary version, so a :class:`Profile` is per family.

Two different things decide the format, and they must not be confused:

* **The configured Effekseer version** (``effekseer.version`` in
  ``effect_config.json``, ``$EFFEKSEER_VERSION`` or ``--effekseer-version``)
  picks a :class:`Profile`: the CUI to run, the enum domains the editor accepts
  (see ``enums.py``) and the binary version the CUI must produce.
* **A file's own ``<ToolVersion>``** decides how Effekseer *loads* it. Every
  editor runs its version migrations (``Core.LoadFromXml`` +
  ``Utils/ProjectVersionUpdater.cs``) only on files older than each
  migration's threshold. ``presets.py`` builds the oldest shapes (the ones
  the real samples it was built from use), so they are only read correctly
  from a file old enough for every migration to run - which is why
  ``new-project`` always writes :data:`LEGACY_TOOL_VERSION`. In a newer file
  those fields are silently ignored, and the reverse (a migrated, "native"
  field in an old file) is overwritten by the migration. :data:`MIGRATIONS`
  lists both sides per threshold; the guards below refuse either mismatch.
  Verified by compiling each shape under several ToolVersions with the 1.80.7
  CUI and decoding the ``EDIT`` chunk (``selftest`` stage 11). An editor also
  refuses a ``ToolVersion`` newer than itself, printing "Version Error" while
  still exiting 0.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .model import Elem

FALLBACK_VERSION = "1.7.3.0"
# Pre-1.00 ToolVersion of the AndrewFM01 samples presets.py was built from:
# unparsable, so every editor (1.50RC1 ... 1.80.7) runs all its migrations.
LEGACY_TOOL_VERSION = "0.7CTP1"


def _parse_uint(text: str) -> int | None:
    """``uint.TryParse`` with the default ``NumberStyles.Integer``."""
    m = re.fullmatch(r"\s*\+?(\d+)\s*", text)
    if m is None:
        return None
    value = int(m.group(1))
    return value if value <= 0xFFFFFFFF else None


def parse_tool_version(text: str) -> int:
    """Port of Effekseer's ``Core.ParseVersion`` (1.80.7 ``Core.cs``): the
    number every ``ToolVersion`` comparison in the editor uses.
    ``"1.80"`` -> 180030, ``"1.80β2"`` -> 180012, ``"1.7.3.0"`` -> 173030,
    ``"0.7CTP1"`` -> 30 (unparsable, so every migration runs).
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
    binary_version: int   # INFO/BIN_ version this family's CUI writes


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
    """Highest effect binary version a runtime of that family loads
    (``SupportBinaryVersion``)."""
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
# the Effekseer tool on disk
def resolve_cui_exe(exe: Path) -> Path:
    """1.80's ``Tool/Effekseer.exe`` is a launcher that re-runs
    ``Tool/bin/Effekseer.exe`` (and prints a ``Finished ...`` line); run the
    real one directly when it is there."""
    real = exe.parent / "bin" / "Effekseer.exe"
    return real if real.is_file() else exe


_UTF16_RUN_RE = re.compile(rb"(?:[0-9A-Za-z.]\x00|\xb1\x03|\xb2\x03)+")
_VERSION_TOKEN_RE = re.compile(r"(?<![0-9A-Za-z.])1\.\d+(?:\.\d+)*(?:RC\d+|α\d+|β\d+|[a-u])?(?![0-9A-Za-z.])")


def detect_cui_version(exe: Path) -> str | None:
    """The editor version (``Core.Version``, e.g. ``1.62e``, ``1.7.3.0``,
    ``1.80.7``) found in ``EffekseerCore.dll`` next to ``exe`` or in its
    ``bin/`` - ``Effekseer.exe``'s own file-version resource just reads
    ``1.0.0.0``. The DLL's UTF-16 strings also hold its migration thresholds
    (``1.60α9``, ``1.80β2``, ...), all older than the editor itself, so the
    highest by :func:`parse_tool_version` wins. Matches ``Core.Version`` for
    every 1.5x-1.80.x release except the 1.50 release candidates (reported as
    ``1.50``; same family). ``None`` when the DLL or a plausible string isn't
    found."""
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
# per-file ToolVersion rules
@dataclass(frozen=True)
class Migration:
    """One editor migration: files whose ToolVersion is below ``skipped_from``
    get ``legacy`` fields moved into ``native`` ones (overwriting those);
    files at or above it keep ``native`` as written and ignore ``legacy``.
    Paths are ``/``-separated, relative to ``<Node>``; a trailing ``/*``
    means any child of that element. ``kinds`` limits the ``native`` side to
    nodes whose ``DrawingValues/Type`` is one of them (the migration only
    touches those); ``legacy_requires`` limits the ``legacy`` side to nodes
    that also have that element (the migration does nothing without it, so
    nothing is lost)."""
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

# Node-relative blocks the toolkit knows of that older families don't have
# (absent from their EffekseerCore.dll), with the family that added them.
_ADDED_IN = {"GpuParticles": "1.80", "CollisionsValues": "1.80", "KillRulesValues": "1.7",
             "CommonValues/TriggerParam": "1.7"}


def tool_version_of(project: Elem) -> str:
    tv = project.child("ToolVersion")
    return (tv.text or "") if tv is not None else ""


def uses_v180_layout(project: Elem) -> bool:
    return parse_tool_version(tool_version_of(project)) >= V180_LAYOUT_MIN


def layout_of(project: Elem) -> str:
    """``CommonValues`` layout for ``presets.common_values``: ``"v180"`` for a
    file Effekseer 1.80 reads natively, else ``"legacy"``."""
    return "v180" if uses_v180_layout(project) else "legacy"


def drawing_type(node: Elem) -> int:
    """``DrawingValues/Type`` as Effekseer reads it: a missing ``Type`` (or
    ``DrawingValues``) is Sprite (2) in every 1.5x-1.80.x editor; -1 when the
    text isn't an integer."""
    t = node.get("DrawingValues.Type")
    try:
        return int((t.text or "").strip()) if t is not None else 2
    except ValueError:
        return -1


def node_migration_problems(node: Elem, tool_version: str) -> list[str]:
    """Fields directly under ``node`` that Effekseer drops (legacy shape in a
    file too new for the migration) or overwrites (native shape in a file old
    enough to be migrated) for a file declaring ``tool_version``."""
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
    """``(path, label, node)`` for every node, with ``show``'s addressing."""
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
