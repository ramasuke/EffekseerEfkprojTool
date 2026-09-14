"""CLI subcommands for tools.effect: new-project, show, validate, add-node,
set-params, apply, compile, upgrade, install, check-env, export.

Nodes have no stable id in the ``.efkproj`` format (unlike ``tools/bt``'s
per-node GUIDs), so ``--parent``/``--path`` address a node by a dot-separated
0-based child-index path from the root, e.g. ``"1.0"`` = the root's 2nd child
node's 1st child node. ``""`` (or ``"root"``) means the root itself - use it
as ``--parent`` to attach a new top-level node. ``show`` prints these paths.
"""

from __future__ import annotations

import argparse
import filecmp
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from . import assets
from . import config
from . import efkefc
from . import enums
from . import meta as meta_mod
from . import presets as p
from . import versions
from . import xmlio
from .model import Elem

_KIND_BUILDERS = {
    "sprite": lambda: p.drawing_values("sprite", p.sprite()),
    "ring": lambda: p.drawing_values("ring", p.ring()),
    "ribbon": lambda: p.drawing_values("ribbon", p.ribbon()),
    "track": lambda: p.drawing_values("track", p.track()),
}


class CliError(RuntimeError):
    pass


def _resolve(arg: str) -> Path:
    path = Path(arg)
    if path.is_absolute():
        return path
    if path.exists():
        return path.resolve()
    return config.get().project_root / path


# ---------------------------------------------------------------------------
# compact CLI-flag value parsing (shared by add-node's dedicated flags)
def _parse_bool(spec: str) -> bool:
    return spec.lower() == "true"


def _parse_pva(spec: str) -> dict:
    """``"CENTER"`` -> a fixed value; ``"MIN:CENTER:MAX"`` -> a range."""
    parts = spec.split(":")
    if len(parts) == 1:
        v = float(parts[0])
        return {"center": v, "max": v, "min": v}
    if len(parts) == 3:
        mn, ctr, mx = (float(x) for x in parts)
        return {"center": ctr, "max": mx, "min": mn}
    raise CliError(f"bad value {spec!r}: expected CENTER or MIN:CENTER:MAX")


def _parse_color(spec: str) -> dict:
    """``"R:G:B[:A]"``, 0-255 ints, A defaults to 255."""
    parts = spec.split(":")
    if len(parts) not in (3, 4):
        raise CliError(f"bad color {spec!r}: expected R:G:B[:A]")
    vals = [int(x) for x in parts]
    if len(vals) == 3:
        vals.append(255)
    return dict(zip("rgba", vals))


def _parse_color_random(spec: str) -> dict:
    """``"R,G,B[,A]"``, each channel itself ``CENTER`` or ``MIN:CENTER:MAX``."""
    channels = spec.split(",")
    if len(channels) not in (3, 4):
        raise CliError(f"bad color-random {spec!r}: expected R,G,B[,A] "
                        "(each CENTER or MIN:CENTER:MAX)")
    names = ["r", "g", "b", "a"]
    return {names[i]: _parse_pva(ch) for i, ch in enumerate(channels)}


def _parse_fade(spec: str) -> dict:
    """``"FRAME[:START_SPEED[:END_SPEED]]"`` - the speeds are Effekseer
    ``EasingStart``/``EasingEnd`` enums (``-30,-20,-10,0,10,20,30`` only)."""
    parts = spec.split(":")
    if not 1 <= len(parts) <= 3:
        raise CliError(f"bad fade {spec!r}: expected FRAME[:START_SPEED[:END_SPEED]]")
    out: dict = {"frame": float(parts[0])}
    try:
        if len(parts) >= 2:
            out["start_speed"] = enums.easing_speed(parts[1], "START_SPEED")
        if len(parts) >= 3:
            out["end_speed"] = enums.easing_speed(parts[2], "END_SPEED")
    except ValueError as e:
        raise CliError(f"bad fade {spec!r}: {e}") from e
    return out


def _read_project(path: Path) -> Elem:
    if Path(path).read_bytes()[:4] == b"EFKE":
        raise CliError(f"{path} is in the compiled .efkefc format, not an XML .efkproj (the Effekseer "
                       "editor saves that format when you save from it); this toolkit can't read it")
    try:
        return xmlio.read(path)
    except Exception as e:  # noqa: BLE001
        raise CliError(f"{path} is not a readable .efkproj: {e}") from e


def _warn_missing_assets_in(node: Elem, proj_path: Path) -> None:
    """Warn (don't refuse - the file may be copied in later; `compile` refuses)
    about texture/model/sound paths in ``node`` that don't exist yet."""
    missing = assets.missing_project_assets(node, proj_path.parent)
    if missing:
        print(f"WARNING: {len(missing)} referenced file(s) don't exist relative to {proj_path.name} "
              "(`compile` will refuse until they do):\n" + assets.describe_missing(missing),
              file=sys.stderr)


# ---------------------------------------------------------------------------
# which Effekseer: target version (-> versions.Profile) and its CUI
@dataclass(frozen=True)
class Effekseer:
    version: str
    version_source: str
    profile: versions.Profile
    cui: Path | None          # as configured (a 1.80 launcher is resolved when run)
    cui_source: str | None
    detected: str | None      # version read from the CUI's EffekseerCore.dll

    @property
    def editor_version(self) -> str:
        """The editor that will actually load files: the CUI's, when known."""
        return self.detected or self.version


def version_candidates(version_arg: str | None) -> list[tuple[str, str | None]]:
    cfg = config.get()
    return [
        ("--effekseer-version", version_arg),
        ("$EFFEKSEER_VERSION", os.environ.get("EFFEKSEER_VERSION")),
        (f"effekseer.version in {cfg.config_path.name}", cfg.version or None),
    ]


