"""Curated, sample-derived builders for new ``.efkproj`` content.

Effekseer's real schema is hundreds of fields across dozens of node kinds;
most fields in any given file are only present because they differ from the
editor's default. Rather than guess at a complete typed schema, this module
gives you:

* :func:`elem` - a small generic composer for building any nested tag shape
  (leaf text, or nested children from either raw values or other ``Elem``s).
* value-shape helpers (:func:`fixed_axes`, :func:`pva`, :func:`easing`,
  :func:`random_color`) for the "distribution" shapes seen across the corpus
  this toolkit was built from.
* common node-block builders (``common_values``, ``location_values``, ...)
  and node builders (:func:`sprite_node`, :func:`ring_node`,
  :func:`ribbon_node`, :func:`model_node`, :func:`track_node`,
  :func:`group_node`) assembled from real field names and defaults observed
  in those samples.

**Scope**: built from 14 AndrewFM01 samples originally (v1: ``Sprite`` /
``Ring`` / ``Ribbon`` ``DrawingValues`` only), then widened against a 310-file
corpus spanning 11 real asset packs (AndrewFM01, MAGICALxSPIRAL, NextSoft01,
NitoriBox, Pierre01_130, Pierre02_130, ProjectDanmakuGirls, Suzuki01,
TouhouStrategy, tktk01, tktk02) to add ``Model``/``Track`` ``DrawingValues``
kinds, the ``SoundValues``/``LocationAbsValues`` node-level blocks, and
several previously-unmodeled parameter categories on the existing blocks
(texture/fade/UV on ``RendererCommonValues``, random/per-corner color and
position on ``Sprite``, Easing/Single/Axis scaling+rotation variants, parent
transform-inheritance flags on ``CommonValues``). Still out of scope, same
reasoning as v1 (rare in the corpus and/or no confirmed-active real example
to crib from): FCurve (keyframed) variants of Scaling/Rotation/Sprite color,
project-root ``Behavior``/``TargetLocation``/``Culling`` metadata, and a
``Field``/turbulence/collision node concept (none found in 310 real samples).
"""

from __future__ import annotations

from .enums import easing_speed
from .model import Elem

# ---------------------------------------------------------------------------
# generic composition
def _fmt(value) -> str:
    if isinstance(value, (dict, list, tuple)):
        # A dict/list here means a PVA-shaped {"center":.., "max":.., "min":..}
        # spec (or similar) was passed where a leaf text value was expected -
        # e.g. xyz("Velocity", x={...}) instead of building a proper nested
        # PVA block. str()-ing it would silently write the Python repr as
        # element text (well-formed XML, garbage data) instead of failing.
        raise TypeError(
            f"_fmt() got a {type(value).__name__} ({value!r}); did you mean to "
            "build a nested Elem (e.g. via pva()) instead of passing this as a "
            "leaf value?"
        )
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return repr(value)
    return str(value)


def _opt_speed(value, what: str) -> int | None:
    """``None`` passes through (field omitted); anything else must be a legal
    Effekseer easing speed (see :func:`enums.easing_speed`)."""
    return None if value is None else easing_speed(value, what)


def elem(tag: str, *, text=None, children: list[Elem] | None = None, **leaf_children) -> Elem:
    """Build an :class:`Elem`.

    ``elem("X", text=1.8)`` -> a text leaf ``<X>1.8</X>``.
    ``elem("Location", X=1.8)`` -> ``<Location><X>1.8</X></Location>``.
    ``elem("Outer_Fixed", Location=elem("Location", X=1.8))`` nests an
    already-built ``Elem`` (keyword name is only for readability at the call
    site - the child's own ``.tag`` is what's written).
    """
    e = Elem(tag)
    if children:
        e.children.extend(children)
    for key, val in leaf_children.items():
        if isinstance(val, Elem):
            e.children.append(val)
        elif val is not None:
            e.children.append(Elem(key, text=_fmt(val)))
    if text is not None and not e.children:
        e.text = _fmt(text)
    return e


# ---------------------------------------------------------------------------
# value-shape helpers
def fixed_axes(tag: str, **axes) -> Elem:
    """A ``Tag_Fixed``-style leaf with per-axis values, e.g.
    ``fixed_axes("ColorAll_Fixed", R=0, G=0, B=0, A=255)``.
    """
    return elem(tag, **axes)


def pva(tag: str, *, x=None, y=None, z=None, center=None, max=None, min=None,
        drawn_as: int | None = None) -> Elem:
    """Either a single scalar PVA block (pass ``center``/``max``/``min``
    directly) or a per-axis PVA block (pass ``x=``/``y=``/``z=`` as dicts of
    ``{"center":..,"max":..,"min":..}``), matching both shapes seen in the
    samples (e.g. ``ScalingValues.PVA.Scale.X`` vs a bare scalar PVA).
    """
    e = Elem(tag)
    axes = {"X": x, "Y": y, "Z": z}
    if any(v is not None for v in axes.values()):
        for name, spec in axes.items():
            if spec is None:
                continue
            # Recurse through the scalar branch so each axis comes out as
            # <Center>/<Max>/<Min>(/<DrawnAs>). This used to be
            # elem(name, **spec), which wrote the dict keys verbatim as
            # lowercase <center>/<max>/<min> - Effekseer's loader looks the
            # children up case-sensitively (e["Center"]), so the whole axis
            # was silently ignored and fell back to the editor default (scale
            # 1.0, no randomization) in every shipped effect built this way.
            e.children.append(pva(name, **spec))
        if drawn_as is not None:
            e.children.append(Elem("DrawnAs", text=_fmt(drawn_as)))
        return e
    if center is not None:
        e.children.append(Elem("Center", text=_fmt(center)))
    if max is not None:
        e.children.append(Elem("Max", text=_fmt(max)))
    if min is not None:
        e.children.append(Elem("Min", text=_fmt(min)))
    if drawn_as is not None:
        e.children.append(Elem("DrawnAs", text=_fmt(drawn_as)))
    return e


