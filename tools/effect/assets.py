"""Asset references (textures, models, materials, sounds) inside effects.

Effekseer stores every such reference as a path *relative to the file that
holds it*: relative to the ``.efkproj`` in the source, and relative to the
output file in a compiled ``.efkefc`` (the CUI / editor rewrites them on
export). Three ways that goes wrong, all guarded against by the toolkit:

1. compiling/exporting into another directory than the ``.efkproj`` leaves
   paths that point outside the ``.efkefc``'s folder (``../OneDrive/...``);
2. copying an ``.efkproj`` somewhere else without rewriting its paths;
3. sample projects still carrying their author's local paths.

The CUI compiles all of these without an error, so ``compile`` / ``install``
check them up front instead.
"""

from __future__ import annotations

import os
from pathlib import Path, PurePosixPath

from .model import Elem

ASSET_EXTS = ("png", "jpg", "jpeg", "bmp", "tga", "dds", "efkmodel", "efkmat", "efkcurve", "wav")

_NOT_ASSET_TAGS = {"Name"}


def is_asset_path(text: str | None) -> bool:
    return bool(text) and text.strip().lower().endswith(tuple("." + e for e in ASSET_EXTS))


def project_asset_elems(proj: Elem) -> list[Elem]:
    """Every leaf in an ``.efkproj`` tree whose text is an asset path."""
    found: list[Elem] = []

    def walk(e: Elem) -> None:
        if e.children:
            for c in e.children:
                walk(c)
        elif e.tag not in _NOT_ASSET_TAGS and is_asset_path(e.text):
            found.append(e)

    walk(proj)
    return found


def missing_project_assets(proj: Elem, proj_dir: Path) -> list[str]:
    """Asset paths (deduplicated, in file order) that don't resolve from ``proj_dir``."""
    missing: list[str] = []
    for e in project_asset_elems(proj):
        if e.text not in missing and not (Path(proj_dir) / e.text).is_file():
            missing.append(e.text)
    return missing


def escapes(rel: str) -> bool:
    """True for an absolute path or one that leaves its base folder (``../x``)."""
    p = rel.replace("\\", "/")
    if PurePosixPath(p).is_absolute() or (len(p) > 1 and p[1] == ":"):
        return True
    return os.path.normpath(p).replace("\\", "/").split("/")[0] == ".."


def relpath_posix(target: Path, start: Path) -> str:
    return os.path.relpath(Path(target).resolve(), Path(start).resolve()).replace("\\", "/")


def describe_missing(paths: list[str]) -> str:
    lines = []
    for rel in paths:
        hint = ("  (points outside the folder - likely a path left over from another PC, e.g. "
                "a sample pack author's; put the file near the .efkproj and fix the path)"
                if escapes(rel) else "")
        lines.append(f"  - {rel}{hint}")
    return "\n".join(lines)