def cui_candidates(cui_path_arg: str | None, version: str | None) -> list[tuple[str, str | None]]:
    """``(source label, path)`` in lookup order: ``--cui-path``, ``$EFFEKSEER_CUI``,
    ``effekseer.cui_paths`` (the entry for ``version``, then others of the same
    version family; every entry when no version is set), then
    ``effekseer.cui_path``."""
    cfg = config.get()
    out: list[tuple[str, str | None]] = [
        ("--cui-path", cui_path_arg),
        ("$EFFEKSEER_CUI", os.environ.get("EFFEKSEER_CUI")),
    ]
    entries = list(cfg.cui_paths.items())
    if version:
        entries = ([(k, v) for k, v in entries if k == version]
                   + [(k, v) for k, v in entries if k != version and versions.same_family(k, version)])
    out += [(f"effekseer.cui_paths[{k!r}] in {cfg.config_path.name}", str(v)) for k, v in entries]
    out.append((f"effekseer.cui_path in {cfg.config_path.name}", str(cfg.cui_path) if cfg.cui_path else None))
    return out


def resolve_effekseer(cui_path_arg: str | None, version_arg: str | None) -> Effekseer:
    """Target version: ``--effekseer-version``, ``$EFFEKSEER_VERSION``,
    ``effekseer.version``; if none is set, the version of the CUI found, else
    :data:`versions.FALLBACK_VERSION`. The CUI: see :func:`cui_candidates`."""
    version, version_source = next(((v, label) for label, v in version_candidates(version_arg) if v),
                                   (None, None))
    cui, cui_source = next(((Path(c), label) for label, c in cui_candidates(cui_path_arg, version)
                            if c and Path(c).is_file()), (None, None))
    detected = versions.detect_cui_version(cui) if cui is not None else None
    if version is None:
        if detected:
            version, version_source = detected, f"detected from {cui}"
        else:
            version, version_source = versions.FALLBACK_VERSION, "fallback (no version configured)"
    try:
        profile = versions.profile_for(version)
    except ValueError as e:
        raise CliError(f"{version_source}: {e}") from e
    return Effekseer(version, version_source, profile, cui, cui_source, detected)


def _cui_mismatch(eff: Effekseer) -> str | None:
    if eff.cui is not None and eff.detected and not versions.same_family(eff.detected, eff.version):
        return (f"the Effekseer CUI {eff.cui} ({eff.cui_source}) is Effekseer {eff.detected}, but the target "
                f"version is {eff.version} ({eff.version_source}). Point effekseer.cui_paths[{eff.version!r}] "
                "at that version's Effekseer.exe, or change the target version")
    return None


def _reject_write_problems(node: Elem, label: str, eff: Effekseer, tool_version: str) -> None:
    """Refuse to write a node carrying an Effekseer enum value the target
    editor would crash on (see ``enums.py``), or fields the file's
    ``ToolVersion`` makes Effekseer drop or overwrite (``versions.MIGRATIONS``).
    Catches the ``--set``/``"set"`` escape hatch, which can otherwise put
    anything in."""
    problems = enums.check_node(node, eff.profile) + versions.node_migration_problems(node, tool_version)
    if problems:
        raise CliError(f"{label}: {len(problems)} problem(s) for Effekseer {eff.version}, nothing written:\n  "
                       + "\n  ".join(problems))
    for msg in versions.node_unsupported_blocks(node, eff.profile):
        print(f"WARNING: {label}: {msg}", file=sys.stderr)


# ---------------------------------------------------------------------------
# node-path addressing
def resolve_node(project: Elem, path: str) -> Elem:
    root = project.require("Root")
    if path in ("", "root", "."):
        return root
    children = root.require("Children")
    node = None
    for part in path.split("."):
        try:
            idx = int(part)
        except ValueError as e:
            raise CliError(f"bad node path {path!r}: {part!r} is not an index") from e
        if idx < 0 or idx >= len(children.children):
            raise CliError(f"no node at index {idx} in path {path!r} "
                            f"(only {len(children.children)} children there)")
        node = children.children[idx]
        kids = node.child("Children")
        children = kids if kids is not None else Elem("Children")
    return node


def _drawing_kind(node: Elem) -> str | None:
    """The node's drawing kind, ``None`` for a node that draws nothing
    (``Type`` 0). A missing ``Type``/``DrawingValues`` is a Sprite."""
    type_val = versions.drawing_type(node)
    if type_val == 0:
        return None
    for kind, num in p.DRAWING_TYPE.items():
        if num == type_val:
            return kind
    return f"type={type_val}"


# ---------------------------------------------------------------------------
def cmd_new_project(args: argparse.Namespace) -> int:
    target_dir = Path(args.dir)
    if not target_dir.is_absolute():
        target_dir = Path.cwd() / target_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    out_path = target_dir / f"{args.name}.efkproj"
    if out_path.exists() and not args.force:
        print(f"error: {out_path} already exists (use --force)", file=sys.stderr)
        return 1

    proj = p.new_project(start_frame=args.start, end_frame=args.end, is_loop=args.loop,
                         tool_version=versions.LEGACY_TOOL_VERSION)
    xmlio.write(out_path, proj)
    print(f"created {out_path}  (ToolVersion {versions.LEGACY_TOOL_VERSION}: every Effekseer 1.5x-1.80.x "
          "opens it and migrates the toolkit's fields; `upgrade` converts it to a newer native format)")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    proj = xmlio.read(_resolve(args.file))
    root = proj.require("Root")
    print(f"Root  (StartFrame={proj.child('StartFrame').text} "
          f"EndFrame={proj.child('EndFrame').text} IsLoop={proj.child('IsLoop').text} "
          f"ToolVersion={versions.tool_version_of(proj) or '(none)'}, {versions.layout_of(proj)} CommonValues)")
    kids = root.child("Children")
    if kids:
        _print_children(kids, 1, "")
    return 0


def _print_children(children: Elem, depth: int, prefix: str) -> None:
    pad = "  " * depth
    for i, node in enumerate(children.children):
        path = f"{prefix}{i}" if prefix == "" else f"{prefix}.{i}"
        name = node.child("Name")
        name_text = name.text if name is not None else "?"
        kind = _drawing_kind(node)
        kind_str = f"  [{kind}]" if kind else ""
        print(f"{pad}[{path}] {name_text}{kind_str}")
        sub = node.child("Children")
        if sub and sub.children:
            _print_children(sub, depth + 1, path)


