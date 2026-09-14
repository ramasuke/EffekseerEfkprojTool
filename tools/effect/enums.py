"""Effekseer ``Enum<T>``-typed field domains (from the 1.7.3.0 editor sources)
and a checker for ``.efkproj`` node trees.

Why this exists: Effekseer's editor loads every ``Value.Enum<T>`` leaf with a
bare ``int.TryParse -> SetValue`` (``Data/IO.cs``, no range check), and the
GUI's ``Effekseer.GUI.Component.Enum.Update()`` then does
``enums.Where(v == selected).FirstOrDefault().Item2`` - for a value that is not
one of the enum's members ``FirstOrDefault()`` is null and the editor dies with
a ``NullReferenceException`` the moment a panel showing that field is drawn
(e.g. the "Basic Render Settings" dock for ``FadeIn``/``FadeOut``). The CUI
compiler does **not** catch this - it feeds the raw int straight into the
easing formula and exits 0 - so a bad value only surfaces when somebody opens
the ``.efkproj`` in the GUI. This module is the toolkit-side guard.

Every domain below was read from the 1.7.3.0 sources
(``Dev/Editor/EffekseerCore/Data/{Define,RendererCommonValues,RendererValues,
CommonValues,LocationValues,RotationValues,ScaleValues,
GenerationLocationValues,SoundValues}.cs``) and checked for false positives
against the 310-file real sample corpus this toolkit was built from (see
``selftest.stage_corpus_sweep``). It is deliberately *not* a full schema:
only fields the toolkit itself writes (or that share their leaf tag with one)
are listed, and a leaf whose text is not an integer is never flagged.
"""

from __future__ import annotations

from .model import Elem

# EasingStart / EasingEnd (Define.cs): negative = *Slowly{1,2,3}, positive =
# *Rapidly{1,2,3}, 0 = Start/End (linear). Used by FadeIn/FadeOut and every
# Easing/SingleEasing/AxisEasing/*_Easing block's StartSpeed/EndSpeed.
EASING_SPEEDS: tuple[int, ...] = (-30, -20, -10, 0, 10, 20, 30)


def easing_speed(value, what: str = "StartSpeed/EndSpeed") -> int:
    """Coerce ``value`` to one of :data:`EASING_SPEEDS` or raise ``ValueError``.

    Accepts ints, integral floats (``30.0``) and numeric strings (``"-30"``).
    """
    try:
        f = float(value)
    except (TypeError, ValueError) as e:
        raise ValueError(f"{what}={value!r} is not a number") from e
    if not f.is_integer() or int(f) not in EASING_SPEEDS:
        raise ValueError(
            f"{what}={value!r} is not a valid Effekseer easing speed; allowed values are "
            f"{list(EASING_SPEEDS)} (negative = slowly, positive = rapidly, 0 = linear). "
            "Effekseer's editor crashes (NullReferenceException in Enum.Update) on any "
            "other value, even though the CUI compiles it without complaint."
        )
    return int(f)


def _r(*values: int) -> frozenset[int]:
    return frozenset(values)