def easing(tag: str, start: Elem | None = None, end: Elem | None = None,
           start_speed=None, end_speed=None) -> Elem:
    """A ``Start``/``End`` (+ optional ``StartSpeed``/``EndSpeed``) block.
    ``start``/``end`` can be per-axis (``elem("Start", X=pva(...), ...)``),
    flat-scalar (``pva("Start", center=.., max=.., min=..)``), or per-channel
    (``random_color("Start", r=.., g=.., ...)``) - whichever shape the
    caller builds, since real samples use all three depending on which block
    this ``Easing`` sits under (Location/Scaling/Rotation vs. Scaling's
    ``SingleEasing`` vs. Model/Track's per-channel color easing).
    ``start_speed``/``end_speed`` are Effekseer ``EasingStart``/``EasingEnd``
    enums, not free floats: only ``-30,-20,-10,0,10,20,30`` are legal (see
    :data:`enums.EASING_SPEEDS`); anything else raises ``ValueError`` here
    because the Effekseer editor crashes on it.
    """
    e = Elem(tag)
    if start is not None:
        e.children.append(elem("Start", children=start.children) if start.tag != "Start" else start)
    if end is not None:
        e.children.append(elem("End", children=end.children) if end.tag != "End" else end)
    if start_speed is not None:
        e.children.append(Elem("StartSpeed", text=_fmt(easing_speed(start_speed, "start_speed"))))
    if end_speed is not None:
        e.children.append(Elem("EndSpeed", text=_fmt(easing_speed(end_speed, "end_speed"))))
    return e


def color(tag: str, r=None, g=None, b=None, a=None) -> Elem:
    return elem(tag, R=r, G=g, B=b, A=a)


def random_color(tag: str, *, r=None, g=None, b=None, a=None,
                  drawn_as: int | None = None, color_space: int | None = None) -> Elem:
    """A per-channel PVA color block, e.g. ``random_color("ColorAll_Random",
    r={"center": 0, "max": 255, "min": 0}, a={"center": 255, "max": 255,
    "min": 255})`` -> ``<ColorAll_Random><R>...</R><A>...</A></ColorAll_Random>``.
    Each channel is a flat ``{"center":..,"max":..,"min":..}`` dict. The
    block-level ``drawn_as``/``color_space`` siblings (after ``R``/``G``/
    ``B``/``A``) are real but rarely touched (all real samples use `1`/`0`).
    """
    e = Elem(tag)
    for name, spec in (("R", r), ("G", g), ("B", b), ("A", a)):
        if spec is not None:
            e.children.append(pva(name, **spec))
    if drawn_as is not None:
        e.children.append(Elem("DrawnAs", text=_fmt(drawn_as)))
    if color_space is not None:
        e.children.append(Elem("ColorSpace", text=_fmt(color_space)))
    return e


def xyz(tag: str, x=None, y=None, z=None) -> Elem:
    return elem(tag, X=x, Y=y, Z=z)


def axis_pva(*, axis: Elem, rotation: dict | None = None, velocity: dict | None = None,
             acceleration: dict | None = None) -> Elem:
    """``AxisPVA`` (``RotationValues`` Type=3): ``axis`` is a per-axis PVA
    ``Elem`` naming the spin-axis direction (e.g. ``xyz("Axis",
    x=pva("X", center=0, max=0, min=0), z=pva("Z", center=1, max=1, min=1))``
    for a Z-axis spin); ``rotation``/``velocity``/``acceleration`` are flat
    ``{"center":..,"max":..,"min":..}`` dicts for the scalar angle/spin-speed
    around that axis.
    """
    e = Elem("AxisPVA")
    e.children.append(axis if axis.tag == "Axis" else Elem("Axis", children=axis.children))
    if rotation is not None:
        e.children.append(pva("Rotation", **rotation))
    if velocity is not None:
        e.children.append(pva("Velocity", **velocity))
    if acceleration is not None:
        e.children.append(pva("Acceleration", **acceleration))
    return e


def axis_easing(*, axis: Elem, start: dict | None = None, end: dict | None = None,
                 start_speed=None, end_speed=None) -> Elem:
    """``AxisEasing`` (``RotationValues`` Type=4) - structurally inferred by
    analogy with :func:`axis_pva`/:func:`easing` (an axis direction plus an
    eased scalar angle); no sample in the 310-file corpus had this variant
    actively selected (always cached-inert behind ``RotationValues.Type=3``
    in the files that carry it), so treat this as unverified until a real
    active example turns up. ``start``/``end`` are flat ``{"center":..,
    "max":..,"min":..}`` dicts.
    """
    e = Elem("AxisEasing")
    e.children.append(axis if axis.tag == "Axis" else Elem("Axis", children=axis.children))
    if start is not None:
        e.children.append(pva("Start", **start))
    if end is not None:
        e.children.append(pva("End", **end))
    if start_speed is not None:
        e.children.append(Elem("StartSpeed", text=_fmt(easing_speed(start_speed, "start_speed"))))
    if end_speed is not None:
        e.children.append(Elem("EndSpeed", text=_fmt(easing_speed(end_speed, "end_speed"))))
    return e