def cmd_validate(args: argparse.Namespace) -> int:
    path = _resolve(args.file)
    eff = resolve_effekseer(None, args.effekseer_version)
    try:
        proj = xmlio.read(path)
    except Exception as e:  # noqa: BLE001
        print(f"FAIL  not well-formed XML: {e}", file=sys.stderr)
        return 1

    problems: list[str] = []
    if proj.tag != "EffekseerProject":
        problems.append(f"root element is <{proj.tag}>, expected <EffekseerProject>")
    for required in ("Root", "ToolVersion", "Version", "StartFrame", "EndFrame", "IsLoop"):
        if proj.child(required) is None:
            problems.append(f"missing top-level <{required}>")

    root = proj.child("Root")
    node_count = 0
    unknown_kinds: set[str] = set()
    if root is not None:
        kids = root.child("Children")
        if kids is not None:
            def walk(children: Elem) -> None:
                nonlocal node_count
                for node in children.children:
                    node_count += 1
                    kind = _drawing_kind(node)
                    if kind and kind.startswith("type="):
                        unknown_kinds.add(kind)
                    sub = node.child("Children")
                    if sub:
                        walk(sub)
            walk(kids)

    for k in sorted(unknown_kinds):
        problems.append(f"unsupported DrawingValues {k} (this toolkit only models "
                         f"{sorted(p.DRAWING_TYPE)}; this may still compile fine via the "
                         "CUI, it just wasn't built by this toolkit)")
    problems.extend(enums.check_project(proj, eff.profile))
    problems.extend(versions.project_migration_problems(proj))
    too_new = versions.too_new_problem(proj, eff.editor_version)
    if too_new:
        problems.append(too_new)
    problems.extend(f"referenced file not found relative to {path.name}: {rel}"
                    + ("  (points outside the folder - likely a path from another PC)" if assets.escapes(rel) else "")
                    for rel in assets.missing_project_assets(proj, path.parent))

    for msg in versions.project_unsupported_blocks(proj, eff.profile):
        print(f"WARNING: {msg}")
    if problems:
        print(f"{len(problems)} problem(s) in {path.name} (Effekseer {eff.version}):")
        for msg in problems:
            print(f"  - {msg}")
        return 1
    print(f"OK  {path.name}  ({node_count} node(s), Effekseer {eff.version}, "
          f"{versions.layout_of(proj)} CommonValues)")
    return 0


# ---------------------------------------------------------------------------
# add-node: dedicated-flag -> presets kwargs (main/most-discoverable fields;
# anything else stays reachable via --set dotted.path=value)
_TRIGGER_NAMES = {"none": 0, "trigger0": 1, "trigger1": 257, "trigger2": 513, "trigger3": 769,
                  "parent-removed": 2, "parent-collided": 3}


def _parse_trigger(spec: str) -> int:
    """A ``TriggerType``: a name from ``_TRIGGER_NAMES`` or its raw int."""
    key = spec.strip().lower()
    if key in _TRIGGER_NAMES:
        return _TRIGGER_NAMES[key]
    try:
        return int(key)
    except ValueError:
        raise CliError(f"bad trigger {spec!r}: expected one of {sorted(_TRIGGER_NAMES)} or an int") from None


def _common_kwargs_from_args(args: argparse.Namespace) -> dict:
    kwargs: dict = {}
    if args.life is not None:
        kwargs["life"] = _parse_pva(args.life)
    if args.max_generation is not None:
        kwargs["max_generation"] = args.max_generation
    if args.infinite is not None:
        kwargs["infinite"] = args.infinite
    if args.generation_time is not None:
        kwargs["generation_time"] = _parse_pva(args.generation_time)
    if args.generation_timing is not None:
        kwargs["generation_timing"] = {"continuous": 0, "trigger": 1}[args.generation_timing]
    if args.trigger is not None:
        kwargs["trigger"] = _parse_trigger(args.trigger)
    if args.trigger_count is not None:
        kwargs["trigger_count"] = _parse_pva(args.trigger_count)
    if args.trigger_to_start is not None:
        kwargs["trigger_to_start"] = _parse_trigger(args.trigger_to_start)
    if args.trigger_to_stop is not None:
        kwargs["trigger_to_stop"] = _parse_trigger(args.trigger_to_stop)
    if args.trigger_to_remove is not None:
        kwargs["trigger_to_remove"] = _parse_trigger(args.trigger_to_remove)
    return kwargs


def _renderer_kwargs_from_args(args: argparse.Namespace) -> dict:
    kwargs: dict = {}
    if args.color_texture is not None:
        kwargs["color_texture"] = args.color_texture
    if args.fade_in is not None:
        kwargs["fade_in"] = _parse_fade(args.fade_in)
    if args.fade_out is not None:
        kwargs["fade_out"] = _parse_fade(args.fade_out)
    if args.uv_scroll is not None:
        sx, _, sy = args.uv_scroll.partition(":")
        kwargs["uv_scroll"] = {"speed": {"x": float(sx), "y": float(sy) if sy else 0.0}}
    return kwargs


def _generation_location_from_args(args: argparse.Namespace) -> Elem | None:
    if args.generation_shape is None:
        return None
    if args.generation_shape == "circle":
        return p.generation_location_circle(
            division=float(args.division) if args.division is not None else None,
            radius=_parse_pva(args.radius) if args.radius is not None else None,
            angle_start=_parse_pva(args.angle_start) if args.angle_start is not None else None,
            angle_end=_parse_pva(args.angle_end) if args.angle_end is not None else None,
        )
    if args.generation_shape == "sphere":
        return p.generation_location_sphere(
            radius=_parse_pva(args.radius) if args.radius is not None else None,
        )
    return p.generation_location_point()


