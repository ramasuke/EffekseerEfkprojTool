"""``export`` - copy the distributable subset of the toolkit into another
directory (the public EffekseerEfkprojTool repository's working tree).

NanamiEngine stays the source of truth: edit here, export, then commit/push in
the destination. ``MANIFEST`` is the single list of what ships; the
project-specific ``effect_config.json`` is replaced by ``dist/effect_config.json``
(no personal paths, ``.meta`` output off) and ``dist/`` also provides the
repository's user documentation (README.md, docs/*.md), LICENSE and .gitignore.
``tools/effect/README.md`` is this project's internal reference and is not
shipped.
"""

from __future__ import annotations

import shutil
from pathlib import Path

_SRC_ROOT = Path(__file__).resolve().parents[2]
_DIST = "tools/effect/dist"

# (path in the exported tree, source path relative to this project's root)
MANIFEST: list[tuple[str, str]] = [
    ("README.md", f"{_DIST}/README.md"),
    *[(f"docs/{n}.md", f"{_DIST}/docs/{n}.md") for n in (
        "setup", "usage", "versions", "troubleshooting", "development",
    )],
    ("LICENSE", f"{_DIST}/LICENSE"),
    (".gitignore", f"{_DIST}/.gitignore"),
    ("tools/effect.py", "tools/effect.py"),
    *[(f"tools/effect/{n}", f"tools/effect/{n}") for n in (
        "__init__.py", "__main__.py", "assets.py", "cli.py", "config.py", "efkefc.py", "enums.py",
        "export.py", "meta.py", "model.py", "presets.py", "selftest.py", "versions.py", "xmlio.py",
    )],
    ("tools/effect/effect_config.json", f"{_DIST}/effect_config.json"),
    *[(f"tools/effect/testdata/{n}.efkproj", f"tools/effect/testdata/{n}.efkproj") for n in (
        "actionLines_shockwave", "smallTexturesRibbon", "drill",
        "blue_laser", "Gohlem1", "Sylph2", "Water_Impact",
    )],
    *[(f"tools/common/{n}", f"tools/common/{n}") for n in (
        "__init__.py", "cereal_json.py", "meta_base.py",
    )],
]


class ExportError(RuntimeError):
    pass


def export(out_dir: Path, verbose: bool) -> list[Path]:
    out_dir = Path(out_dir).resolve()
    try:
        out_dir.relative_to(_SRC_ROOT)
    except ValueError:
        pass
    else:
        raise ExportError(f"--out {out_dir} is inside {_SRC_ROOT}; export to a directory outside this project")

    missing = [src for _, src in MANIFEST if not (_SRC_ROOT / src).is_file()]
    if missing:
        raise ExportError("source file(s) missing, nothing exported:\n  " + "\n  ".join(missing))

    written: list[Path] = []
    for dest_rel, src_rel in MANIFEST:
        dest = out_dir / dest_rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(_SRC_ROOT / src_rel, dest)
        written.append(dest)
        if verbose:
            print(f"  {dest_rel}")

    shipped = {out_dir / d for d, _ in MANIFEST}
    stray = sorted(p for p in (out_dir / "tools").rglob("*")
                   if p.is_file() and p not in shipped and "__pycache__" not in p.parts)
    if verbose:
        print(f"exported {len(written)} file(s) to {out_dir}")
        if stray:
            print(f"WARNING: {len(stray)} file(s) under {out_dir / 'tools'} are not in the export "
                  "manifest (removed or renamed upstream?):")
            for p in stray:
                print(f"  - {p.relative_to(out_dir).as_posix()}")
    return written
