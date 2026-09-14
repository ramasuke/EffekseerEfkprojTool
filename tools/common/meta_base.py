""".meta sidecar codec for "thin proxy" ``AssetBase``-derived asset types.

A ``.meta`` is a cereal-JSON ``std::shared_ptr<AssetBase>`` holding one asset
object: a stable ``guid_`` (what other files reference this asset by) plus
``contentPath_`` pointing back at the sibling data file. Written by
``File::OnSave()`` in the engine.

This module is generic over the *thin proxy* asset family - ``EnemyBehaviourFile``,
``SceneFile``, ``PrefabGameObjectFile`` - where the ``.meta`` holds only
``contentPath_``/``guid_`` and the real payload lives in the separate data file.
It does **not** generalise to "fat" ``ScriptableObject``-derived assets (e.g.
``SwordManInitStatus``), which serialise their entire payload inline in the
``.meta`` with an empty sibling data file - a different asset family entirely.

Each thin-proxy asset type is described by a :class:`MetaSpec`; callers bind one
per asset type (see ``tools/bt/meta.py`` for the ``EnemyBehaviourFile`` binding).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

from .cereal_json import Num, OrderedObj, dumps, loads, read_text, to_file_bytes

# First shared-ptr id / first polymorphic type id cereal ever allocates - a
# .meta file only ever holds this one object, so the id is always the same.
_ID = 0x80000001


@dataclass(frozen=True)
class MetaSpec:
    asset_fqn: str            # polymorphic_name, e.g. "NanamiEngine::Module::Asset::SceneFile"
    data_ext: str              # e.g. ".scene"
    meta_ext: str              # e.g. ".scene.meta"
    default_dir: str           # fallback content dir, e.g. "Assets/Scene"
    outer_class_version: int = 0  # the asset class's own CEREAL_CLASS_VERSION
    # Number of empty cereal::base_class<> archive() calls the concrete class's
    # save()/load() makes before its own CEREAL_NVP fields - one "valueN" block
    # per base class serialized ahead of contentPath_/guid_. Most thin-proxy
    # assets only base_class<AssetBase>() (1); a type that also base_class<>()s
    # a second interface (e.g. ParticleFile also serializing IEnablableAsset)
    # needs 2. Check the class's save()/load() template if unsure.
    base_class_count: int = 1


def mint_guid() -> str:
    return str(uuid.uuid4()).upper()


def content_path_for(spec: MetaSpec, name: str, target_dir: Path, repo_root: Path) -> str:
    """Match the sibling ``.meta`` separator convention, or fall back to default.

    Observed form: backslash-separated directory, forward slash before the file,
    e.g. ``Assets\\Data\\EnemyBehaviour/Hyena.enemyBehaviourData``.
    """
    for sib in sorted(target_dir.glob("*" + spec.meta_ext)):
        try:
            cp = read_meta(spec, sib)["content_path"]
        except Exception:  # noqa: BLE001
            continue
        prefix = cp.rsplit("/", 1)[0] if "/" in cp else cp.rsplit("\\", 1)[0]
        return f"{prefix}/{name}{spec.data_ext}"
    try:
        rel = target_dir.resolve().relative_to(repo_root.resolve())
        dir_bs = str(rel).replace("/", "\\")
    except ValueError:
        dir_bs = spec.default_dir.replace("/", "\\")
    return f"{dir_bs}/{name}{spec.data_ext}"


def render_meta(spec: MetaSpec, name: str, guid: str, content_path: str) -> str:
    data = OrderedObj()
    data["cereal_class_version"] = Num.of_int(spec.outer_class_version)
    for i in range(spec.base_class_count):
        data[f"value{i}"] = OrderedObj([("cereal_class_version", Num.of_int(0))])
    data["contentPath_"] = content_path
    data["guid_"] = OrderedObj([("cereal_class_version", Num.of_int(0)), ("value_", guid)])

    inner = OrderedObj()
    inner["polymorphic_id"] = Num.of_int(_ID)
    inner["polymorphic_name"] = spec.asset_fqn
    inner["ptr_wrapper"] = OrderedObj([("id", Num.of_int(_ID)), ("data", data)])
    return dumps(OrderedObj([("value0", inner)]))


def write_meta(spec: MetaSpec, path: Path, name: str, guid: str, content_path: str) -> None:
    path.write_bytes(to_file_bytes(render_meta(spec, name, guid, content_path)))


def read_meta(spec: MetaSpec, path: Path) -> dict:
    obj = loads(read_text(path))
    d = obj["value0"]["ptr_wrapper"]["data"]
    cp = d["contentPath_"]
    guid = d["guid_"]["value_"]
    fname = Path(path).name
    name = fname[: -len(spec.meta_ext)] if fname.endswith(spec.meta_ext) else Path(cp).name.split(".")[0]
    return {"name": name, "guid": guid, "content_path": cp}