def _build_drawing(args: argparse.Namespace) -> Elem:
    kind = args.kind
    if kind == "sprite":
        color_all = p.color("ColorAll_Fixed", **_parse_color(args.color)) if args.color else None
        color_all_random = (p.random_color("ColorAll_Random", **_parse_color_random(args.color_random))
                             if args.color_random else None)
        return p.drawing_values("sprite", p.sprite(
            billboard=int(args.billboard) if args.billboard is not None else 0,
            color_all=color_all, color_all_random=color_all_random,
        ))
    if kind == "ring":
        if args.color:
            c = _parse_color(args.color)
            block = p.ring(outer_color=p.color("OuterColor_Fixed", **c),
                            center_color=p.color("CenterColor_Fixed", **c),
                            inner_color=p.color("InnerColor_Fixed", **c))
        else:
            block = p.ring()
        return p.drawing_values("ring", block)
    if kind == "ribbon":
        color_all = p.color("ColorAll_Fixed", **_parse_color(args.color)) if args.color else None
        return p.drawing_values("ribbon", p.ribbon(color_all=color_all))
    if kind == "model":
        if not args.model:
            raise CliError("--kind model requires --model PATH")
        color_fixed = p.color("Color_Fixed", **_parse_color(args.color)) if args.color else None
        return p.drawing_values("model", p.model(
            model_path=args.model,
            lighting=_parse_bool(args.lighting) if args.lighting is not None else None,
            color_fixed=color_fixed,
        ))
    if kind == "track":
        if args.track_color:
            c = _parse_color(args.track_color)
            block = p.track(
                color_left=p.color("ColorLeft_Fixed", **c),
                color_left_middle=p.color("ColorLeftMiddle_Fixed", **c),
                color_center=p.color("ColorCenter_Fixed", **c),
                color_center_middle=p.color("ColorCenterMiddle_Fixed", **c),
                color_right=p.color("ColorRight_Fixed", **c),
                color_right_middle=p.color("ColorRightMiddle_Fixed", **c),
            )
        else:
            block = p.track()
        return p.drawing_values("track", block)
    raise CliError(f"unknown --kind {kind!r}")


def cmd_add_node(args: argparse.Namespace) -> int:
    path = _resolve(args.file)
    eff = resolve_effekseer(None, args.effekseer_version)
    proj = xmlio.read(path)
    layout = versions.layout_of(proj)
    parent = resolve_node(proj, args.parent)
    parent_children = parent.child_or_add("Children")

    node_kwargs: dict = {}
    common_kwargs = _common_kwargs_from_args(args)
    if common_kwargs:
        try:
            node_kwargs["common"] = p.common_values(layout=layout, **common_kwargs)
        except ValueError as e:
            raise CliError(f"add-node {args.name!r}: {e}; {path.name} has ToolVersion "
                           f"{versions.tool_version_of(proj) or '(none)'}, nothing written (`upgrade "
                           f"--effekseer-version 1.80.x` converts it)") from e
    renderer_kwargs = _renderer_kwargs_from_args(args)
    if renderer_kwargs:
        node_kwargs["renderer_common"] = p.renderer_common(**renderer_kwargs)
    gen_loc = _generation_location_from_args(args)
    if gen_loc is not None:
        node_kwargs["generation_location"] = gen_loc

    if args.kind == "group":
        new_node = p.group_node(args.name, **node_kwargs)
    else:
        new_node = p.node(args.name, drawing=_build_drawing(args), **node_kwargs)

    for assignment in args.set or []:
        key, _, value = assignment.partition("=")
        new_node.set_path(key, value)
    _reject_write_problems(new_node, f"add-node {args.name!r}", eff, versions.tool_version_of(proj))

    parent_children.children.append(new_node)
    xmlio.write(path, proj)
    idx = len(parent_children.children) - 1
    new_path = idx if args.parent in ("", "root", ".") else f"{args.parent}.{idx}"
    print(f"added [{new_path}] {args.name} ({args.kind}) under [{args.parent or 'root'}]")
    _warn_missing_assets_in(new_node, path)
    return 0


def cmd_set_params(args: argparse.Namespace) -> int:
    path = _resolve(args.file)
    eff = resolve_effekseer(None, args.effekseer_version)
    proj = xmlio.read(path)
    node = resolve_node(proj, args.path)
    for assignment in args.set or []:
        key, _, value = assignment.partition("=")
        node.set_path(key, value)
    _reject_write_problems(node, f"set-params [{args.path}]", eff, versions.tool_version_of(proj))
    xmlio.write(path, proj)
    print(f"updated [{args.path}] ({len(args.set)} field(s))")
    _warn_missing_assets_in(node, path)
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    path = _resolve(args.file)
    eff = resolve_effekseer(None, args.effekseer_version)
    ops = json.loads(Path(args.ops).read_text(encoding="utf-8"))
    proj = xmlio.read(path)
    tool_version = versions.tool_version_of(proj)
    for i, op in enumerate(ops):
        kind = op.get("op")
        if kind == "add-node":
            parent = resolve_node(proj, op.get("parent", ""))
            parent_children = parent.child_or_add("Children")
            node_kind = op["kind"]
            if node_kind == "group":
                new_node = p.group_node(op.get("name", "Node"))
            elif node_kind == "model":
                model_path = op.get("model")
                if not model_path:
                    raise CliError(f"op {i}: kind 'model' requires a 'model' path")
                new_node = p.node(op.get("name", "Node"),
                                   drawing=p.drawing_values("model", p.model(model_path=model_path)))
            elif node_kind in _KIND_BUILDERS:
                new_node = p.node(op.get("name", "Node"), drawing=_KIND_BUILDERS[node_kind]())
            else:
                raise CliError(f"op {i}: unknown kind {node_kind!r}")
            for key, value in (op.get("set") or {}).items():
                new_node.set_path(key, str(value))
            _reject_write_problems(new_node, f"op {i} (add-node)", eff, tool_version)
            parent_children.children.append(new_node)
        elif kind == "set-params":
            node = resolve_node(proj, op["path"])
            for key, value in (op.get("set") or {}).items():
                node.set_path(key, str(value))
            _reject_write_problems(node, f"op {i} (set-params [{op['path']}])", eff, tool_version)
        else:
            raise CliError(f"op {i}: unknown op {kind!r}")
    xmlio.write(path, proj)
    print(f"applied {len(ops)} op(s) to {path.name}")
    _warn_missing_assets_in(proj, path)
    return 0


# ---------------------------------------------------------------------------
# compiled .efkefc introspection (see efkefc.py)
def _read_efkefc(path: Path) -> bytes:
    data = Path(path).read_bytes()
    try:
        efkefc.read_chunks(data)
    except efkefc.EfkefcError as e:
        raise CliError(f"{path} does not look like a .efkefc ({e})") from e
    return data


def efkefc_asset_paths(path: Path) -> list[str]:
    """Every asset path a compiled ``.efkefc`` references (its ``INFO``
    chunk) - the list the runtime resolves *relative to the .efkefc's own
    directory* when the effect is loaded."""
    try:
        return efkefc.asset_paths(_read_efkefc(path))
    except efkefc.EfkefcError as e:
        raise CliError(f"{path}: {e}") from e