# ---------------------------------------------------------------------------
# common Node child-block builders
COMMON_LAYOUTS = ("legacy", "v180")


def common_values(*, layout: str, max_generation=None, infinite: bool | None = None,
                   location_effect_type: int | None = None,
                   rotation_effect_type: int | None = None,
                   scale_effect_type: int | None = None,
                   generation_time=None, generation_time_offset=None,
                   life=None, remove_when_life_extinct: bool | None = None,
                   remove_when_parent_removed: bool | None = None,
                   remove_when_all_children_removed: bool | None = None,
                   trigger_to_start: int | None = None, trigger_to_stop: int | None = None,
                   trigger_to_remove: int | None = None,
                   generation_timing: int | None = None, trigger: int | None = None,
                   trigger_count=None) -> Elem:
    """``CommonValues``. ``location_effect_type``/``rotation_effect_type``/
    ``scale_effect_type`` are the parent-transform-inheritance flags for
    child nodes (0/1/2, real corpus mode is 1).

    ``layout`` must match the target file's ``ToolVersion`` (see
    ``versions.layout_of``), because Effekseer picks the layout from it:

    * ``"legacy"`` (ToolVersion < 1.80β2): ``RemoveWhen*``, ``GenerationTime``/
      ``GenerationTimeOffset`` and ``TriggerParam`` are direct children; order
      matches a real verbose sample (``NextSoft01/MagicFire1.efkproj``) and
      the 1.7.3 editor's own output. 1.80 migrates these on load.
    * ``"v180"``: the same values live in ``<Generation>``/``<Removal>``
      (1.80.7 ``Data/CommonValues.cs``, order as the 1.80.7 editor writes it),
      which also carry the 1.80-only ``generation_timing`` (0=Continuous,
      1=Trigger), ``trigger`` and ``trigger_count``.

    ``trigger_*`` are Effekseer ``TriggerType`` values: 0=None,
    1/257/513/769=Trigger0-3, and (1.80 only) 2=ParentRemoved,
    3=ParentCollided. PVA-shaped values are ``{"center":..,"max":..,"min":..}``.
    """
    if layout not in COMMON_LAYOUTS:
        raise ValueError(f"layout={layout!r}; expected one of {COMMON_LAYOUTS}")
    if layout == "legacy" and (generation_timing is not None or trigger is not None
                               or trigger_count is not None):
        raise ValueError("generation_timing/trigger/trigger_count only exist in Effekseer 1.80's "
                         "CommonValues layout (a file with ToolVersion 1.80 or later)")
    e = Elem("CommonValues")
    if max_generation is not None or infinite is not None:
        mg = Elem("MaxGeneration")
        if max_generation is not None:
            mg.children.append(Elem("Value", text=_fmt(max_generation)))
        if infinite is not None:
            mg.children.append(Elem("Infinite", text=_fmt(infinite)))
        e.children.append(mg)
    if location_effect_type is not None:
        e.children.append(Elem("LocationEffectType", text=_fmt(location_effect_type)))
    if rotation_effect_type is not None:
        e.children.append(Elem("RotationEffectType", text=_fmt(rotation_effect_type)))
    if scale_effect_type is not None:
        e.children.append(Elem("ScaleEffectType", text=_fmt(scale_effect_type)))

    if layout == "v180":
        if life is not None:
            e.children.append(pva("Life", **life))
        generation = elem(
            "Generation", Timing=generation_timing,
            GenerationTime=pva("GenerationTime", **generation_time) if generation_time is not None else None,
            GenerationTimeOffset=(pva("GenerationTimeOffset", **generation_time_offset)
                                  if generation_time_offset is not None else None),
            ToStartGeneration=trigger_to_start, ToStopGeneration=trigger_to_stop, Trigger=trigger,
            TriggerCount=pva("TriggerCount", **trigger_count) if trigger_count is not None else None,
        )
        if generation.children:
            e.children.append(generation)
        removal = elem("Removal", WhenLifeIsExtinct=remove_when_life_extinct,
                       WhenParentIsRemoved=remove_when_parent_removed,
                       WhenAllChildrenAreRemoved=remove_when_all_children_removed,
                       TriggerToRemove=trigger_to_remove)
        if removal.children:
            e.children.append(removal)
        return e

    if remove_when_life_extinct is not None:
        e.children.append(Elem("RemoveWhenLifeIsExtinct", text=_fmt(remove_when_life_extinct)))
    if remove_when_parent_removed is not None:
        e.children.append(Elem("RemoveWhenParentIsRemoved", text=_fmt(remove_when_parent_removed)))
    if remove_when_all_children_removed is not None:
        e.children.append(Elem("RemoveWhenAllChildrenAreRemoved", text=_fmt(remove_when_all_children_removed)))
    if life is not None:
        e.children.append(pva("Life", **life))
    if generation_time is not None:
        e.children.append(pva("GenerationTime", **generation_time))
    if generation_time_offset is not None:
        e.children.append(pva("GenerationTimeOffset", **generation_time_offset))
    trigger_param = elem("TriggerParam", ToStartGeneration=trigger_to_start,
                         ToStopGeneration=trigger_to_stop, ToRemove=trigger_to_remove)
    if trigger_param.children:
        e.children.append(trigger_param)
    return e


