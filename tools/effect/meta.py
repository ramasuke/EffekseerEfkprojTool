"""``.efkefc.meta`` サイドカーファイル。

``.meta`` は ``ParticleFile`` アセットを持つ cereal-JSON の ``std::shared_ptr<AssetBase>``:
安定した ``guid_`` (コンポーネントのパーティクルエフェクトのフィールドが参照するもの)
と、コンパイル済み ``.efkefc`` を指す ``contentPath_``。エンジンでは
``File::OnSave()`` が書き出す。ここで同じものを作るので、``install`` の結果は
すぐにエディタ/プレハブから紐付けられるアセットになる。

汎用の :mod:`tools.common.meta_base` コーデックを ``ParticleFile`` アセット型に
薄く結び付けたもの - 形式の説明はそのモジュールを、他のアセット型に同じパターンを
適用した例は ``tools/bt/meta.py`` / ``tools/scene/meta.py`` を参照。
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
        # ParticleFile::save/load は AssetBase と LifeCycleCallback::IEnablableAsset の
        # 両方を base_class<>() する -> 空の valueN ラッパーは 1 つではなく 2 つ。
        base_class_count=2,
    )


mint_guid = _base.mint_guid


def content_path_for(name: str, target_dir: Path, repo_root: Path) -> str:
    """``.efkefc`` アセットについての Effekseer 独自の ``contentPath_`` 規則に合わせる。

    他の薄いプロキシのアセット型 (``meta_base.content_path_for`` の「ファイル名の
    直前はスラッシュ」規則。これも実際の ``.prefab`` では完全には一貫していない) と
    違い、このリポジトリで確認した実際のネストした ``.efkefc.meta``
    (``tktk01/fireBall``、``MAGICALxSPIRAL/Salamander11``、``tktk2/Gun6``) は例外なく
    **すべてバックスラッシュ** のパスを使っている - なのでこのバインディングは
    汎用のフォールバックに委ねない。
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
