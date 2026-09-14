"""Effekseer ``Enum<T>``-typed field domains, per Effekseer version family
(1.5x, 1.6x, 1.7x, 1.80.x), and a checker for ``.efkproj`` node trees.

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

The other families' tables were checked against every release with a
Windows tool (1.50RC1 ... 1.80.7) by walking ``Effekseer.Data.Node``'s
properties by reflection in each release's ``EffekseerCore.dll`` and listing
each ``Value.Enum<T>``'s members - which is exactly the list the GUI's
``Enum.Initialize`` offers. All releases of a family have identical domains,
and each table below matches its family's DLLs for every suffix present there.
Later families only *add* members (1.80: ``Billboard=4``, ``Wrap=2``, ...;
1.7: ``FadeOutType=2``, ``Gradient`` colors, ``RotationValues.Type=6``,
``TriggerParam``; 1.6: more Location/Scaling types), so a value valid only in
a newer family is a violation when targeting an older one - that editor
crashes on it. One member was *renumbered*: ``TextureUVType`` is
Strech=0/Tile=1 up to 1.7 and Strech=0/TilePerParticle=1/Tile=2 in 1.80.
"""

from __future__ import annotations

from .model import Elem
from .versions import Profile, walk_nodes

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
ENUM_DOMAINS_17: dict[tuple[str, ...], frozenset[int]] = {
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
    ("TriggerParam", "ToStartGeneration"): _r(0, 1, 257, 513, 769),  # TriggerType (None, Trigger0-3)
    ("TriggerParam", "ToStopGeneration"): _r(0, 1, 257, 513, 769),
    ("TriggerParam", "ToRemove"): _r(0, 1, 257, 513, 769),
    ("DrawingValues", "TextureUVType", "Type"): _r(0, 1),      # TextureUVType (Strech/Tile)
    ("DrawingValues", "Model", "ModelReference"): _r(0, 1),    # ModelReferenceType
    ("GenerationLocationValues", "Model", "ModelReference"): _r(0, 1),
}

_TRIGGER_TYPE_180 = _r(0, 1, 257, 513, 769, 2, 3)              # + ParentRemoved, ParentCollided
_ADDED_IN_180: dict[tuple[str, ...], frozenset[int]] = {
    ("RendererCommonValues", "Wrap"): _r(0, 1, 2),             # WrapType + Mirror
    ("RendererCommonValues", "Wrap2"): _r(0, 1, 2),
    ("Sprite", "Billboard"): _r(0, 1, 2, 3, 4),                # BillboardType + DirectionalBillboard
    ("Ring", "Billboard"): _r(0, 1, 2, 3, 4),
    ("Model", "Billboard"): _r(0, 1, 2, 3, 4),
    ("RotationValues", "Type"): _r(0, 1, 2, 3, 4, 5, 6, 7),    # + RotateToVelocity
    ("RotationValues", "Velocity", "Axis"): _r(0, 1, 2, 3, 4, 5),  # PlaneAxisType
    ("TriggerParam", "ToStartGeneration"): _TRIGGER_TYPE_180,
    ("TriggerParam", "ToStopGeneration"): _TRIGGER_TYPE_180,
    ("TriggerParam", "ToRemove"): _TRIGGER_TYPE_180,
    ("CommonValues", "Generation", "Timing"): _r(0, 1),        # GenerationTimingType
    ("CommonValues", "Generation", "ToStartGeneration"): _TRIGGER_TYPE_180,
    ("CommonValues", "Generation", "ToStopGeneration"): _TRIGGER_TYPE_180,
    ("CommonValues", "Generation", "Trigger"): _TRIGGER_TYPE_180,
    ("CommonValues", "Removal", "TriggerToRemove"): _TRIGGER_TYPE_180,
    ("DrawingValues", "TextureUVType", "Type"): _r(0, 1, 2),   # TilePerParticle=1, Tile renumbered to 2
    ("DrawingValues", "Model", "ModelReference"): _r(0, 1, 2),  # + ExternalModel
    ("GenerationLocationValues", "Model", "ModelReference"): _r(0, 1, 2),
    ("GenerationLocationValues", "Model", "Coordinate"): _r(0, 1),  # ModelCoordinateType
    ("KillRulesValues", "Type"): _r(0, 1, 2, 3),               # KillType
    ("KillRulesValues", "PlaneAxis"): _r(0, 1, 2, 3, 4, 5),    # PlaneAxisType
    ("CollisionsValues", "WorldCoordinateSyatem"): _r(0, 1),   # WorldCoordinateSyatemType (sic)
    # GpuParticles (GpuParticles.cs)
    ("GpuParticles", "EmitShape", "Shape"): _r(0, 1, 2, 3, 4),  # EmitShapeParams.ShapeType
    ("GpuParticles", "Scale", "Type"): _r(0, 2),               # ScaleParams.ParamaterType (Fixed/Easing)
    ("GpuParticles", "RenderBasic", "BlendType"): _r(0, 1, 2, 3, 4),  # AlphaBlendType
    ("GpuParticles", "RenderShape", "Shape"): _r(0, 1, 2),     # RenderShapeParams.ShapeType
    ("GpuParticles", "RenderShape", "SpriteBillboard"): _r(0, 1, 2, 3),  # RenderShapeParams.BillboardType
    ("GpuParticles", "RenderColor", "ColorInheritType"): _r(0, 1, 2, 3),  # ParentEffectType
    ("GpuParticles", "RenderColor", "ColorAll", "Type"): _r(0, 1, 2, 3, 4),  # StandardColorType
    ("GpuParticles", "RenderMaterial", "Material"): _r(0, 1),  # RenderMaterialParams.MaterialType
    ("GpuParticles", "RenderMaterial", "ColorTexture", "Filter"): _r(0, 1),  # FilterType
    ("GpuParticles", "RenderMaterial", "ColorTexture", "Wrap"): _r(0, 1, 2),  # WrapType
    ("GpuParticles", "RenderMaterial", "NormalTexture", "Filter"): _r(0, 1),
    ("GpuParticles", "RenderMaterial", "NormalTexture", "Wrap"): _r(0, 1, 2),
}
ENUM_DOMAINS_180: dict[tuple[str, ...], frozenset[int]] = {**ENUM_DOMAINS_17, **_ADDED_IN_180}