def location_values(*, fixed_xyz: dict | None = None, velocity: Elem | None = None,
                     acceleration: Elem | None = None, easing: Elem | None = None) -> Elem:
    """``LocationValues``. ``fixed_xyz`` is a plain ``{"X":.., "Y":.., "Z":..}``
    dict for a ``Type=0``/``Fixed`` block; ``velocity``/``acceleration`` are
    ``xyz("Velocity", ...)``/``xyz("Acceleration", ...)``-shaped ``Elem``s for
    a ``Type=1``/``PVA`` block; ``easing`` is a ``Type=2`` per-axis
    ``easing("Easing", start=elem("Start", X=pva(...), ...), end=...)``
    block.
    """
    e = Elem("LocationValues")
    if fixed_xyz is not None:
        e.children.append(Elem("Type", text="0"))
        e.children.append(elem("Fixed", Location=xyz("Location", **fixed_xyz)))
    elif velocity is not None or acceleration is not None:
        e.children.append(Elem("Type", text="1"))
        pva_block = Elem("PVA")
        if velocity is not None:
            pva_block.children.append(velocity)
        if acceleration is not None:
            pva_block.children.append(acceleration)
        e.children.append(pva_block)
    if easing is not None:
        e.children.append(Elem("Type", text="2"))
        e.children.append(easing if easing.tag == "Easing" else Elem("Easing", children=easing.children))
    return e


def location_abs_values(*, gravity: dict | None = None, attractive_force=None) -> Elem:
    """``LocationAbsValues`` (a ``Node``-level sibling of ``LocationValues``,
    sitting after ``ScalingValues``/before ``GenerationLocationValues`` in
    real files). ``gravity`` is a plain ``{"x":..,"y":..,"z":..}`` dict
    (Type=1, real shape doubles the tag: ``<Gravity><Gravity><X>...``);
    ``attractive_force`` is a plain scalar pull-strength (Type=2). Real
    example: ``AndrewFM01/blue_laser.efkproj``.
    """
    e = Elem("LocationAbsValues")
    if gravity is not None:
        e.children.append(Elem("Type", text="1"))
        e.children.append(elem("Gravity", Gravity=xyz("Gravity", **gravity)))
    elif attractive_force is not None:
        e.children.append(Elem("Type", text="2"))
        e.children.append(elem("AttractiveForce", Force=attractive_force))
    return e


def rotation_values(*, fixed: Elem | None = None, velocity: Elem | None = None,
                     acceleration: Elem | None = None, easing: Elem | None = None,
                     axis_pva: Elem | None = None, axis_easing: Elem | None = None) -> Elem:
    """``RotationValues``. ``fixed`` is ``xyz("Rotation", ...)``-shaped for a
    ``Type=0``/``Fixed`` block; ``velocity``/``acceleration`` are
    ``xyz("Rotation", X=pva(...), ...)``-style (each axis itself a PVA) for a
    ``Type=1``/``PVA`` block; ``easing`` is a ``Type=2`` per-axis
    ``easing("Easing", ...)`` block (same shape as ``location_values``'s).
    ``axis_pva``/``axis_easing`` (Type=3/4, see :func:`axis_pva`/
    :func:`axis_easing`) are **not** "single scalar applied to all axes" like
    ``ScalingValues``'s Type=3/4 - they define a spin axis plus the angle
    around it.
    """
    e = Elem("RotationValues")
    if fixed is not None:
        e.children.append(Elem("Type", text="0"))
        e.children.append(elem("Fixed", Rotation=fixed))
    elif velocity is not None or acceleration is not None:
        e.children.append(Elem("Type", text="1"))
        pva_block = Elem("PVA")
        if velocity is not None:
            pva_block.children.append(velocity if velocity.tag == "Velocity" else Elem("Velocity", children=velocity.children))
        if acceleration is not None:
            pva_block.children.append(acceleration if acceleration.tag == "Acceleration" else Elem("Acceleration", children=acceleration.children))
        e.children.append(pva_block)
    if easing is not None:
        e.children.append(Elem("Type", text="2"))
        e.children.append(easing if easing.tag == "Easing" else Elem("Easing", children=easing.children))
    if axis_pva is not None:
        e.children.append(Elem("Type", text="3"))
        e.children.append(axis_pva if axis_pva.tag == "AxisPVA" else Elem("AxisPVA", children=axis_pva.children))
    if axis_easing is not None:
        e.children.append(Elem("Type", text="4"))
        e.children.append(axis_easing if axis_easing.tag == "AxisEasing" else Elem("AxisEasing", children=axis_easing.children))
    return e


def scaling_values(*, fixed: Elem | None = None, pva_scale: Elem | None = None,
                    easing: Elem | None = None, single_pva: dict | None = None,
                    single_easing: Elem | None = None) -> Elem:
    """``ScalingValues``. ``fixed`` is ``xyz("Scale", ...)``-shaped for a
    ``Type=0``/``Fixed`` block; ``pva_scale`` is a ``pva("Scale", x={...},
    y={...}, drawn_as=0)``-shaped ``Elem`` for a ``Type=1``/``PVA`` block;
    ``easing`` is a ``Type=2`` per-axis ``easing("Easing", ...)`` block;
    ``single_pva`` is a flat ``{"center":..,"max":..,"min":..}`` dict
    (Type=3, applied uniformly to all axes); ``single_easing`` is a
    ``Type=4`` flat-scalar ``easing("SingleEasing", start=pva("Start",
    center=..,...), end=pva("End", ...), start_speed=.., end_speed=..)``
    block (note: flat ``Start``/``End``, unlike ``easing``'s per-axis ones).
    """
    e = Elem("ScalingValues")
    if fixed is not None:
        e.children.append(Elem("Type", text="0"))
        e.children.append(elem("Fixed", Scale=fixed))
    if pva_scale is not None:
        if fixed is None:
            e.children.append(Elem("Type", text="1"))
        e.children.append(elem("PVA", Scale=pva_scale))
    if easing is not None:
        e.children.append(Elem("Type", text="2"))
        e.children.append(easing if easing.tag == "Easing" else Elem("Easing", children=easing.children))
    if single_pva is not None:
        e.children.append(Elem("Type", text="3"))
        e.children.append(elem("SinglePVA", Scale=pva("Scale", **single_pva)))
    if single_easing is not None:
        e.children.append(Elem("Type", text="4"))
        e.children.append(single_easing if single_easing.tag == "SingleEasing" else Elem("SingleEasing", children=single_easing.children))
    return e


