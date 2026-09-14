"""CLI subcommands for tools.effect: new-project, show, validate, add-node,
set-params, apply, compile, install, check-env, export.

Nodes have no stable id in the ``.efkproj`` format (unlike ``tools/bt``'s
per-node GUIDs), so ``--parent``/``--path`` address a node by a dot-separated
0-based child-index path from the root, e.g. ``"1.0"`` = the root's 2nd child
node's 1st child node. ``""`` (or ``"root"``) means the root itself - use it
as ``--parent`` to attach a new top-level node. ``show`` prints these paths.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import struct
import subprocess
import sys
from pathlib import Path

from . import config
from . import enums
from . import meta as meta_mod
from . import presets as p
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


def _reject_enum_violations(node: Elem, label: str) -> None:
    """Refuse to write a node carrying an Effekseer enum value the editor
    would crash on (see ``enums.py``). Catches the ``--set``/``"set"`` escape
    hatch, which can otherwise put any int into an enum-typed leaf."""
    problems = enums.check_node(node)
    if problems:
        raise CliError(f"{label}: {len(problems)} Effekseer enum-domain violation(s), nothing written:\n  "
                       + "\n  ".join(problems))


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
    dv = node.child("DrawingValues")
    if dv is None:
        return None
    t = dv.child("Type")
    type_val = t.text if t is not None else "0"
    for kind, num in p.DRAWING_TYPE.items():
        if str(num) == type_val:
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

    proj = p.new_project(start_frame=args.start, end_frame=args.end, is_loop=args.loop)
    xmlio.write(out_path, proj)
    print(f"created {out_path}")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    proj = xmlio.read(_resolve(args.file))
    root = proj.require("Root")
    print(f"Root  (StartFrame={proj.child('StartFrame').text} "
          f"EndFrame={proj.child('EndFrame').text} IsLoop={proj.child('IsLoop').text})")
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
    problems.extend(enums.check_project(proj))

    if problems:
        print(f"{len(problems)} problem(s) in {path.name}:")
        for msg in problems:
            print(f"  - {msg}")
        return 1
    print(f"OK  {path.name}  ({node_count} node(s))")
    return 0


# ---------------------------------------------------------------------------
# add-node: dedicated-flag -> presets kwargs (main/most-discoverable fields;
# anything else stays reachable via --set dotted.path=value)
def _common_kwargs_from_args(args: argparse.Namespace) -> dict:
    kwargs: dict = {}
    if args.life is not None:
        kwargs["life"] = _parse_pva(args.life)
    if args.max_generation is not None:
        kwargs["max_generation"] = args.max_generation
    if args.infinite is not None:
        kwargs["infinite"] = args.infinite
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
    proj = xmlio.read(path)
    parent = resolve_node(proj, args.parent)
    parent_children = parent.child_or_add("Children")

    node_kwargs: dict = {}
    common_kwargs = _common_kwargs_from_args(args)
    if common_kwargs:
        node_kwargs["common"] = p.common_values(**common_kwargs)
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
    _reject_enum_violations(new_node, f"add-node {args.name!r}")

    parent_children.children.append(new_node)
    xmlio.write(path, proj)
    idx = len(parent_children.children) - 1
    new_path = idx if args.parent in ("", "root", ".") else f"{args.parent}.{idx}"
    print(f"added [{new_path}] {args.name} ({args.kind}) under [{args.parent or 'root'}]")
    return 0


def cmd_set_params(args: argparse.Namespace) -> int:
    path = _resolve(args.file)
    proj = xmlio.read(path)
    node = resolve_node(proj, args.path)
    for assignment in args.set or []:
        key, _, value = assignment.partition("=")
        node.set_path(key, value)
    _reject_enum_violations(node, f"set-params [{args.path}]")
    xmlio.write(path, proj)
    print(f"updated [{args.path}] ({len(args.set)} field(s))")
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    path = _resolve(args.file)
    ops = json.loads(Path(args.ops).read_text(encoding="utf-8"))
    proj = xmlio.read(path)
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
            _reject_enum_violations(new_node, f"op {i} (add-node)")
            parent_children.children.append(new_node)
        elif kind == "set-params":
            node = resolve_node(proj, op["path"])
            for key, value in (op.get("set") or {}).items():
                node.set_path(key, str(value))
            _reject_enum_violations(node, f"op {i} (set-params [{op['path']}])")
        else:
            raise CliError(f"op {i}: unknown op {kind!r}")
    xmlio.write(path, proj)
    print(f"applied {len(ops)} op(s) to {path.name}")
    return 0


# ---------------------------------------------------------------------------
# compiled .efkefc introspection
_ASSET_EXT_RE = re.compile(r"[^\x00]+?\.(?:png|jpg|jpeg|bmp|tga|dds|efkmodel|efkmat|efkcurve|wav)",
                           re.IGNORECASE)


def efkefc_asset_paths(path: Path) -> list[str]:
    """Every asset path (textures, models, materials, sounds) a compiled
    ``.efkefc`` references, read from its ``INFO`` chunk - the list the
    runtime resolves *relative to the .efkefc's own directory* when the effect
    is loaded (``Effect::GetColorImagePath()`` etc.). Order is the chunk's.

    The chunk is ``int32 version`` followed by string lists, each ``int32
    count`` then ``count`` x (``int32 length`` + UTF-16LE chars incl. NUL);
    parsed that way when it reads cleanly to the end, else falls back to
    scanning the UTF-16 text for asset-looking paths (so an unfamiliar chunk
    layout degrades to a best-effort list rather than an error).
    """
    raw = Path(path).read_bytes()
    i = raw.find(b"INFO")
    if not raw.startswith(b"EFKE") or i < 0:
        raise CliError(f"{path} does not look like a .efkefc (no EFKE/INFO header)")
    size = struct.unpack_from("<i", raw, i + 4)[0]
    chunk = raw[i + 8:i + 8 + size]

    paths: list[str] = []
    off = 4  # skip version
    try:
        while off < len(chunk):
            count = struct.unpack_from("<i", chunk, off)[0]
            off += 4
            if not 0 <= count <= 4096:
                raise ValueError("implausible list count")
            for _ in range(count):
                n = struct.unpack_from("<i", chunk, off)[0]
                off += 4
                if not 0 <= n <= 4096 or off + n * 2 > len(chunk):
                    raise ValueError("implausible string length")
                paths.append(chunk[off:off + n * 2].decode("utf-16-le").rstrip("\x00"))
                off += n * 2
        return paths
    except (ValueError, struct.error):
        text = chunk[4:].decode("utf-16-le", errors="ignore")
        return [m.group(0).strip() for m in _ASSET_EXT_RE.finditer(text)]


def _warn_missing_assets(efkefc: Path) -> list[str]:
    """Print a warning per referenced asset that is not present next to
    ``efkefc`` (the runtime would then render that node untextured / skip the
    model); returns the missing relative paths."""
    missing = [rel for rel in efkefc_asset_paths(efkefc)
               if rel and not (efkefc.parent / rel).exists()]
    if missing:
        print(f"WARNING: {efkefc.name} references {len(missing)} asset(s) that do not exist "
              f"next to it (copy them under {efkefc.parent} or the effect renders without them):",
              file=sys.stderr)
        for rel in missing:
            print(f"  - {rel}", file=sys.stderr)
    return missing


def cui_candidates(cui_path_arg: str | None) -> list[tuple[str, str | None]]:
    """``(source label, path)`` in lookup order: ``--cui-path``, ``$EFFEKSEER_CUI``,
    then ``effekseer.cui_path`` in ``effect_config.json``."""
    cfg = config.get()
    return [
        ("--cui-path", cui_path_arg),
        ("$EFFEKSEER_CUI", os.environ.get("EFFEKSEER_CUI")),
        (f"effekseer.cui_path in {cfg.config_path}", str(cfg.cui_path) if cfg.cui_path else None),
    ]


def find_cui(cui_path_arg: str | None) -> Path | None:
    for _, candidate in cui_candidates(cui_path_arg):
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    return None


def _find_cui_path(args: argparse.Namespace) -> Path:
    cui = find_cui(args.cui_path)
    if cui is not None:
        return cui
    tried = "\n  ".join(f"{label}: {value or '(not set)'}" for label, value in cui_candidates(args.cui_path))
    raise CliError(
        f"Effekseer CUI (Tool/Effekseer.exe) not found. Tried:\n  {tried}\n"
        "Set effekseer.cui_path in tools/effect/effect_config.json to your Effekseer.exe "
        f"(this toolkit is verified with Effekseer {config.get().verified_version}; "
        "see tools/effect/SETUP.md)."
    )


def cmd_compile(args: argparse.Namespace) -> int:
    in_path = _resolve(args.file)
    out_path = _resolve(args.out) if args.out else in_path.with_suffix(".efkefc")
    cui = _find_cui_path(args)
    if out_path.resolve().parent != in_path.resolve().parent:
        # The CUI stores every ColorTexture/Model/Wave path *relative to the
        # output file*, so compiling straight into Assets/Art/Effect/<Sub>/
        # from _Source/<Sub>/ turns "Texture/x.png" into
        # "../_Source/<Sub>/Texture/x.png" - the effect then depends on the
        # _Source tree at runtime instead of the textures shipped next to it.
        print(f"WARNING: --out is in a different directory than {in_path.name}; the CUI will "
              "rewrite the effect's asset paths relative to that directory. Compile next to "
              "the .efkproj and use `install --dest` to ship it instead.", file=sys.stderr)

    result = subprocess.run(
        [str(cui), "-cui", "-in", str(in_path), "-o", str(out_path)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"CUI exited {result.returncode}", file=sys.stderr)
        print(result.stdout, file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        return 1
    if not out_path.exists():
        print(f"CUI exited 0 but {out_path} was not created", file=sys.stderr)
        return 1
    header = out_path.read_bytes()[:16]
    if not header.startswith(b"EFKE") or b"INFO" not in header:
        print(f"{out_path} does not look like a valid .efkefc (header {header!r})", file=sys.stderr)
        return 1
    print(f"compiled {out_path}")
    _warn_missing_assets(out_path)
    return 0


def cmd_install(args: argparse.Namespace) -> int:
    efkefc_src = _resolve(args.efkefc)
    dest = _resolve(args.dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(efkefc_src, dest)
    _warn_missing_assets(dest)

    cfg = config.get()
    try:
        rel = dest.resolve().relative_to(cfg.effect_dir)
    except ValueError:
        rel = Path(dest.name)

    if args.project:
        project_src = _resolve(args.project)
        source_dest = cfg.effect_dir / cfg.source_subdir / rel.with_suffix(".efkproj")
        source_dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(project_src, source_dest)
        print(f"copied source {source_dest}")

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
    cui = find_cui(args.cui_path)

    def exists(path: Path | None) -> str:
        if path is None:
            return "(not set)"
        return f"{path}  [{'found' if path.exists() else 'NOT FOUND'}]"

    print(f"config:           {cfg.config_path}")
    print(f"project root:     {exists(cfg.project_root)}")
    print(f"Effekseer CUI:    {exists(cui) if cui else '(not found)'}")
    for label, value in cui_candidates(args.cui_path):
        print(f"  - {label}: {value or '(not set)'}")
    print(f"verified version: Effekseer {cfg.verified_version}")
    print(f"effect dir:       {exists(cfg.effect_dir)}")
    print(f"source subdir:    {cfg.source_subdir}")
    print(f".meta output:     {'on (' + cfg.meta_asset_type + ')' if cfg.meta_enabled else 'off'}")
    corpus = os.environ.get("EFFEKSEER_CORPUS")
    print(f"selftest corpus:  {exists(Path(corpus) if corpus else cfg.corpus_dir)}")

    if cui is None:
        print("\nerror: Effekseer CUI not found - set effekseer.cui_path in "
              f"{cfg.config_path.name} to your Effekseer.exe (see tools/effect/SETUP.md)", file=sys.stderr)
        return 1
    print(f"\nOK. Using an Effekseer version other than {cfg.verified_version} may cause errors "
          "when the generated effects are loaded (see tools/effect/SETUP.md).")
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
    sp.set_defaults(func=_wrap(cmd_new_project))

    sp = sub.add_parser("show", help="print a .efkproj node tree as an outline")
    sp.add_argument("file")
    sp.set_defaults(func=_wrap(cmd_show))

    sp = sub.add_parser("validate", help="structural sanity checks")
    sp.add_argument("file")
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
    sp.set_defaults(func=_wrap(cmd_add_node))

    sp = sub.add_parser("set-params", help="set fields on an existing node")
    sp.add_argument("file")
    sp.add_argument("--path", required=True, help='node path, e.g. "1.0"')
    sp.add_argument("--set", action="append", required=True, metavar="dotted.path=value")
    sp.set_defaults(func=_wrap(cmd_set_params))

    sp = sub.add_parser("apply", help="apply a batch of ops from a JSON file")
    sp.add_argument("file")
    sp.add_argument("ops", help="path to a JSON list of {op, ...} objects")
    sp.set_defaults(func=_wrap(cmd_apply))

    sp = sub.add_parser("compile", help="compile .efkproj -> .efkefc via the Effekseer CUI")
    sp.add_argument("file")
    sp.add_argument("--out", default=None, help="output path (default: FILE with .efkefc)")
    sp.add_argument("--cui-path", default=None,
                     help="Effekseer.exe to use instead of effekseer.cui_path in effect_config.json")
    sp.set_defaults(func=_wrap(cmd_compile))

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
                     help="Effekseer.exe to use instead of effekseer.cui_path in effect_config.json")
    sp.set_defaults(func=_wrap(cmd_check_env))

    sp = sub.add_parser("export", help="copy the distributable toolkit files into another directory "
                                       "(e.g. the EffekseerEfkprojTool repository)")
    sp.add_argument("--out", required=True, help="destination directory (must be outside this project)")
    sp.set_defaults(func=_wrap(cmd_export))
