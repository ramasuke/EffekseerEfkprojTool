"""新しい ``.efkproj`` の内容を作る、サンプル由来の厳選ビルダー。

Effekseer の実際のスキーマは数十のノード種別にわたる数百のフィールドがあり、
どのファイルでもほとんどのフィールドはエディタの既定値と違うから存在するだけ。
完全な型付きスキーマを推測する代わりに、このモジュールは次を提供する:

* :func:`elem` - 任意の入れ子のタグ構造 (リーフのテキスト、または生の値や
  他の ``Elem`` からなる入れ子の子) を組み立てる小さな汎用コンポーザー。
* 値の形のヘルパー (:func:`fixed_axes`、:func:`pva`、:func:`easing`、
  :func:`random_color`)。このツールキットの元になったコーパス全体で見られる
  「分布」の形に対応する。
* 共通のノードブロックビルダー (``common_values``、``location_values``、...) と
  ノードビルダー (:func:`sprite_node`、:func:`ring_node`、
  :func:`ribbon_node`、:func:`model_node`、:func:`track_node`、
  :func:`group_node`)。それらのサンプルで観測した実際のフィールド名と既定値から
  組み立てている。

**範囲**: 最初は AndrewFM01 のサンプル 14 個から作り (v1: ``Sprite`` /
``Ring`` / ``Ribbon`` の ``DrawingValues`` のみ)、その後 11 の実アセットパック
(AndrewFM01、MAGICALxSPIRAL、NextSoft01、NitoriBox、Pierre01_130、Pierre02_130、
ProjectDanmakuGirls、Suzuki01、TouhouStrategy、tktk01、tktk02) にまたがる
310 ファイルのコーパスで広げ、``Model``/``Track`` の ``DrawingValues`` 種別、
ノードレベルの ``SoundValues``/``LocationAbsValues`` ブロック、既存ブロックで未対応
だったいくつかのパラメータ区分 (``RendererCommonValues`` のテクスチャ/フェード/UV、
``Sprite`` のランダム/頂点ごとの色と位置、Easing/Single/Axis の拡縮+回転の変種、
``CommonValues`` の親トランスフォーム継承フラグ) を追加した。v1 と同じ理由
(コーパスでまれ、かつ/または参考にできる実際に有効な例が無い) でまだ範囲外のもの:
拡縮/回転/Sprite 色の FCurve (キーフレーム) 版、プロジェクトルートの
``Behavior``/``TargetLocation``/``Culling`` メタデータ、``Field``/乱流/衝突の
ノード概念 (310 個の実サンプルに 1 つも無かった)。
"""

from __future__ import annotations

from .enums import easing_speed
from .model import Elem

# ---------------------------------------------------------------------------
# 汎用の組み立て
def _fmt(value) -> str:
    if isinstance(value, (dict, list, tuple)):
        # ここに dict/list が来るのは、リーフのテキスト値を期待する場所に PVA 形の
        # {"center":.., "max":.., "min":..} 指定 (などの) が渡されたということ -
        # 例えば正しい入れ子の PVA ブロックを作らずに xyz("Velocity", x={...}) とした場合。
        # str() すると失敗せずに Python の repr を要素テキストとして黙って書いてしまう
        # (XML としては正しいが中身はゴミ)。
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
    """``None`` はそのまま通す (フィールド省略)。それ以外は Effekseer の正しい
    イージング速度でなければならない (:func:`enums.easing_speed` 参照)。"""
    return None if value is None else easing_speed(value, what)