def _effect_binary_version(path: Path) -> int:
    data = _read_efkefc(path)
    try:
        return efkefc.bin_version(data)
    except efkefc.EfkefcError:
        return efkefc.info_version(data)


def _warn_missing_assets(efkefc_path: Path) -> list[str]:
    """Print a warning per referenced asset that is not present next to
    ``efkefc_path`` (the runtime would then render that node untextured / skip
    the model); returns the missing relative paths."""
    missing = [rel for rel in efkefc_asset_paths(efkefc_path)
               if rel and not (efkefc_path.parent / rel).exists()]
    if missing:
        print(f"WARNING: {efkefc_path.name} references {len(missing)} asset(s) that do not exist "
              f"next to it (copy them under {efkefc_path.parent} or the effect renders without them):",
              file=sys.stderr)
        for rel in missing:
            print(f"  - {rel}", file=sys.stderr)
    return missing


def _require_cui(eff: Effekseer, cui_path_arg: str | None) -> Path:
    if eff.cui is None:
        tried = "\n  ".join(f"{label}: {value or '(not set)'}"
                            for label, value in cui_candidates(cui_path_arg, eff.version))
        raise CliError(
            f"Effekseer {eff.version} CUI (Tool/Effekseer.exe) not found. Tried:\n  {tried}\n"
            f"Set effekseer.cui_paths[{eff.version!r}] in tools/effect/effect_config.json to that version's "
            "Effekseer.exe (see docs/setup.md)."
        )
    mismatch = _cui_mismatch(eff)
    if mismatch:
        raise CliError(mismatch)
    return eff.cui


def cmd_compile(args: argparse.Namespace) -> int:
    in_path = _resolve(args.file)
    out_path = _resolve(args.out) if args.out else in_path.with_suffix(".efkefc")
    if out_path.resolve().parent != in_path.resolve().parent:
        # The CUI stores every ColorTexture/Model/Wave path *relative to the
        # output file*, so compiling into another folder turns "Texture/x.png"
        # into "../<somewhere>/Texture/x.png" - a path that breaks as soon as
        # the .efkefc is moved or shipped.
        raise CliError(f"--out must be in the same folder as {in_path.name}: the CUI rewrites the "
                       "effect's texture/model paths relative to the output folder, so they would "
                       "point outside it. Compile next to the .efkproj and use `install --dest` to "
                       "ship it.")
    eff, _proj = _preflight_cui(in_path, args, "compiled")
    written = _run_cui(eff, in_path, out_path)
    print(f"compiled {out_path}  (Effekseer {eff.editor_version}, binary version {written})")
    _warn_missing_assets(out_path)
    return 0


def _preflight_cui(in_path: Path, args: argparse.Namespace, verb: str) -> tuple[Effekseer, Elem]:
    """Everything ``compile``/``upgrade`` refuse before running the CUI (which
    itself accepts all of it without an error)."""
    proj = _read_project(in_path)
    missing = assets.missing_project_assets(proj, in_path.parent)
    if missing:
        raise CliError(f"{in_path.name} references {len(missing)} texture/model/sound file(s) that "
                       f"don't exist relative to {in_path.parent}; nothing {verb} (the CUI would "
                       f"accept it anyway and the effect would render without them):\n"
                       + assets.describe_missing(missing))
    eff = resolve_effekseer(args.cui_path, args.effekseer_version)
    _require_cui(eff, args.cui_path)
    blockers = versions.project_migration_problems(proj)
    too_new = versions.too_new_problem(proj, eff.editor_version)
    if too_new:
        blockers.append(too_new)
    if blockers:
        raise CliError(f"{in_path.name}: {len(blockers)} problem(s) for Effekseer {eff.version}; nothing "
                       f"{verb} (the CUI would drop these values or refuse the file without an error):\n  "
                       + "\n  ".join(blockers))
    return eff, proj