def generation_location_point(*, location: dict | None = None) -> Elem:
    """``GenerationLocationValues`` Type=0/``Point`` - the most common shape
    in the corpus (746/310-file tally) yet previously entirely unbuilt.
    ``location`` is a ``pva("Location", x={...}, y={...}, z={...})``-style
    per-axis dict, i.e. ``{"x": {"center":..,"max":..,"min":..}, "y": ...}``.
    """
    e = Elem("GenerationLocationValues")
    e.children.append(Elem("Type", text="0"))
    point = Elem("Point")
    if location is not None:
        point.children.append(pva("Location", **location))
    e.children.append(point)
    return e


def generation_location_circle(*, division=None, circle_type: int | None = None,
                                angle_start=None, angle_end=None, radius=None,
                                effects_rotation: bool = True) -> Elem:
    """``GenerationLocationValues`` Type=3/``Circle``. ``circle_type`` is the
    nested division-mode submode (0/1/2, default 0 in real samples) - not to
    be confused with the outer ``Type`` selector.
    """
    e = Elem("GenerationLocationValues")
    e.children.append(Elem("EffectsRotation", text=_fmt(effects_rotation)))
    e.children.append(Elem("Type", text="3"))
    circle = Elem("Circle")
    if division is not None:
        circle.children.append(pva("Division", **division) if isinstance(division, dict) else elem("Division", text=division))
    if circle_type is not None:
        circle.children.append(Elem("Type", text=_fmt(circle_type)))
    if angle_start is not None:
        circle.children.append(pva("AngleStart", **angle_start))
    if angle_end is not None:
        circle.children.append(pva("AngleEnd", **angle_end))
    if radius is not None:
        circle.children.append(pva("Radius", **radius))
    e.children.append(circle)
    return e


def generation_location_sphere(*, radius=None, rotation_x=None, rotation_y=None,
                                effects_rotation: bool = True) -> Elem:
    e = Elem("GenerationLocationValues")
    e.children.append(Elem("EffectsRotation", text=_fmt(effects_rotation)))
    e.children.append(Elem("Type", text="1"))
    sphere = Elem("Sphere")
    if radius is not None:
        sphere.children.append(pva("Radius", **radius))
    if rotation_x is not None:
        sphere.children.append(pva("RotationX", **rotation_x))
    if rotation_y is not None:
        sphere.children.append(pva("RotationY", **rotation_y))
    e.children.append(sphere)
    return e


def renderer_common(*, color_texture: str | None = None,
                     filter_: int | None = None, alpha_blend: int | None = None,
                     zwrite: bool | None = None, wrap: int | None = None,
                     ztest: bool | None = None, color_inherit_type: int | None = None,
                     fade_in: dict | None = None, fade_out: dict | None = None,
                     uv_fixed: dict | None = None, uv_animation: dict | None = None,
                     uv_scroll: dict | None = None,
                     distortion: bool | None = None, distortion_intensity=None) -> Elem:
    """``RendererCommonValues``. ``fade_in``/``fade_out`` are ``{"frame":..,
    "start_speed":..,"end_speed":..}`` (only ``frame`` required; the speeds are
    Effekseer ``EasingStart``/``EasingEnd`` enums - only ``-30,-20,-10,0,10,20,
    30`` are legal, see :data:`enums.EASING_SPEEDS` - not free floats, and an
    out-of-range value is rejected here because it crashes the Effekseer
    editor while compiling fine). ``uv_fixed``
    is ``{"start":{"x":..,"y":..}, "size":{"x":..,"y":..}}``; ``uv_animation``
    additionally takes ``frame_length``/``frame_count_x``/``frame_count_y``/
    ``loop_type``; ``uv_scroll`` replaces ``size`` with a ``speed`` dict. Pass
    at most one ``uv_*`` - each also drives the ``UV`` selector (1/2/3).
    """
    e = Elem("RendererCommonValues")
    if color_texture is not None:
        e.children.append(Elem("ColorTexture", text=color_texture))
    if filter_ is not None:
        e.children.append(Elem("Filter", text=_fmt(filter_)))
    if alpha_blend is not None:
        e.children.append(Elem("AlphaBlend", text=_fmt(alpha_blend)))
    if zwrite is not None:
        e.children.append(Elem("ZWrite", text=_fmt(zwrite)))
    if wrap is not None:
        e.children.append(Elem("Wrap", text=_fmt(wrap)))
    if ztest is not None:
        e.children.append(Elem("ZTest", text=_fmt(ztest)))
    if color_inherit_type is not None:
        e.children.append(Elem("ColorInheritType", text=_fmt(color_inherit_type)))
    if distortion is not None:
        e.children.append(Elem("Distortion", text=_fmt(distortion)))
    if distortion_intensity is not None:
        e.children.append(Elem("DistortionIntensity", text=_fmt(distortion_intensity)))
    if fade_in is not None:
        e.children.append(Elem("FadeInType", text="1"))
        e.children.append(elem("FadeIn", Frame=fade_in.get("frame"),
                                StartSpeed=_opt_speed(fade_in.get("start_speed"), "fade_in.start_speed"),
                                EndSpeed=_opt_speed(fade_in.get("end_speed"), "fade_in.end_speed")))
    if fade_out is not None:
        e.children.append(Elem("FadeOutType", text="1"))
        e.children.append(elem("FadeOut", Frame=fade_out.get("frame"),
                                StartSpeed=_opt_speed(fade_out.get("start_speed"), "fade_out.start_speed"),
                                EndSpeed=_opt_speed(fade_out.get("end_speed"), "fade_out.end_speed")))
    if uv_fixed is not None:
        e.children.append(Elem("UV", text="1"))
        e.children.append(elem("UVFixed",
                                Start=xyz("Start", **uv_fixed.get("start", {})),
                                Size=xyz("Size", **uv_fixed.get("size", {}))))
    if uv_animation is not None:
        e.children.append(Elem("UV", text="2"))
        e.children.append(elem(
            "UVAnimation",
            Start=xyz("Start", **uv_animation.get("start", {})),
            Size=xyz("Size", **uv_animation.get("size", {})),
            FrameLength=uv_animation.get("frame_length"),
            FrameCountX=uv_animation.get("frame_count_x"),
            FrameCountY=uv_animation.get("frame_count_y"),
            LoopType=uv_animation.get("loop_type"),
        ))
    if uv_scroll is not None:
        e.children.append(Elem("UV", text="3"))
        e.children.append(elem(
            "UVScroll",
            Start=xyz("Start", **uv_scroll.get("start", {})),
            Size=xyz("Size", **uv_scroll.get("size", {})),
            Speed=xyz("Speed", **uv_scroll.get("speed", {})),
        ))
    return e