def elem(tag: str, *, text=None, children: list[Elem] | None = None, **leaf_children) -> Elem:
    """:class:`Elem` を作る。

    ``elem("X", text=1.8)`` -> テキストリーフ ``<X>1.8</X>``。
    ``elem("Location", X=1.8)`` -> ``<Location><X>1.8</X></Location>``。
    ``elem("Outer_Fixed", Location=elem("Location", X=1.8))`` は作成済みの
    ``Elem`` を入れ子にする (キーワード名は呼び出し側の読みやすさのためだけで、
    書き出されるのは子自身の ``.tag``)。
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
# 値の形のヘルパー
def fixed_axes(tag: str, **axes) -> Elem:
    """軸ごとの値を持つ ``Tag_Fixed`` 形式のリーフ。例:
    ``fixed_axes("ColorAll_Fixed", R=0, G=0, B=0, A=255)``。
    """
    return elem(tag, **axes)


def pva(tag: str, *, x=None, y=None, z=None, center=None, max=None, min=None,
        drawn_as: int | None = None) -> Elem:
    """単一スカラーの PVA ブロック (``center``/``max``/``min`` を直接渡す) か、
    軸ごとの PVA ブロック (``x=``/``y=``/``z=`` に
    ``{"center":..,"max":..,"min":..}`` の dict を渡す) のどちらか。サンプルで見られる
    両方の形に対応する (例: ``ScalingValues.PVA.Scale.X`` と素のスカラー PVA)。
    """
    e = Elem(tag)
    axes = {"X": x, "Y": y, "Z": z}
    if any(v is not None for v in axes.values()):
        for name, spec in axes.items():
            if spec is None:
                continue
            # スカラーの分岐を再帰的に通して、各軸が
            # <Center>/<Max>/<Min>(/<DrawnAs>) になるようにする。以前は
            # elem(name, **spec) で、dict のキーをそのまま小文字の
            # <center>/<max>/<min> として書いていた - Effekseer のローダーは子を
            # 大文字小文字を区別して探す (e["Center"]) ので、軸全体が黙って
            # 無視され、この方法で作って配布したエフェクトはすべてエディタの既定値
            # (スケール 1.0、ランダム無し) になっていた。
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
    """``Start``/``End`` (+ 任意の ``StartSpeed``/``EndSpeed``) ブロック。
    ``start``/``end`` は軸ごと (``elem("Start", X=pva(...), ...)``)、
    平坦なスカラー (``pva("Start", center=.., max=.., min=..)``)、チャンネルごと
    (``random_color("Start", r=.., g=.., ...)``) のどれでもよく、呼び出し側が作った形が
    そのまま使われる。実サンプルでは、この ``Easing`` がどのブロックの下にあるか
    (Location/Scaling/Rotation か、Scaling の ``SingleEasing`` か、Model/Track の
    チャンネルごとの色イージングか) によって 3 つすべてが使われている。
    ``start_speed``/``end_speed`` は Effekseer の ``EasingStart``/``EasingEnd``
    列挙値で、自由な浮動小数ではない: 正しいのは ``-30,-20,-10,0,10,20,30`` のみ
    (:data:`enums.EASING_SPEEDS` 参照)。Effekseer のエディタがそれ以外で落ちるので、
    ここで ``ValueError`` を投げる。
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
    """チャンネルごとの PVA 色ブロック。例: ``random_color("ColorAll_Random",
    r={"center": 0, "max": 255, "min": 0}, a={"center": 255, "max": 255,
    "min": 255})`` -> ``<ColorAll_Random><R>...</R><A>...</A></ColorAll_Random>``。
    各チャンネルは平坦な ``{"center":..,"max":..,"min":..}`` の dict。
    ブロックレベルの ``drawn_as``/``color_space`` 兄弟 (``R``/``G``/``B``/``A`` の後) は
    実在するがほとんど触られない (実サンプルはすべて `1`/`0`)。
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
    """``AxisPVA`` (``RotationValues`` Type=3): ``axis`` は回転軸の方向を表す
    軸ごとの PVA の ``Elem`` (例: Z 軸回転なら ``xyz("Axis",
    x=pva("X", center=0, max=0, min=0), z=pva("Z", center=1, max=1, min=1))``)。
    ``rotation``/``velocity``/``acceleration`` はその軸まわりのスカラーの角度/回転速度を
    表す平坦な ``{"center":..,"max":..,"min":..}`` の dict。
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
    """``AxisEasing`` (``RotationValues`` Type=4) - :func:`axis_pva`/:func:`easing` から
    類推した構造 (軸方向 + イージングするスカラー角度)。310 ファイルのコーパスには
    この変種を実際に選択しているサンプルが無かった (持っているファイルでは常に
    ``RotationValues.Type=3`` の裏に残った無効なキャッシュ) ので、実際に有効な例が
    見つかるまでは未検証として扱うこと。``start``/``end`` は平坦な ``{"center":..,
    "max":..,"min":..}`` の dict。
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
# Node 共通の子ブロックのビルダー
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
    """``CommonValues``。``location_effect_type``/``rotation_effect_type``/
    ``scale_effect_type`` は子ノードへの親トランスフォーム継承フラグ
    (0/1/2、実コーパスの最頻値は 1)。

    Effekseer はファイルの ``ToolVersion`` からレイアウトを選ぶので、``layout`` は
    対象ファイルの ``ToolVersion`` に合わせること (``versions.layout_of`` 参照):

    * ``"legacy"`` (ToolVersion < 1.80β2): ``RemoveWhen*``、``GenerationTime``/
      ``GenerationTimeOffset``、``TriggerParam`` が直接の子。順序は冗長な実サンプル
      (``NextSoft01/MagicFire1.efkproj``) と 1.7.3 エディタ自身の出力に一致する。
      1.80 は読み込み時にこれらをマイグレーションする。
    * ``"v180"``: 同じ値が ``<Generation>``/``<Removal>`` の中にある
      (1.80.7 ``Data/CommonValues.cs``、順序は 1.80.7 エディタが書くとおり)。
      こちらは 1.80 専用の ``generation_timing`` (0=Continuous、1=Trigger)、
      ``trigger``、``trigger_count`` も持つ。

    ``trigger_*`` は Effekseer の ``TriggerType`` の値: 0=None、
    1/257/513/769=Trigger0-3、(1.80 のみ) 2=ParentRemoved、
    3=ParentCollided。PVA 形の値は ``{"center":..,"max":..,"min":..}``。
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
    """``LocationValues``。``fixed_xyz`` は ``Type=0``/``Fixed`` ブロック用の素の
    ``{"X":.., "Y":.., "Z":..}`` の dict。``velocity``/``acceleration`` は
    ``Type=1``/``PVA`` ブロック用の ``xyz("Velocity", ...)``/``xyz("Acceleration", ...)``
    形の ``Elem``。``easing`` は ``Type=2`` の軸ごとの
    ``easing("Easing", start=elem("Start", X=pva(...), ...), end=...)``
    ブロック。
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
    """``LocationAbsValues`` (``LocationValues`` と同じ ``Node`` レベルの兄弟で、
    実ファイルでは ``ScalingValues`` の後/``GenerationLocationValues`` の前にある)。
    ``gravity`` は素の ``{"x":..,"y":..,"z":..}`` の dict (Type=1。実際の形では
    タグが二重になる: ``<Gravity><Gravity><X>...``)。``attractive_force`` は
    素のスカラーの引力の強さ (Type=2)。実例:
    ``AndrewFM01/blue_laser.efkproj``。
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
    """``RotationValues``。``fixed`` は ``Type=0``/``Fixed`` ブロック用の
    ``xyz("Rotation", ...)`` 形。``velocity``/``acceleration`` は ``Type=1``/``PVA``
    ブロック用の ``xyz("Rotation", X=pva(...), ...)`` 形 (各軸自体が PVA)。
    ``easing`` は ``Type=2`` の軸ごとの ``easing("Easing", ...)`` ブロック
    (``location_values`` のものと同じ形)。
    ``axis_pva``/``axis_easing`` (Type=3/4、:func:`axis_pva`/:func:`axis_easing`
    参照) は ``ScalingValues`` の Type=3/4 のような「全軸に同じスカラー」では
    **ない** - 回転軸とその軸まわりの角度を定義する。
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
    """``ScalingValues``。``fixed`` は ``Type=0``/``Fixed`` ブロック用の
    ``xyz("Scale", ...)`` 形。``pva_scale`` は ``Type=1``/``PVA`` ブロック用の
    ``pva("Scale", x={...}, y={...}, drawn_as=0)`` 形の ``Elem``。
    ``easing`` は ``Type=2`` の軸ごとの ``easing("Easing", ...)`` ブロック。
    ``single_pva`` は平坦な ``{"center":..,"max":..,"min":..}`` の dict
    (Type=3、全軸に一様に適用)。``single_easing`` は ``Type=4`` の平坦なスカラーの
    ``easing("SingleEasing", start=pva("Start", center=..,...), end=pva("End", ...),
    start_speed=.., end_speed=..)`` ブロック (注: ``easing`` の軸ごとのものと違い、
    ``Start``/``End`` は平坦)。
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
    """``GenerationLocationValues`` Type=0/``Point`` - コーパスで最も多い形
    (310 ファイル中 746 件) なのに、以前はまったく作れなかった。
    ``location`` は ``pva("Location", x={...}, y={...}, z={...})`` 形式の軸ごとの
    dict、つまり ``{"x": {"center":..,"max":..,"min":..}, "y": ...}``。
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
    """``GenerationLocationValues`` Type=3/``Circle``。``circle_type`` は入れ子の
    分割モードのサブモード (0/1/2、実サンプルの既定値は 0) - 外側の ``Type``
    セレクタと混同しないこと。
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
    """``RendererCommonValues``。``fade_in``/``fade_out`` は ``{"frame":..,
    "start_speed":..,"end_speed":..}`` (必須は ``frame`` のみ。速度は Effekseer の
    ``EasingStart``/``EasingEnd`` 列挙値で、正しいのは ``-30,-20,-10,0,10,20,
    30`` のみ - :data:`enums.EASING_SPEEDS` 参照 - 自由な浮動小数ではない。範囲外の
    値はコンパイルは通るのに Effekseer エディタを落とすので、ここで拒否する)。
    ``uv_fixed`` は ``{"start":{"x":..,"y":..}, "size":{"x":..,"y":..}}``。
    ``uv_animation`` はさらに ``frame_length``/``frame_count_x``/``frame_count_y``/
    ``loop_type`` を取る。``uv_scroll`` は ``size`` の代わりに ``speed`` の dict を取る。
    ``uv_*`` は多くても 1 つだけ渡すこと - どれも ``UV`` セレクタ (1/2/3) も決める。
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
# DrawingValues の種別ごとのビルダー
def _append_color_mode(e: Elem, prefix: str, fixed: Elem | None,
                        random_: Elem | None, easing_: Elem | None) -> None:
    """``<prefix>_Fixed``/``_Random``/``_Easing`` の 3 つ組を追加する (Sprite/Ribbon の
    ``ColorAll`` と、Ring の ``OuterColor``/``CenterColor``/``InnerColor`` の両方で
    使う)。``<prefix>N</prefix>`` のモードセレクタは Random(1)/Easing(2) のときだけ
    書く - Fixed(0) には不要で、実際の疎なファイルすべてと一致する
    (コーパスでは ``color_all`` 単独で明示的なセレクタを持っていたことは一度も無い)。
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
    # Effekseer の実際の BillboardType: 0=Billboard (常にカメラを向く - ほぼすべての
    # パーティクルスプライトが求めるもの)、1=YAxisFixed、2=Fixed (カメラ向きの補正を
    # 一切しない - 向きの固定された静的な平面として描かれる。例: 地面に平らな衝撃波の
    # リング)、3=RotatedBillboard。以前はこれを 2 を既定にしていた (手元の実サンプルで
    # たまたまそれを使っていた地面デカール 1 つから写した) ため、普通の煙/火花の
    # スプライトがカメラを向く雲ではなく平らな静的カードとして描かれていた。
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
    """``Ring``。``outer``/``center``/``inner`` の各色は Sprite/Ribbon の ``ColorAll`` と
    同じ Fixed/Random/Easing の 3 つ組を持つ (実際の ``<OuterColor>``/
    ``<CenterColor>``/``<InnerColor>`` モードセレクタがそれぞれ独立に 0/1/2 を取る
    ことで確認済み) - :func:`_append_color_mode` 参照。
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
    """``Model`` の ``DrawingValues`` ブロック (Type=5)。``model_path`` は隣にある
    ``.efkmodel`` アセットへの相対パス (例: ``"Model/foo.efkmodel"``
    - Effekseer CUI がコンパイル時に ``RendererCommonValues.ColorTexture`` と同じ
    方法で解決するので、ツールキット側の特別な処理は不要)。``color_easing`` は
    チャンネルごとの ``easing("Color_Easing", start=random_color("Start", r={...}, ...),
    end=random_color("End", ...), start_speed=.., end_speed=..)`` ブロック。
    指定すると ``color_fixed`` と並んで ``Color`` セレクタ (=2) を出力する (冗長な
    実ファイルと一致 - ``color_fixed`` 単独ならセレクタは不要)。
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
    """``Track`` の ``DrawingValues`` ブロック (Type=6): 左から右へ 6 本の色の
    「レール」。各パラメータは作成済みの ``Elem`` で、タグはそのレールについて
    Effekseer が期待するとおり - ``color("ColorLeft_Fixed", r=.., g=.., b=..,
    a=..)`` または ``easing("ColorLeft_Easing", start=random_color("Start",
    ...), end=random_color("End", ...))`` (レールごとに ``ColorLeft`` を
    ``ColorLeftMiddle``/``ColorCenter``/``ColorCenterMiddle``/``ColorRight``/
    ``ColorRightMiddle`` に置き換える)。形状用のフィールドは別に無い - Track の
    形は頂点データではなく、ノード自身の移動履歴から決まる。
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
    """``SoundValues`` - ``DrawingValues`` と同じ ``Node`` レベルの兄弟で、
    ``DrawingValues`` の種別 *ではない* (Effekseer はノードのサウンドを、描画する
    ものと一緒に、または何も描画せずに再生する)。``volume``/``pitch``/``pan``/
    ``delay`` は平坦な ``{"center":..,"max":..,"min":..}`` の dict。``distance`` は
    素のスカラー。``wave`` は隣にある ``.wav`` アセットへの相対パス (``ColorTexture``/
    ``Model`` のアセットパスと同じく CUI がコンパイル時に解決するので、ツールキット側の
    特別な処理は不要)。実例: ``NextSoft01/MagicFire1.efkproj`` (310 ファイルの
    コーパスでこれを本当に有効にしている 2 ファイルのうちの 1 つ - ほとんどの実ファイルは
    代わりに無効な ``Type=0`` の ``SoundValues`` を持っている)。
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
# Node / プロジェクトの組み立て
def node(name: str = "Node", *, common: Elem | None = None, location: Elem | None = None,
         rotation: Elem | None = None, scaling: Elem | None = None,
         location_abs: Elem | None = None, generation_location: Elem | None = None,
         renderer_common: Elem | None = None, drawing: Elem | None = None,
         sound: Elem | None = None, is_rendered: bool | None = None,
         children: list[Elem] | None = None) -> Elem:
    """親の ``<Children>`` にそのまま追加できる完全な ``<Node>`` を作る。
    ブロックの順序は実ファイルとバイト単位で一致する
    (``NextSoft01/MagicFire1.efkproj``/``AndrewFM01/blue_laser.efkproj`` で確認):
    Common、Location、Rotation、Scaling、LocationAbs、GenerationLocation、
    RendererCommon、Drawing、Sound、その後 IsRendered/Name/Children。
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
    """何も描かず、子をまとめるだけの純粋なコンテナノード。
    ``DrawingValues/Type`` は明示的に 0 (None) と書く: ``Type`` が無い - または
    ``DrawingValues`` が無い - と、Effekseer 1.5x-1.80.x のどのエディタでも *Sprite*
    になる (各ファミリーの CUI で確認)。"""
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
    """完全な ``<EffekseerProject>`` の骨組みを作る。

    既定値 (``tool_version``/``version``) はこのツールキットの元になった
    AndrewFM01 の実サンプルに合わせてある。``ToolVersion`` は仮の値ではない:
    Effekseer が読む ``CommonValues`` のレイアウトを決め (:func:`common_values`
    参照)、エディタは自分より新しいものを拒否するので、``new-project`` は対象
    バージョンの ``versions.Profile.new_project_tool_version`` を渡す
    (1.7 では ``"0.7CTP1"``、どのエディタでも読める。1.80 では ``"1.80"``)。
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