# (tag-path suffix, relative to <Node>) -> allowed ints. A rule applies to a
# leaf whose tag path *ends with* the suffix (longest matching suffix wins),
# so ("StartSpeed",) covers FadeIn/StartSpeed, Easing/StartSpeed,
# ColorAll_Easing/StartSpeed, ... while ("Sprite", "Color") only covers
# DrawingValues/Sprite/Color. Comments name the Effekseer enum each domain
# was read from.
ENUM_DOMAINS: dict[tuple[str, ...], frozenset[int]] = {
    ("StartSpeed",): frozenset(EASING_SPEEDS),                 # EasingStart
    ("EndSpeed",): frozenset(EASING_SPEEDS),                   # EasingEnd
    ("DrawnAs",): _r(0, 1),                                    # DrawnAs
    ("ColorSpace",): _r(0, 1),                                 # ColorSpace
    # RendererCommonValues
    ("RendererCommonValues", "Filter"): _r(0, 1),              # FilterType
    ("RendererCommonValues", "Filter2"): _r(0, 1),
    ("RendererCommonValues", "Wrap"): _r(0, 1),                # WrapType
    ("RendererCommonValues", "Wrap2"): _r(0, 1),
    ("RendererCommonValues", "AlphaBlend"): _r(0, 1, 2, 3, 4),  # AlphaBlendType
    ("RendererCommonValues", "FadeInType"): _r(0, 1),          # FadeInMethod
    ("RendererCommonValues", "FadeOutType"): _r(0, 1, 2),      # FadeOutMethod
    ("RendererCommonValues", "UV"): _r(0, 1, 2, 3, 4),         # UVType
    ("UVAnimation", "LoopType"): _r(0, 1, 2),                  # LoopType
    ("RendererCommonValues", "ColorInheritType"): _r(0, 1, 2, 3),  # ParentEffectType
    ("RendererCommonValues", "Material"): _r(0, 6, 7, 128),    # MaterialType
    # DrawingValues + per-kind blocks (RendererValues.cs)
    ("DrawingValues", "Type"): _r(0, 2, 3, 4, 5, 6),           # ParamaterType (1 unused)
    ("Sprite", "Billboard"): _r(0, 1, 2, 3),                   # BillboardType
    ("Ring", "Billboard"): _r(0, 1, 2, 3),
    ("Model", "Billboard"): _r(0, 1, 2, 3),
    ("Sprite", "RenderingOrder"): _r(0, 1),                    # RenderingOrder
    ("Ring", "RenderingOrder"): _r(0, 1),
    ("Sprite", "ColorAll"): _r(0, 1, 2, 3, 4),                 # StandardColorType
    ("Ribbon", "ColorAll"): _r(0, 1, 2),                       # ColorAllType
    ("Sprite", "Color"): _r(0, 1),                             # ColorType (Default/Fixed)
    ("Ribbon", "Color"): _r(0, 1),
    ("Sprite", "Position"): _r(0, 1),                          # PositionType
    ("Ribbon", "Position"): _r(0, 1),
    ("Ring", "Outer"): _r(0, 1, 2),                            # LocationType
    ("Ring", "Inner"): _r(0, 1, 2),
    ("Ring", "CenterRatio"): _r(0, 1, 2),                      # CenterRatioType
    ("Ring", "ViewingAngle"): _r(0, 1, 2),                     # ViewingAngleType
    ("Ring", "OuterColor"): _r(0, 1, 2),                       # ColorType (Fixed/Random/Easing)
    ("Ring", "CenterColor"): _r(0, 1, 2),
    ("Ring", "InnerColor"): _r(0, 1, 2),
    ("DrawingValues", "Model", "Color"): _r(0, 1, 2, 3, 4),    # StandardColorType
    ("DrawingValues", "Model", "Culling"): _r(0, 1, 2),        # CullingValues
    # transform / generation blocks
    ("LocationValues", "Type"): _r(0, 1, 2, 3, 4, 5),          # LocationValues.ParamaterType
    ("RotationValues", "Type"): _r(0, 1, 2, 3, 4, 5, 6),       # RotationValues.ParamaterType
    ("ScalingValues", "Type"): _r(0, 1, 2, 3, 4, 5, 6),        # ScaleValues.ParamaterType
    ("GenerationLocationValues", "Type"): _r(0, 1, 2, 3, 4),   # ParameterType
    ("GenerationLocationValues", "Circle", "Type"): _r(0, 1, 2),  # CircleType
    ("GenerationLocationValues", "Line", "Type"): _r(0, 1),    # LineType
    ("GenerationLocationValues", "Model", "Type"): _r(0, 1, 2, 3, 4),  # ModelType
    ("CommonValues", "LocationEffectType"): _r(0, 1, 2, 3, 4, 5),  # TranslationParentEffectType
    ("CommonValues", "RotationEffectType"): _r(0, 1, 2, 3),    # ParentEffectType
    ("CommonValues", "ScaleEffectType"): _r(0, 1, 2, 3),
    ("SoundValues", "Type"): _r(0, 1),                         # SoundValues.ParamaterType
    ("Sound", "PanType"): _r(0, 1),                            # ParamaterPanType
}


def _domain_for(path: tuple[str, ...]) -> tuple[tuple[str, ...], frozenset[int]] | None:
    best = None
    for suffix, allowed in ENUM_DOMAINS.items():
        if len(suffix) <= len(path) and path[-len(suffix):] == suffix:
            if best is None or len(suffix) > len(best[0]):
                best = (suffix, allowed)
    return best


def check_node(node: Elem) -> list[str]:
    """Return one message per enum-domain violation directly under ``node``
    (child ``<Node>``s under ``<Children>`` are *not* descended into - walk
    them yourself, see :func:`check_project`).
    """
    problems: list[str] = []

    def walk(e: Elem, path: tuple[str, ...]) -> None:
        for c in e.children:
            if c.tag == "Children":
                continue
            sub = path + (c.tag,)
            if c.children:
                walk(c, sub)
                continue
            text = (c.text or "").strip()
            try:
                value = int(text)
            except ValueError:
                continue
            hit = _domain_for(sub)
            if hit is not None and value not in hit[1]:
                problems.append(
                    f"{'/'.join(sub)}={value} is not a valid Effekseer value "
                    f"(allowed: {sorted(hit[1])}); the Effekseer editor crashes on it"
                )

    walk(node, ())
    return problems


def check_project(project: Elem) -> list[str]:
    """Run :func:`check_node` over every node of an ``<EffekseerProject>``;
    each message is prefixed with the node's ``[index.path]`` (same addressing
    as ``show``/``--parent``).
    """
    problems: list[str] = []
    root = project.child("Root")
    kids = root.child("Children") if root is not None else None
    if kids is None:
        return problems

    def walk(children: Elem, prefix: str) -> None:
        for i, node in enumerate(children.children):
            path = f"{prefix}{i}" if prefix == "" else f"{prefix}.{i}"
            name = node.child("Name")
            label = f"[{path}] {name.text if name is not None else '?'}"
            for msg in check_node(node):
                problems.append(f"{label}: {msg}")
            sub = node.child("Children")
            if sub is not None and sub.children:
                walk(sub, path)

    walk(kids, "")
    return problems