# ---------------------------------------------------------------------------
# DrawingValues kind builders
def _append_color_mode(e: Elem, prefix: str, fixed: Elem | None,
                        random_: Elem | None, easing_: Elem | None) -> None:
    """Append a ``<prefix>_Fixed``/``_Random``/``_Easing`` triad (used for
    both Sprite/Ribbon's ``ColorAll`` and Ring's ``OuterColor``/
    ``CenterColor``/``InnerColor``). The ``<prefix>N</prefix>`` mode selector
    is only written for Random(1)/Easing(2) - Fixed(0) needs none, matching
    every real sparse file (``color_all`` alone has never carried an
    explicit selector in the corpus).
    """
    if easing_ is not None:
        e.children.append(Elem(prefix, text="2"))
    elif random_ is not None:
        e.children.append(Elem(prefix, text="1"))
    if fixed is not None:
        tag = f"{prefix}_Fixed"
        e.children.append(fixed if fixed.tag == tag else Elem(tag, children=fixed.children))
    if random_ is not None:
        tag = f"{prefix}_Random"
        e.children.append(random_ if random_.tag == tag else Elem(tag, children=random_.children))
    if easing_ is not None:
        tag = f"{prefix}_Easing"
        e.children.append(easing_ if easing_.tag == tag else Elem(tag, children=easing_.children))


def sprite(*, billboard: int | None = 0, color_all: Elem | None = None,
           color_all_random: Elem | None = None, color_all_easing: Elem | None = None,
           rendering_order: int | None = None,
           position_corners: dict | None = None, color_corners: dict | None = None) -> Elem:
    # Effekseer's real BillboardType: 0=Billboard (always faces the camera -
    # what almost every particle sprite wants), 1=YAxisFixed, 2=Fixed (no
    # camera-facing correction at all - renders as a static oriented plane,
    # e.g. a ground-flat shockwave ring), 3=RotatedBillboard. Defaulting this
    # to 2 previously (copied from the one real sample on hand that happened
    # to use it, a ground decal) made ordinary puff/spark sprites render as a
    # flat static card instead of a camera-facing cloud.
    e = Elem("Sprite")
    if rendering_order is not None:
        e.children.append(Elem("RenderingOrder", text=_fmt(rendering_order)))
    if billboard is not None:
        e.children.append(Elem("Billboard", text=_fmt(billboard)))
    _append_color_mode(e, "ColorAll", color_all, color_all_random, color_all_easing)
    if position_corners is not None:
        e.children.append(Elem("Position", text="1"))
        for key, tag in (("ll", "Position_Fixed_LL"), ("lr", "Position_Fixed_LR"),
                         ("ul", "Position_Fixed_UL"), ("ur", "Position_Fixed_UR")):
            spec = position_corners.get(key)
            if spec is not None:
                e.children.append(xyz(tag, **spec))
    if color_corners is not None:
        e.children.append(Elem("Color", text="1"))
        for key, tag in (("ll", "Color_Fixed_LL"), ("lr", "Color_Fixed_LR"),
                         ("ul", "Color_Fixed_UL"), ("ur", "Color_Fixed_UR")):
            spec = color_corners.get(key)
            if spec is not None:
                e.children.append(color(tag, **spec))
    return e