# 1.6x (1.60-1.62e): no TriggerParam yet, fewer members in these enums.
ENUM_DOMAINS_16: dict[tuple[str, ...], frozenset[int]] = {
    **{k: v for k, v in ENUM_DOMAINS_17.items() if k[0] != "TriggerParam"},
    ("RendererCommonValues", "FadeOutType"): _r(0, 1),         # no FadeOutMethod 2
    ("Sprite", "ColorAll"): _r(0, 1, 2, 3),                    # StandardColorType without Gradient
    ("DrawingValues", "Model", "Color"): _r(0, 1, 2, 3),
    ("RotationValues", "Type"): _r(0, 1, 2, 3, 4, 5),          # no RotateToViewpoint
}

# 1.5x (1.50RC1-1.51): additionally no ModelReference, fewer location/scale types.
ENUM_DOMAINS_15: dict[tuple[str, ...], frozenset[int]] = {
    **{k: v for k, v in ENUM_DOMAINS_16.items() if k[-1] != "ModelReference"},
    ("LocationValues", "Type"): _r(0, 1, 2, 3),
    ("ScalingValues", "Type"): _r(0, 1, 2, 3, 4, 5),
    ("CommonValues", "LocationEffectType"): _r(0, 1, 2, 3),
}

_DOMAINS_BY_FAMILY = {"1.5": ENUM_DOMAINS_15, "1.6": ENUM_DOMAINS_16, "1.7": ENUM_DOMAINS_17,
                      "1.80": ENUM_DOMAINS_180}


def domains_for(profile: Profile) -> dict[tuple[str, ...], frozenset[int]]:
    return _DOMAINS_BY_FAMILY[profile.family]


def _domain_for(path: tuple[str, ...], domains: dict[tuple[str, ...], frozenset[int]]
                ) -> tuple[tuple[str, ...], frozenset[int]] | None:
    best = None
    for suffix, allowed in domains.items():
        if len(suffix) <= len(path) and path[-len(suffix):] == suffix:
            if best is None or len(suffix) > len(best[0]):
                best = (suffix, allowed)
    return best


def check_node(node: Elem, profile: Profile) -> list[str]:
    """Return one message per enum-domain violation directly under ``node``
    for the Effekseer version ``profile`` targets (child ``<Node>``s under
    ``<Children>`` are *not* descended into - see :func:`check_project`).
    """
    domains = domains_for(profile)
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
            hit = _domain_for(sub, domains)
            if hit is not None and value not in hit[1]:
                problems.append(
                    f"{'/'.join(sub)}={value} is not a valid Effekseer {profile.family} value "
                    f"(allowed: {sorted(hit[1])}); the Effekseer editor crashes on it"
                )

    walk(node, ())
    return problems


def check_project(project: Elem, profile: Profile) -> list[str]:
    """Run :func:`check_node` over every node of an ``<EffekseerProject>``;
    each message is prefixed with the node's ``[index.path]`` (same addressing
    as ``show``/``--parent``).
    """
    return [f"{label}: {msg}" for _, label, node in walk_nodes(project)
            for msg in check_node(node, profile)]
