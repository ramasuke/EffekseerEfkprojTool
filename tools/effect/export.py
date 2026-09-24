"""``export`` - ツールキットのうち配布する部分を別ディレクトリ (公開リポジトリ
EffekseerEfkprojTool の作業ツリー) にコピーする。

正本は NanamiEngine のまま: ここで編集して export し、コピー先で commit/push する。
配布物の一覧は ``MANIFEST`` だけ。プロジェクト固有の ``effect_config.json`` は
``dist/effect_config.json`` (個人的なパス無し、``.meta`` 出力オフ) に置き換わり、
``dist/`` はリポジトリのユーザー向けドキュメント (README.md、docs/*.md)、LICENSE、
.gitignore も提供する。``tools/effect/README.md`` はこのプロジェクト内部の
リファレンスなので配布しない。
"""

from __future__ import annotations

import shutil
from pathlib import Path

_SRC_ROOT = Path(__file__).resolve().parents[2]
_DIST = "tools/effect/dist"

# (書き出し先ツリーでのパス、このプロジェクトのルートからの元パス)
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