def ring(*, vertex_count: int = 36, outer: Elem | None = None, inner: Elem | None = None,
          center_ratio=None,
          outer_color: Elem | None = None, outer_color_random: Elem | None = None,
          outer_color_easing: Elem | None = None,
          center_color: Elem | None = None, center_color_random: Elem | None = None,
          center_color_easing: Elem | None = None,
          inner_color: Elem | None = None, inner_color_random: Elem | None = None,
          inner_color_easing: Elem | None = None) -> Elem:
    """``Ring``. Each of ``outer``/``center``/``inner`` color has the same
    Fixed/Random/Easing triad as Sprite/Ribbon's ``ColorAll`` (confirmed via
    real ``<OuterColor>``/``<CenterColor>``/``<InnerColor>`` mode selectors,
    each independently taking 0/1/2) - see :func:`_append_color_mode`.
    """
    e = Elem("Ring")
    e.children.append(Elem("VertexCount", text=_fmt(vertex_count)))
    if outer is not None:
        e.children.append(elem("Outer_Fixed", Location=outer))
    if inner is not None:
        e.children.append(elem("Inner_Fixed", Location=inner))
    if center_ratio is not None:
        e.children.append(Elem("CenterRatio_Fixed", text=_fmt(center_ratio)))
    _append_color_mode(e, "OuterColor", outer_color, outer_color_random, outer_color_easing)
    _append_color_mode(e, "CenterColor", center_color, center_color_random, center_color_easing)
    _append_color_mode(e, "InnerColor", inner_color, inner_color_random, inner_color_easing)
    return e


def ribbon(*, viewpoint_dependent: bool = True, color_all: Elem | None = None,
           color_all_random: Elem | None = None, color_all_easing: Elem | None = None) -> Elem:
    e = Elem("Ribbon")
    e.children.append(Elem("ViewpointDependent", text=_fmt(viewpoint_dependent)))
    _append_color_mode(e, "ColorAll", color_all, color_all_random, color_all_easing)
    return e


def model(*, model_path: str, lighting: bool | None = None,
          normal_texture: str | None = None,
          color_fixed: Elem | None = None, color_easing: Elem | None = None) -> Elem:
    """``Model`` ``DrawingValues`` block (Type=5). ``model_path`` is a
    relative path to a sibling ``.efkmodel`` asset (e.g. ``"Model/foo.efkmodel"``
    - resolved by the Effekseer CUI at compile time the same way
    ``RendererCommonValues.ColorTexture`` is, no special toolkit handling
    needed). ``color_easing`` is a per-channel ``easing("Color_Easing",
    start=random_color("Start", r={...}, ...), end=random_color("End", ...),
    start_speed=.., end_speed=..)`` block; when given, a ``Color`` selector
    (=2) is emitted alongside ``color_fixed`` (matches real verbose files -
    ``color_fixed`` alone needs no selector).
    """
    e = Elem("Model")
    e.children.append(Elem("Model", text=model_path))
    if normal_texture is not None:
        e.children.append(Elem("NormalTexture", text=normal_texture))
    if lighting is not None:
        e.children.append(Elem("Lighting", text=_fmt(lighting)))
    if color_easing is not None:
        e.children.append(Elem("Color", text="2"))
    if color_fixed is not None:
        e.children.append(color_fixed if color_fixed.tag == "Color_Fixed" else Elem("Color_Fixed", children=color_fixed.children))
    if color_easing is not None:
        e.children.append(color_easing if color_easing.tag == "Color_Easing" else Elem("Color_Easing", children=color_easing.children))
    return e


def track(*, color_left: Elem | None = None, color_left_middle: Elem | None = None,
          color_center: Elem | None = None, color_center_middle: Elem | None = None,
          color_right: Elem | None = None, color_right_middle: Elem | None = None) -> Elem:
    """``Track`` ``DrawingValues`` block (Type=6): 6 color "rails", left to
    right. Each param is a pre-built ``Elem`` tagged exactly as Effekseer
    expects for that rail - ``color("ColorLeft_Fixed", r=.., g=.., b=..,
    a=..)`` or ``easing("ColorLeft_Easing", start=random_color("Start",
    ...), end=random_color("End", ...))`` (swap ``ColorLeft`` for
    ``ColorLeftMiddle``/``ColorCenter``/``ColorCenterMiddle``/``ColorRight``/
    ``ColorRightMiddle`` per rail). No separate geometry fields - a Track's
    shape comes from the node's own motion history, not vertex data.
    """
    e = Elem("Track")
    for block in (color_left, color_left_middle, color_center,
                  color_center_middle, color_right, color_right_middle):
        if block is not None:
            e.children.append(block)
    return e


DRAWING_TYPE = {"sprite": 2, "ribbon": 3, "ring": 4, "model": 5, "track": 6}


def drawing_values(kind: str, block: Elem) -> Elem:
    if kind not in DRAWING_TYPE:
        raise ValueError(f"unknown DrawingValues kind {kind!r}; supported: {sorted(DRAWING_TYPE)}")
    e = Elem("DrawingValues")
    e.children.append(Elem("Type", text=_fmt(DRAWING_TYPE[kind])))
    e.children.append(block)
    return e