def _run_cui(eff: Effekseer, in_path: Path, out_path: Path) -> int:
    """Run the CUI ``-in in_path -o out_path``; returns the output's binary
    version after checking it is the one ``eff`` writes."""
    if out_path.exists():
        out_path.unlink()
    result = subprocess.run(
        [str(versions.resolve_cui_exe(eff.cui)), "-cui", "-in", str(in_path.resolve()), "-o", str(out_path.resolve())],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        hint = ("" if (result.stdout + result.stderr).strip() else
                " with no output - Effekseer CUIs intermittently do that while another Effekseer "
                "process is running; retry once nothing else is running")
        raise CliError(f"CUI exited {result.returncode}{hint}:\n{result.stdout}\n{result.stderr}")
    if not out_path.exists():
        raise CliError(f"CUI exited 0 but {out_path} was not created. Its output:\n{result.stdout}\n{result.stderr}")
    try:
        written = efkefc.info_version(out_path.read_bytes())
    except efkefc.EfkefcError as e:
        raise CliError(f"{out_path} does not look like a valid .efkefc ({e})") from e
    if written != eff.profile.binary_version:
        raise CliError(f"{out_path} has binary version {written}, but Effekseer {eff.version} writes "
                       f"{eff.profile.binary_version}: the CUI {eff.cui} is not Effekseer {eff.version}")
    return written


def cmd_upgrade(args: argparse.Namespace) -> int:
    """Rewrite an ``.efkproj`` in the target editor's native format by letting
    that editor migrate it: compile to a scratch ``.efkefc`` next to it and
    keep the project XML the CUI stores in its ``EDIT`` chunk."""
    in_path = _resolve(args.file)
    out_path = _resolve(args.out) if args.out else in_path
    if out_path.resolve().parent != in_path.resolve().parent:
        raise CliError(f"--out must be in the same folder as {in_path.name}: the upgraded project's "
                       "texture/model paths are relative to that folder")
    eff, proj = _preflight_cui(in_path, args, "upgraded")
    scratch = in_path.with_name(f".{in_path.stem}.upgrade.efkefc")
    try:
        _run_cui(eff, in_path, scratch)
        upgraded = efkefc.edit_project(scratch.read_bytes())
    except efkefc.EfkefcError as e:
        raise CliError(f"could not read the migrated project back from {scratch.name}: {e}") from e
    finally:
        if scratch.exists():
            scratch.unlink()
    problems = enums.check_project(upgraded, eff.profile) + versions.project_migration_problems(upgraded)
    if problems:
        raise CliError(f"the migrated project fails the toolkit's checks, nothing written:\n  " + "\n  ".join(problems))
    xmlio.write(out_path, upgraded)
    print(f"upgraded {in_path.name} -> {out_path}  (ToolVersion {versions.tool_version_of(proj) or '(none)'} -> "
          f"{versions.tool_version_of(upgraded)}, migrated by Effekseer {eff.editor_version} itself; "
          f"{versions.layout_of(upgraded)} CommonValues)")
    return 0


def _plan_asset_copies(efkefc_src: Path, dest: Path) -> list[tuple[Path, Path]]:
    """``(from, to)`` for every file ``efkefc_src`` references that has to be
    copied next to ``dest``; raises (before anything is copied) when a path
    points outside the effect's folder, a file can't be found, or a different
    file with the same name is already installed."""
    refs = list(dict.fromkeys(r for r in efkefc_asset_paths(efkefc_src) if r))
    outside = [r for r in refs if assets.escapes(r)]
    if outside:
        raise CliError(f"{efkefc_src.name} references file(s) outside its own folder, so it was "
                       "exported into a different folder than its .efkproj; nothing installed. "
                       "Re-export/compile it into the same folder as the .efkproj:\n"
                       + "\n".join(f"  - {r}" for r in outside))
    copies: list[tuple[Path, Path]] = []
    missing: list[str] = []
    conflicts: list[str] = []
    for rel in refs:
        src, dst = efkefc_src.parent / rel, dest.parent / rel
        if not src.is_file():
            if not dst.is_file():
                missing.append(rel)
            continue
        if dst.is_file():
            if src.resolve() != dst.resolve() and not filecmp.cmp(src, dst, shallow=False):
                conflicts.append(rel)
            continue
        copies.append((src, dst))
    if missing:
        raise CliError(f"{efkefc_src.name} references file(s) found neither next to it nor next to "
                       f"--dest; nothing installed:\n" + "\n".join(f"  - {r}" for r in missing))
    if conflicts:
        raise CliError(f"a different file with the same name is already installed next to {dest.name} "
                       "(possibly used by another effect); nothing installed. Rename the texture/model "
                       "in your effect or remove the old file:\n"
                       + "\n".join(f"  - {dest.parent / r}" for r in conflicts))
    return copies


def _rebased_project(project_src: Path, efkefc_src: Path, dest: Path, source_dest: Path) -> Elem:
    """``project_src`` with every asset path rewritten to point, from
    ``source_dest``'s folder, at the copy installed next to ``dest``."""
    proj = _read_project(project_src)
    missing = assets.missing_project_assets(proj, project_src.parent)
    if missing:
        raise CliError(f"{project_src.name} references file(s) that don't exist relative to it; "
                       "nothing installed:\n" + assets.describe_missing(missing))
    try:
        for e in assets.project_asset_elems(proj):
            rel = assets.relpath_posix(project_src.parent / e.text, efkefc_src.parent)
            e.text = assets.relpath_posix(dest.parent / rel, source_dest.parent)
    except ValueError as err:  # os.path.relpath across drives
        raise CliError(f"can't express {project_src.name}'s asset paths relative to {source_dest.parent} "
                       f"({err}); nothing installed") from err
    return proj


def cmd_install(args: argparse.Namespace) -> int:
    efkefc_src = _resolve(args.efkefc)
    dest = _resolve(args.dest)
    cfg = config.get()
    try:
        dest_rel = dest.resolve().relative_to(cfg.effect_dir)
    except ValueError:
        dest_rel = Path(dest.name)

    if cfg.runtime_version:
        binary = _effect_binary_version(efkefc_src)
        limit = versions.runtime_max_binary_version(cfg.runtime_version)
        if binary > limit:
            raise CliError(f"{efkefc_src.name} has binary version {binary} (Effekseer "
                           f"{versions.binary_version_label(binary)}), but project.runtime_version is "
                           f"{cfg.runtime_version!r}, whose runtime refuses anything above {limit}; nothing "
                           "installed. Compile it with that Effekseer version instead.")
    copies = _plan_asset_copies(efkefc_src, dest)
    project = None
    if args.project:
        project_src = _resolve(args.project)
        source_dest = cfg.effect_dir / cfg.source_subdir / dest_rel.with_suffix(".efkproj")
        project = _rebased_project(project_src, efkefc_src, dest, source_dest)

    dest.parent.mkdir(parents=True, exist_ok=True)
    if efkefc_src.resolve() != dest.resolve():
        shutil.copyfile(efkefc_src, dest)
    for src, dst in copies:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        print(f"copied asset  {dst}")
    _warn_missing_assets(dest)

    if project is not None:
        source_dest.parent.mkdir(parents=True, exist_ok=True)
        xmlio.write(source_dest, project)
        print(f"copied source {source_dest} (asset paths point at the installed files)")
        unresolved = assets.missing_project_assets(project, source_dest.parent)
        if unresolved:
            print(f"WARNING: {source_dest.name} references file(s) the compiled effect doesn't use, "
                  "so they were not installed:\n" + assets.describe_missing(unresolved), file=sys.stderr)

    if not cfg.meta_enabled:
        print(f"installed {dest}")
        print("          (no .meta: meta.enabled is false in effect_config.json)")
        return 0

    name = dest.stem
    meta_path = dest.with_suffix(dest.suffix + ".meta")
    if meta_path.exists():
        # Re-installing over an asset that is already wired into prefabs /
        # components: keep its .meta (and so its GUID) untouched so every
        # existing reference stays valid. Only a brand-new asset gets a
        # freshly minted GUID.
        guid = meta_mod.read_meta(meta_path)["guid"]
        print(f"installed {dest}")
        print(f"          {meta_path.name} (existing, kept)")
        print(f"GUID:     {guid}  (reused)")
        return 0

    guid = meta_mod.mint_guid()
    content_path = meta_mod.content_path_for(name, dest.parent, cfg.project_root)
    meta_mod.write_meta(meta_path, name, guid, content_path)

    print(f"installed {dest}")
    print(f"          {meta_path.name}")
    print(f"GUID:     {guid}")
    return 0


def cmd_check_env(args: argparse.Namespace) -> int:
    cfg = config.get()
    eff = resolve_effekseer(args.cui_path, args.effekseer_version)

    def exists(path: Path | None) -> str:
        if path is None:
            return "(not set)"
        return f"{path}  [{'found' if path.exists() else 'NOT FOUND'}]"

    print(f"config:            {cfg.config_path}")
    print(f"project root:      {exists(cfg.project_root)}")
    print(f"target version:    Effekseer {eff.version}  ({eff.version_source})")
    for label, value in version_candidates(args.effekseer_version):
        print(f"  - {label}: {value or '(not set)'}")
    print(f"  -> Effekseer {eff.profile.family} enum domains, compiled binary version {eff.profile.binary_version}")
    print(f"Effekseer CUI:     {exists(eff.cui) if eff.cui else '(not found)'}"
          + (f"  ({eff.cui_source})" if eff.cui else ""))
    for label, value in cui_candidates(args.cui_path, eff.version):
        print(f"  - {label}: {value or '(not set)'}")
    if eff.cui is not None:
        print(f"  -> runs {versions.resolve_cui_exe(eff.cui)}")
        print(f"  -> CUI version: {eff.detected or '(could not detect)'}")
    print(f"effect dir:        {exists(cfg.effect_dir)}")
    print(f"source subdir:     {cfg.source_subdir}")
    print(f"runtime version:   " + (f"{cfg.runtime_version} (install refuses binary versions above "
                                    f"{versions.runtime_max_binary_version(cfg.runtime_version)})"
                                    if cfg.runtime_version else "(not set; install doesn't check)"))
    print(f".meta output:      {'on (' + cfg.meta_asset_type + ')' if cfg.meta_enabled else 'off'}")
    corpus = os.environ.get("EFFEKSEER_CORPUS")
    print(f"selftest corpus:   {exists(Path(corpus) if corpus else cfg.corpus_dir)}")

    if eff.cui is None:
        print(f"\nerror: Effekseer {eff.version} CUI not found - set effekseer.cui_paths[{eff.version!r}] in "
              f"{cfg.config_path.name} to its Effekseer.exe (see docs/setup.md)", file=sys.stderr)
        return 1
    mismatch = _cui_mismatch(eff)
    if mismatch:
        print(f"\nerror: {mismatch}", file=sys.stderr)
        return 1
    if cfg.runtime_version and eff.profile.binary_version > versions.runtime_max_binary_version(cfg.runtime_version):
        print(f"\nWARNING: effects compiled with Effekseer {eff.version} (binary version "
              f"{eff.profile.binary_version}) can't be loaded by the project's runtime "
              f"({cfg.runtime_version}); install will refuse them.", file=sys.stderr)
    if not eff.detected:
        print(f"\nOK, but the CUI's version could not be detected; make sure it is Effekseer {eff.version} "
              "(see docs/setup.md).")
        return 0
    print("\nOK.")
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    from . import export
    try:
        export.export(Path(args.out), verbose=True)
    except export.ExportError as e:
        raise CliError(str(e)) from e
    return 0


# ---------------------------------------------------------------------------
def _wrap(fn):
    def run(args: argparse.Namespace) -> int:
        try:
            return fn(args)
        except (CliError, config.ConfigError) as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
    return run


def register(sub: argparse._SubParsersAction) -> None:
    sp = sub.add_parser("new-project", help="create a new .efkproj skeleton")
    sp.add_argument("name")
    sp.add_argument("--dir", default=".", help="target directory (default: cwd)")
    sp.add_argument("--start", type=int, default=0)
    sp.add_argument("--end", type=int, default=60)
    sp.add_argument("--loop", type=lambda s: s.lower() == "true", default=True, metavar="true|false")
    sp.add_argument("--force", action="store_true")
    sp.add_argument("--effekseer-version", default=None, metavar="VERSION",
                     help="target Effekseer version (e.g. 1.7.3.0, 1.80.7) instead of "
                          "$EFFEKSEER_VERSION / effekseer.version in effect_config.json")
    sp.set_defaults(func=_wrap(cmd_new_project))

    sp = sub.add_parser("show", help="print a .efkproj node tree as an outline")
    sp.add_argument("file")
    sp.set_defaults(func=_wrap(cmd_show))

    sp = sub.add_parser("validate", help="structural sanity checks")
    sp.add_argument("file")
    sp.add_argument("--effekseer-version", default=None, metavar="VERSION",
                     help="target Effekseer version (e.g. 1.7.3.0, 1.80.7) instead of "
                          "$EFFEKSEER_VERSION / effekseer.version in effect_config.json")
    sp.set_defaults(func=_wrap(cmd_validate))

    sp = sub.add_parser("add-node", help="add a node under an existing node/root")
    sp.add_argument("file")
    sp.add_argument("--parent", default="", help='node path, e.g. "1.0" (default: root)')
    sp.add_argument("--kind", required=True,
                     choices=["sprite", "ring", "ribbon", "model", "track", "group"])
    sp.add_argument("--name", default="Node")
    # CommonValues
    sp.add_argument("--life", default=None, metavar="CENTER|MIN:CENTER:MAX")
    sp.add_argument("--max-generation", type=int, default=None)
    sp.add_argument("--infinite", type=_parse_bool, default=None, metavar="true|false")
    sp.add_argument("--generation-time", default=None, metavar="CENTER|MIN:CENTER:MAX")
    sp.add_argument("--trigger-to-start", default=None, metavar="TRIGGER",
                     help="none|trigger0..3 (+ parent-removed|parent-collided on 1.80) or an int")
    sp.add_argument("--trigger-to-stop", default=None, metavar="TRIGGER")
    sp.add_argument("--trigger-to-remove", default=None, metavar="TRIGGER")
    sp.add_argument("--generation-timing", choices=["continuous", "trigger"], default=None,
                     help="Effekseer 1.80 files (ToolVersion 1.80+) only")
    sp.add_argument("--trigger", default=None, metavar="TRIGGER",
                     help="trigger that generates particles (--generation-timing trigger; 1.80 files only)")
    sp.add_argument("--trigger-count", default=None, metavar="CENTER|MIN:CENTER:MAX",
                     help="particles per trigger (1.80 files only)")
    # RendererCommonValues
    sp.add_argument("--color-texture", default=None, metavar="PATH")
    sp.add_argument("--fade-in", default=None, metavar="FRAME[:START_SPEED[:END_SPEED]]",
                     help="speeds are Effekseer easing enums: -30,-20,-10,0,10,20,30 only")
    sp.add_argument("--fade-out", default=None, metavar="FRAME[:START_SPEED[:END_SPEED]]",
                     help="speeds are Effekseer easing enums: -30,-20,-10,0,10,20,30 only")
    sp.add_argument("--uv-scroll", default=None, metavar="SPEED_X:SPEED_Y")
    # GenerationLocationValues
    sp.add_argument("--generation-shape", choices=["circle", "sphere", "point"], default=None)
    sp.add_argument("--radius", default=None, metavar="CENTER|MIN:CENTER:MAX (circle/sphere)")
    sp.add_argument("--division", default=None, metavar="N (circle)")
    sp.add_argument("--angle-start", default=None, metavar="CENTER|MIN:CENTER:MAX (circle)")
    sp.add_argument("--angle-end", default=None, metavar="CENTER|MIN:CENTER:MAX (circle)")
    # kind-specific
    sp.add_argument("--billboard", default=None, metavar="N (sprite)")
    sp.add_argument("--color", default=None, metavar="R:G:B[:A] (sprite/ribbon/ring/model)")
    sp.add_argument("--color-random", default=None,
                     metavar="R,G,B[,A] (sprite; each CENTER|MIN:CENTER:MAX)")
    sp.add_argument("--model", default=None, metavar="PATH (required for --kind model)")
    sp.add_argument("--lighting", default=None, metavar="true|false (model)")
    sp.add_argument("--track-color", default=None,
                     metavar="R:G:B[:A] (track; applies to all 6 rails)")
    sp.add_argument("--set", action="append", metavar="dotted.path=value",
                     help="may be repeated; escape hatch for anything not covered above")
    sp.add_argument("--effekseer-version", default=None, metavar="VERSION",
                     help="target Effekseer version (e.g. 1.7.3.0, 1.80.7) instead of "
                          "$EFFEKSEER_VERSION / effekseer.version in effect_config.json")
    sp.set_defaults(func=_wrap(cmd_add_node))

    sp = sub.add_parser("set-params", help="set fields on an existing node")
    sp.add_argument("file")
    sp.add_argument("--path", required=True, help='node path, e.g. "1.0"')
    sp.add_argument("--set", action="append", required=True, metavar="dotted.path=value")
    sp.add_argument("--effekseer-version", default=None, metavar="VERSION",
                     help="target Effekseer version (e.g. 1.7.3.0, 1.80.7) instead of "
                          "$EFFEKSEER_VERSION / effekseer.version in effect_config.json")
    sp.set_defaults(func=_wrap(cmd_set_params))

    sp = sub.add_parser("apply", help="apply a batch of ops from a JSON file")
    sp.add_argument("file")
    sp.add_argument("ops", help="path to a JSON list of {op, ...} objects")
    sp.add_argument("--effekseer-version", default=None, metavar="VERSION",
                     help="target Effekseer version (e.g. 1.7.3.0, 1.80.7) instead of "
                          "$EFFEKSEER_VERSION / effekseer.version in effect_config.json")
    sp.set_defaults(func=_wrap(cmd_apply))

    sp = sub.add_parser("compile", help="compile .efkproj -> .efkefc via the Effekseer CUI")
    sp.add_argument("file")
    sp.add_argument("--out", default=None, help="output path (default: FILE with .efkefc)")
    sp.add_argument("--cui-path", default=None,
                     help="Effekseer.exe to use instead of effekseer.cui_paths in effect_config.json")
    sp.add_argument("--effekseer-version", default=None, metavar="VERSION",
                     help="target Effekseer version (e.g. 1.7.3.0, 1.80.7) instead of "
                          "$EFFEKSEER_VERSION / effekseer.version in effect_config.json")
    sp.set_defaults(func=_wrap(cmd_compile))

    sp = sub.add_parser("upgrade", help="convert a .efkproj to the target Effekseer version's native format "
                                        "(the CUI migrates it; needed for 1.80-only CommonValues settings)")
    sp.add_argument("file")
    sp.add_argument("--out", default=None, help="output path in the same folder (default: overwrite FILE)")
    sp.add_argument("--cui-path", default=None,
                     help="Effekseer.exe to use instead of effekseer.cui_paths in effect_config.json")
    sp.add_argument("--effekseer-version", default=None, metavar="VERSION",
                     help="target Effekseer version (e.g. 1.7.3.0, 1.80.7) instead of "
                          "$EFFEKSEER_VERSION / effekseer.version in effect_config.json")
    sp.set_defaults(func=_wrap(cmd_upgrade))

    sp = sub.add_parser("install", help="copy a compiled .efkefc into the project's effect dir "
                                        "(+ .meta when meta.enabled)")
    sp.add_argument("efkefc", help="compiled .efkefc to install")
    sp.add_argument("--project", default=None,
                     help="source .efkproj to also copy under <project.effect_dir>/<project.source_subdir>/")
    sp.add_argument("--dest", required=True, help="e.g. <project.effect_dir>/MyPack/Spark.efkefc")
    sp.set_defaults(func=_wrap(cmd_install))

    sp = sub.add_parser("check-env", help="print the resolved effect_config.json settings and "
                                          "check that the Effekseer CUI exists")
    sp.add_argument("--cui-path", default=None,
                     help="Effekseer.exe to use instead of effekseer.cui_paths in effect_config.json")
    sp.add_argument("--effekseer-version", default=None, metavar="VERSION",
                     help="target Effekseer version (e.g. 1.7.3.0, 1.80.7) instead of "
                          "$EFFEKSEER_VERSION / effekseer.version in effect_config.json")
    sp.set_defaults(func=_wrap(cmd_check_env))

    sp = sub.add_parser("export", help="copy the distributable toolkit files into another directory "
                                       "(e.g. the EffekseerEfkprojTool repository)")
    sp.add_argument("--out", required=True, help="destination directory (must be outside this project)")
    sp.set_defaults(func=_wrap(cmd_export))
