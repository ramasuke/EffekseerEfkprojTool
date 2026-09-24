"""``AssetBase`` 派生の "thin proxy" アセット型用の .meta サイドカーコーデック。

``.meta`` は1つのアセットオブジェクトを持つ cereal-JSON の
``std::shared_ptr<AssetBase>`` で、安定した ``guid_`` (他のファイルがこのアセットを
参照するためのもの) と、兄弟のデータファイルを指す ``contentPath_`` を持つ。
エンジンの ``File::OnSave()`` が書き出す。

このモジュールは *thin proxy* アセット群 - ``EnemyBehaviourFile``、
``SceneFile``、``PrefabGameObjectFile`` - に対して汎用で、これらの ``.meta`` は
``contentPath_``/``guid_`` だけを持ち、実データは別のデータファイルにある。
``ScriptableObject`` 派生の "fat" アセット (例: ``SwordManInitStatus``) には
**適用できない**。それらはペイロード全体を ``.meta`` 内にインラインで
シリアライズし、兄弟のデータファイルは空 - まったく別のアセット群である。

thin proxy の各アセット型は :class:`MetaSpec` で記述する。呼び出し側がアセット型
ごとに1つ結び付ける (``EnemyBehaviourFile`` の結び付けは ``tools/bt/meta.py`` を参照)。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

from .cereal_json import Num, OrderedObj, dumps, loads, read_text, to_file_bytes

# cereal が最初に割り当てる shared-ptr id / polymorphic 型 id - .meta ファイルは
# このオブジェクト1つしか持たないので、id は常に同じ。
_ID = 0x80000001


@dataclass(frozen=True)
class MetaSpec:
    asset_fqn: str            # polymorphic_name。例: "NanamiEngine::Module::Asset::SceneFile"
    data_ext: str              # 例: ".scene"
    meta_ext: str              # 例: ".scene.meta"
    default_dir: str           # 代替のコンテンツディレクトリ。例: "Assets/Scene"
    outer_class_version: int = 0  # アセットクラス自身の CEREAL_CLASS_VERSION
    # 具象クラスの save()/load() が自身の CEREAL_NVP フィールドより前に行う、
    # 空の cereal::base_class<> archive() 呼び出しの数 - contentPath_/guid_ の前に
    # シリアライズされる基底クラスごとに "valueN" ブロックが1つできる。thin proxy の
    # 多くは base_class<AssetBase>() だけ (1)。2つ目のインターフェースも base_class<>() する
    # 型 (例: IEnablableAsset もシリアライズする ParticleFile) は 2 が必要。
    # 不明ならそのクラスの save()/load() テンプレートを確認すること。
    base_class_count: int = 1


def mint_guid() -> str:
    return str(uuid.uuid4()).upper()


def content_path_for(spec: MetaSpec, name: str, target_dir: Path, repo_root: Path) -> str:
    """兄弟の ``.meta`` の区切り文字の慣例に合わせる。なければ既定値にフォールバックする。

    観測された形式: ディレクトリはバックスラッシュ区切り、ファイルの前だけスラッシュ。
    例: ``Assets\\Data\\EnemyBehaviour/Hyena.enemyBehaviourData``。
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