def sound_values(*, wave: str, volume: dict | None = None, pitch: dict | None = None,
                  pan_type: int | None = None, pan: dict | None = None,
                  distance=None, delay: dict | None = None) -> Elem:
    """``SoundValues`` - a ``Node``-level sibling of ``DrawingValues``, *not*
    a ``DrawingValues`` kind itself (Effekseer plays a node's sound
    alongside whatever it draws, or with no drawing at all). ``volume``/
    ``pitch``/``pan``/``delay`` are flat ``{"center":..,"max":..,"min":..}``
    dicts; ``distance`` is a plain scalar. ``wave`` is a relative path to a
    sibling ``.wav`` asset (resolved by the CUI at compile time, same as
    ``ColorTexture``/``Model``'s asset paths - no special toolkit handling
    needed). Real example: ``NextSoft01/MagicFire1.efkproj`` (one of only 2
    files with this genuinely enabled across a 310-file corpus - most real
    files carry an inert ``Type=0`` ``SoundValues`` instead).
    """
    sound = elem("Sound", Wave=wave)
    if volume is not None:
        sound.children.append(pva("Volume", **volume))
    if pitch is not None:
        sound.children.append(pva("Pitch", **pitch))
    if pan_type is not None:
        sound.children.append(Elem("PanType", text=_fmt(pan_type)))
    if pan is not None:
        sound.children.append(pva("Pan", **pan))
    if distance is not None:
        sound.children.append(Elem("Distance", text=_fmt(distance)))
    if delay is not None:
        sound.children.append(pva("Delay", **delay))
    e = Elem("SoundValues")
    e.children.append(Elem("Type", text="1"))
    e.children.append(sound)
    return e


# ---------------------------------------------------------------------------
# Node / project assembly
def node(name: str = "Node", *, common: Elem | None = None, location: Elem | None = None,
         rotation: Elem | None = None, scaling: Elem | None = None,
         location_abs: Elem | None = None, generation_location: Elem | None = None,
         renderer_common: Elem | None = None, drawing: Elem | None = None,
         sound: Elem | None = None, is_rendered: bool | None = None,
         children: list[Elem] | None = None) -> Elem:
    """Build a full ``<Node>`` ready to append to a parent's ``<Children>``.
    Block order matches a real file byte-for-byte (verified against
    ``NextSoft01/MagicFire1.efkproj``/``AndrewFM01/blue_laser.efkproj``):
    Common, Location, Rotation, Scaling, LocationAbs, GenerationLocation,
    RendererCommon, Drawing, Sound, then IsRendered/Name/Children.
    """
    n = Elem("Node")
    for block in (common, location, rotation, scaling, location_abs,
                  generation_location, renderer_common, drawing, sound):
        if block is not None:
            n.children.append(block)
    if is_rendered is not None:
        n.children.append(Elem("IsRendered", text=_fmt(is_rendered)))
    n.children.append(Elem("Name", text=name))
    kids = Elem("Children")
    if children:
        kids.children.extend(children)
    n.children.append(kids)
    return n


def group_node(name: str = "Node", *, children: list[Elem] | None = None, **node_kwargs) -> Elem:
    """A pure container node that draws nothing, just organizes children.
    ``DrawingValues/Type`` is written as 0 (None) explicitly: a missing
    ``Type`` - or a missing ``DrawingValues`` - is a *Sprite* in every
    Effekseer 1.5x-1.80.x editor (verified with each family's CUI)."""
    if "drawing" in node_kwargs:
        raise ValueError("group_node() draws nothing; use node(drawing=...) for a drawing node")
    return node(name, children=children, drawing=elem("DrawingValues", Type=0), **node_kwargs)


def sprite_node(name: str = "Node", *, sprite_block: Elem, children: list[Elem] | None = None,
                 **node_kwargs) -> Elem:
    return node(name, drawing=drawing_values("sprite", sprite_block), children=children, **node_kwargs)


def ring_node(name: str = "Node", *, ring_block: Elem, children: list[Elem] | None = None,
              **node_kwargs) -> Elem:
    return node(name, drawing=drawing_values("ring", ring_block), children=children, **node_kwargs)


def ribbon_node(name: str = "Node", *, ribbon_block: Elem, children: list[Elem] | None = None,
                **node_kwargs) -> Elem:
    return node(name, drawing=drawing_values("ribbon", ribbon_block), children=children, **node_kwargs)


def model_node(name: str = "Node", *, model_block: Elem, children: list[Elem] | None = None,
               **node_kwargs) -> Elem:
    return node(name, drawing=drawing_values("model", model_block), children=children, **node_kwargs)


def track_node(name: str = "Node", *, track_block: Elem, children: list[Elem] | None = None,
               **node_kwargs) -> Elem:
    return node(name, drawing=drawing_values("track", track_block), children=children, **node_kwargs)


def new_project(*, start_frame: int = 0, end_frame: int = 60, is_loop: bool = True,
                 tool_version: str = "0.7CTP1", version: int = 3,
                 root_children: list[Elem] | None = None) -> Elem:
    """Build a full ``<EffekseerProject>`` skeleton.

    Defaults (``tool_version``/``version``) match the real AndrewFM01 samples
    this toolkit was built from. ``ToolVersion`` is not a placeholder: it
    decides the ``CommonValues`` layout Effekseer reads (see
    :func:`common_values`) and an editor refuses a newer one than itself, so
    ``new-project`` passes the target version's
    ``versions.Profile.new_project_tool_version`` (``"0.7CTP1"`` for 1.7,
    loaded by every editor; ``"1.80"`` for 1.80).
    """
    root = Elem("Root")
    root.children.append(Elem("Name", text="Root"))
    children = Elem("Children")
    if root_children:
        children.children.extend(root_children)
    root.children.append(children)

    proj = Elem("EffekseerProject")
    proj.children.append(root)
    proj.children.append(Elem("ToolVersion", text=tool_version))
    proj.children.append(Elem("Version", text=_fmt(version)))
    proj.children.append(Elem("StartFrame", text=_fmt(start_frame)))
    proj.children.append(Elem("EndFrame", text=_fmt(end_frame)))
    proj.children.append(Elem("IsLoop", text=_fmt(is_loop)))
    return proj
