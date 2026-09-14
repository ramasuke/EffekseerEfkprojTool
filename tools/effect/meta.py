"""``.efkefc.meta`` sidecar files.

A ``.meta`` is a cereal-JSON ``std::shared_ptr<AssetBase>`` holding the
``ParticleFile`` asset: a stable ``guid_`` (what a component's particle-effect
field references) plus ``contentPath_`` back to the compiled ``.efkefc``.
Written by ``File::OnSave()`` in the engine; reproduced here so ``install``
yields an asset the editor/prefabs can bind to immediately.

Thin binding of the generic :mod:`tools.common.meta_base` codec for the
``ParticleFile`` asset type - see that module for the format notes, and
``tools/bt/meta.py`` / ``tools/scene/meta.py`` for the same pattern applied
to other asset types.
"""

from __future__ import annotations

from pathlib import Path

from tools.common import meta_base as _base
from tools.common.meta_base import MetaSpec

from . import config

DATA_EXT = ".efkefc"
META_EXT = ".efkefc.meta"


def _spec() -> MetaSpec:
    cfg = config.get()
    return MetaSpec(
        asset_fqn=cfg.meta_asset_type,
        data_ext=DATA_EXT,
        meta_ext=META_EXT,
        default_dir=cfg.effect_dir_rel,
        outer_class_version=1,
        # ParticleFile::save/load base_class<>()s both AssetBase and
        # LifeCycleCallback::IEnablableAsset -> two empty valueN wrappers, not one.
        base_class_count=2,
    )


mint_guid = _base.mint_guid


def content_path_for(name: str, target_dir: Path, repo_root: Path) -> str:
    """Match Effekseer's own ``contentPath_`` convention for ``.efkefc`` assets.

    Unlike the other thin-proxy asset types (see ``meta_base.content_path_for``'s
    "forward slash before the file" convention, itself not fully consistent
    across real ``.prefab`` files either), every real nested ``.efkefc.meta``
    checked in this repo (``tktk01/fireSpark``, ``MAGICALxSPIRAL/Salamander11``,
    ``tktk2/Gun6``) uses an **all-backslash** path with no exception - so this
    binding doesn't delegate to the generic fallback.
    """
    spec = _spec()
    for sib in sorted(target_dir.glob("*" + META_EXT)):
        try:
            cp = _base.read_meta(spec, sib)["content_path"]
        except Exception:  # noqa: BLE001
            continue
        prefix = cp.rsplit("\\", 1)[0] if "\\" in cp else cp.rsplit("/", 1)[0]
        return f"{prefix}\\{name}{DATA_EXT}"
    try:
        rel = target_dir.resolve().relative_to(repo_root.resolve())
        dir_bs = str(rel).replace("/", "\\")
    except ValueError:
        dir_bs = spec.default_dir.replace("/", "\\")
    return f"{dir_bs}\\{name}{DATA_EXT}"


def render_meta(name: str, guid: str, content_path: str) -> str:
    return _base.render_meta(_spec(), name, guid, content_path)


def write_meta(path: Path, name: str, guid: str, content_path: str) -> None:
    _base.write_meta(_spec(), path, name, guid, content_path)


def read_meta(path: Path) -> dict:
    return _base.read_meta(_spec(), path)
