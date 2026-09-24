"""Effekseer の ``Enum<T>`` 型フィールドの値域を Effekseer のバージョンファミリー
(1.5x、1.6x、1.7x、1.80.x) ごとに持ち、``.efkproj`` のノードツリーをチェックする。

これがある理由: Effekseer のエディタは ``Value.Enum<T>`` のリーフをすべて素の
``int.TryParse -> SetValue`` で読み込み (``Data/IO.cs``、範囲チェック無し)、GUI の
``Effekseer.GUI.Component.Enum.Update()`` はその後
``enums.Where(v == selected).FirstOrDefault().Item2`` を実行する - 列挙のメンバーで
ない値だと ``FirstOrDefault()`` が null になり、そのフィールドを表示するパネルが
描画された瞬間にエディタが ``NullReferenceException`` で落ちる (例: ``FadeIn``/
``FadeOut`` の "Basic Render Settings" ドック)。CUI コンパイラはこれを
**検出しない** - 生の整数をそのままイージング式に渡して 0 で終了する - ので、
不正な値は誰かが GUI で ``.efkproj`` を開いて初めて表面化する。このモジュールは
ツールキット側のガード。

以下の値域はすべて 1.7.3.0 のソース
(``Dev/Editor/EffekseerCore/Data/{Define,RendererCommonValues,RendererValues,
CommonValues,LocationValues,RotationValues,ScaleValues,
GenerationLocationValues,SoundValues}.cs``) から読み取り、このツールキットの元に
なった 310 ファイルの実サンプルコーパスに対して誤検出が無いことを確認した
(``selftest.stage_corpus_sweep`` 参照)。あえて完全なスキーマには *していない*:
ツールキット自身が書くフィールド (またはそれとリーフのタグが同じもの) だけを
載せ、テキストが整数でないリーフは決して検出しない。

他のファミリーの表は、Windows 版ツールのある全リリース (1.50RC1 ... 1.80.7) で、
各リリースの ``EffekseerCore.dll`` にある ``Effekseer.Data.Node`` のプロパティを
リフレクションでたどり、``Value.Enum<T>`` ごとのメンバーを列挙して確認した -
これは GUI の ``Enum.Initialize`` が提示するリストそのもの。同じファミリーの全リリースは
値域が同一で、以下の各表はそのファミリーの DLL に存在するすべての接尾辞について
一致する。新しいファミリーはメンバーを *追加* するだけなので (1.80: ``Billboard=4``、
``Wrap=2``、...; 1.7: ``FadeOutType=2``、``Gradient`` 色、``RotationValues.Type=6``、
``TriggerParam``; 1.6: Location/Scaling の種類の追加)、新しいファミリーでしか有効で
ない値は古いファミリーを対象にしたとき違反になる - そのエディタが落ちる。1 つだけ
*番号が振り直された* メンバーがある: ``TextureUVType`` は 1.7 までは
Strech=0/Tile=1、1.80 では Strech=0/TilePerParticle=1/Tile=2。
"""

from __future__ import annotations

from .model import Elem
from .versions import Profile, walk_nodes

# EasingStart / EasingEnd (Define.cs): 負 = *Slowly{1,2,3}、正 =
# *Rapidly{1,2,3}、0 = Start/End (線形)。FadeIn/FadeOut と、すべての
# Easing/SingleEasing/AxisEasing/*_Easing ブロックの StartSpeed/EndSpeed で使う。
EASING_SPEEDS: tuple[int, ...] = (-30, -20, -10, 0, 10, 20, 30)


def easing_speed(value, what: str = "StartSpeed/EndSpeed") -> int:
    """``value`` を :data:`EASING_SPEEDS` のいずれかに変換する。できなければ ``ValueError``。

    整数、整数値の浮動小数 (``30.0``)、数値文字列 (``"-30"``) を受け付ける。
    """
    try:
        f = float(value)
    except (TypeError, ValueError) as e:
        raise ValueError(f"{what}={value!r} is not a number") from e
    if not f.is_integer() or int(f) not in EASING_SPEEDS:
        raise ValueError(
            f"{what}={value!r} is not a valid Effekseer easing speed; allowed values are "
            f"{list(EASING_SPEEDS)} (negative = slowly, positive = rapidly, 0 = linear). "
            "Effekseer's editor crashes (NullReferenceException in Enum.Update) on any "
            "other value, even though the CUI compiles it without complaint."
        )
    return int(f)


def _r(*values: int) -> frozenset[int]:
    return frozenset(values)


# (タグパスの接尾辞、<Node> からの相対) -> 許される整数。ルールはタグパスが
# その接尾辞で *終わる* リーフに適用される (最長一致の接尾辞が優先) ので、
# ("StartSpeed",) は FadeIn/StartSpeed、Easing/StartSpeed、
# ColorAll_Easing/StartSpeed、... をカバーし、("Sprite", "Color") は
# DrawingValues/Sprite/Color だけをカバーする。コメントは各値域の読み取り元の
# Effekseer 列挙型の名前。
ENUM_DOMAINS_17: dict[tuple[str, ...], frozenset[int]] = {
    ("StartSpeed",): frozenset(EASING_SPEEDS),                 # EasingStart
    ("EndSpeed",): frozenset(EASING_SPEEDS),                   # EasingEnd
    ("DrawnAs",): _r(0, 1),                                    # DrawnAs
    ("ColorSpace",): _r(0, 1),                                 # ColorSpace
    # RendererCommonValues
    ("RendererCommonValues", "Filter"): _r(0, 1),              # FilterType
    ("RendererCommonValues", "Filter2"): _r(0, 1),
    ("RendererCommonValues", "Wrap"): _r(0, 1),                # WrapType
    ("RendererCommonValues", "Wrap2"): _r(0, 1),
    ("RendererCommonValues", "AlphaBlend"): _r(0, 1, 2, 3, 4),  # AlphaBlendType
    ("RendererCommonValues", "FadeInType"): _r(0, 1),          # FadeInMethod
    ("RendererCommonValues", "FadeOutType"): _r(0, 1, 2),      # FadeOutMethod
    ("RendererCommonValues", "UV"): _r(0, 1, 2, 3, 4),         # UVType
    ("UVAnimation", "LoopType"): _r(0, 1, 2),                  # LoopType
    ("RendererCommonValues", "ColorInheritType"): _r(0, 1, 2, 3),  # ParentEffectType
    ("RendererCommonValues", "Material"): _r(0, 6, 7, 128),    # MaterialType
    # DrawingValues + 種別ごとのブロック (RendererValues.cs)
    ("DrawingValues", "Type"): _r(0, 2, 3, 4, 5, 6),           # ParamaterType (1 は未使用)
    ("Sprite", "Billboard"): _r(0, 1, 2, 3),                   # BillboardType
    ("Ring", "Billboard"): _r(0, 1, 2, 3),
    ("Model", "Billboard"): _r(0, 1, 2, 3),
    ("Sprite", "RenderingOrder"): _r(0, 1),                    # RenderingOrder
    ("Ring", "RenderingOrder"): _r(0, 1),
    ("Sprite", "ColorAll"): _r(0, 1, 2, 3, 4),                 # StandardColorType
    ("Ribbon", "ColorAll"): _r(0, 1, 2),                       # ColorAllType
    ("Sprite", "Color"): _r(0, 1),                             # ColorType (Default/Fixed)
    ("Ribbon", "Color"): _r(0, 1),
    ("Sprite", "Position"): _r(0, 1),                          # PositionType
    ("Ribbon", "Position"): _r(0, 1),
    ("Ring", "Outer"): _r(0, 1, 2),                            # LocationType
    ("Ring", "Inner"): _r(0, 1, 2),
    ("Ring", "CenterRatio"): _r(0, 1, 2),                      # CenterRatioType
    ("Ring", "ViewingAngle"): _r(0, 1, 2),                     # ViewingAngleType
    ("Ring", "OuterColor"): _r(0, 1, 2),                       # ColorType (Fixed/Random/Easing)
    ("Ring", "CenterColor"): _r(0, 1, 2),
    ("Ring", "InnerColor"): _r(0, 1, 2),
    ("DrawingValues", "Model", "Color"): _r(0, 1, 2, 3, 4),    # StandardColorType
    ("DrawingValues", "Model", "Culling"): _r(0, 1, 2),        # CullingValues
    # トランスフォーム / 生成ブロック
    ("LocationValues", "Type"): _r(0, 1, 2, 3, 4, 5),          # LocationValues.ParamaterType
    ("RotationValues", "Type"): _r(0, 1, 2, 3, 4, 5, 6),       # RotationValues.ParamaterType
    ("ScalingValues", "Type"): _r(0, 1, 2, 3, 4, 5, 6),        # ScaleValues.ParamaterType
    ("GenerationLocationValues", "Type"): _r(0, 1, 2, 3, 4),   # ParameterType
    ("GenerationLocationValues", "Circle", "Type"): _r(0, 1, 2),  # CircleType
    ("GenerationLocationValues", "Line", "Type"): _r(0, 1),    # LineType
    ("GenerationLocationValues", "Model", "Type"): _r(0, 1, 2, 3, 4),  # ModelType
    ("CommonValues", "LocationEffectType"): _r(0, 1, 2, 3, 4, 5),  # TranslationParentEffectType
    ("CommonValues", "RotationEffectType"): _r(0, 1, 2, 3),    # ParentEffectType
    ("CommonValues", "ScaleEffectType"): _r(0, 1, 2, 3),
    ("SoundValues", "Type"): _r(0, 1),                         # SoundValues.ParamaterType
    ("Sound", "PanType"): _r(0, 1),                            # ParamaterPanType
    ("TriggerParam", "ToStartGeneration"): _r(0, 1, 257, 513, 769),  # TriggerType (None、Trigger0-3)
    ("TriggerParam", "ToStopGeneration"): _r(0, 1, 257, 513, 769),
    ("TriggerParam", "ToRemove"): _r(0, 1, 257, 513, 769),
    ("DrawingValues", "TextureUVType", "Type"): _r(0, 1),      # TextureUVType (Strech/Tile)
    ("DrawingValues", "Model", "ModelReference"): _r(0, 1),    # ModelReferenceType
    ("GenerationLocationValues", "Model", "ModelReference"): _r(0, 1),
}

_TRIGGER_TYPE_180 = _r(0, 1, 257, 513, 769, 2, 3)              # + ParentRemoved, ParentCollided
_ADDED_IN_180: dict[tuple[str, ...], frozenset[int]] = {
    ("RendererCommonValues", "Wrap"): _r(0, 1, 2),             # WrapType + Mirror
    ("RendererCommonValues", "Wrap2"): _r(0, 1, 2),
    ("Sprite", "Billboard"): _r(0, 1, 2, 3, 4),                # BillboardType + DirectionalBillboard
    ("Ring", "Billboard"): _r(0, 1, 2, 3, 4),
    ("Model", "Billboard"): _r(0, 1, 2, 3, 4),
    ("RotationValues", "Type"): _r(0, 1, 2, 3, 4, 5, 6, 7),    # + RotateToVelocity
    ("RotationValues", "Velocity", "Axis"): _r(0, 1, 2, 3, 4, 5),  # PlaneAxisType
    ("TriggerParam", "ToStartGeneration"): _TRIGGER_TYPE_180,
    ("TriggerParam", "ToStopGeneration"): _TRIGGER_TYPE_180,
    ("TriggerParam", "ToRemove"): _TRIGGER_TYPE_180,
    ("CommonValues", "Generation", "Timing"): _r(0, 1),        # GenerationTimingType
    ("CommonValues", "Generation", "ToStartGeneration"): _TRIGGER_TYPE_180,
    ("CommonValues", "Generation", "ToStopGeneration"): _TRIGGER_TYPE_180,
    ("CommonValues", "Generation", "Trigger"): _TRIGGER_TYPE_180,
    ("CommonValues", "Removal", "TriggerToRemove"): _TRIGGER_TYPE_180,
    ("DrawingValues", "TextureUVType", "Type"): _r(0, 1, 2),   # TilePerParticle=1、Tile は 2 に番号変更
    ("DrawingValues", "Model", "ModelReference"): _r(0, 1, 2),  # + ExternalModel
    ("GenerationLocationValues", "Model", "ModelReference"): _r(0, 1, 2),
    ("GenerationLocationValues", "Model", "Coordinate"): _r(0, 1),  # ModelCoordinateType
    ("KillRulesValues", "Type"): _r(0, 1, 2, 3),               # KillType
    ("KillRulesValues", "PlaneAxis"): _r(0, 1, 2, 3, 4, 5),    # PlaneAxisType
    ("CollisionsValues", "WorldCoordinateSyatem"): _r(0, 1),   # WorldCoordinateSyatemType (sic)
    # GpuParticles (GpuParticles.cs)
    ("GpuParticles", "EmitShape", "Shape"): _r(0, 1, 2, 3, 4),  # EmitShapeParams.ShapeType
    ("GpuParticles", "Scale", "Type"): _r(0, 2),               # ScaleParams.ParamaterType (Fixed/Easing)
    ("GpuParticles", "RenderBasic", "BlendType"): _r(0, 1, 2, 3, 4),  # AlphaBlendType
    ("GpuParticles", "RenderShape", "Shape"): _r(0, 1, 2),     # RenderShapeParams.ShapeType
    ("GpuParticles", "RenderShape", "SpriteBillboard"): _r(0, 1, 2, 3),  # RenderShapeParams.BillboardType
    ("GpuParticles", "RenderColor", "ColorInheritType"): _r(0, 1, 2, 3),  # ParentEffectType
    ("GpuParticles", "RenderColor", "ColorAll", "Type"): _r(0, 1, 2, 3, 4),  # StandardColorType
    ("GpuParticles", "RenderMaterial", "Material"): _r(0, 1),  # RenderMaterialParams.MaterialType
    ("GpuParticles", "RenderMaterial", "ColorTexture", "Filter"): _r(0, 1),  # FilterType
    ("GpuParticles", "RenderMaterial", "ColorTexture", "Wrap"): _r(0, 1, 2),  # WrapType
    ("GpuParticles", "RenderMaterial", "NormalTexture", "Filter"): _r(0, 1),
    ("GpuParticles", "RenderMaterial", "NormalTexture", "Wrap"): _r(0, 1, 2),
}
ENUM_DOMAINS_180: dict[tuple[str, ...], frozenset[int]] = {**ENUM_DOMAINS_17, **_ADDED_IN_180}

# 1.6x (1.60-1.62e): TriggerParam はまだ無く、これらの列挙のメンバーも少ない。
ENUM_DOMAINS_16: dict[tuple[str, ...], frozenset[int]] = {
    **{k: v for k, v in ENUM_DOMAINS_17.items() if k[0] != "TriggerParam"},
    ("RendererCommonValues", "FadeOutType"): _r(0, 1),         # FadeOutMethod 2 が無い
    ("Sprite", "ColorAll"): _r(0, 1, 2, 3),                    # Gradient の無い StandardColorType
    ("DrawingValues", "Model", "Color"): _r(0, 1, 2, 3),
    ("RotationValues", "Type"): _r(0, 1, 2, 3, 4, 5),          # RotateToViewpoint が無い
}

# 1.5x (1.50RC1-1.51): さらに ModelReference が無く、location/scale の種類も少ない。
ENUM_DOMAINS_15: dict[tuple[str, ...], frozenset[int]] = {
    **{k: v for k, v in ENUM_DOMAINS_16.items() if k[-1] != "ModelReference"},
    ("LocationValues", "Type"): _r(0, 1, 2, 3),
    ("ScalingValues", "Type"): _r(0, 1, 2, 3, 4, 5),
    ("CommonValues", "LocationEffectType"): _r(0, 1, 2, 3),
}

_DOMAINS_BY_FAMILY = {"1.5": ENUM_DOMAINS_15, "1.6": ENUM_DOMAINS_16, "1.7": ENUM_DOMAINS_17,
                      "1.80": ENUM_DOMAINS_180}


def domains_for(profile: Profile) -> dict[tuple[str, ...], frozenset[int]]:
    return _DOMAINS_BY_FAMILY[profile.family]


def _domain_for(path: tuple[str, ...], domains: dict[tuple[str, ...], frozenset[int]]
                ) -> tuple[tuple[str, ...], frozenset[int]] | None:
    best = None
    for suffix, allowed in domains.items():
        if len(suffix) <= len(path) and path[-len(suffix):] == suffix:
            if best is None or len(suffix) > len(best[0]):
                best = (suffix, allowed)
    return best


def check_node(node: Elem, profile: Profile) -> list[str]:
    """``profile`` が対象とする Effekseer バージョンについて、``node`` 直下の
    列挙値域違反ごとに 1 つメッセージを返す (``<Children>`` 下の子 ``<Node>`` には
    降りない - :func:`check_project` 参照)。
    """
    domains = domains_for(profile)
    problems: list[str] = []

    def walk(e: Elem, path: tuple[str, ...]) -> None:
        for c in e.children:
            if c.tag == "Children":
                continue
            sub = path + (c.tag,)
            if c.children:
                walk(c, sub)
                continue
            text = (c.text or "").strip()
            try:
                value = int(text)
            except ValueError:
                continue
            hit = _domain_for(sub, domains)
            if hit is not None and value not in hit[1]:
                problems.append(
                    f"{'/'.join(sub)}={value} is not a valid Effekseer {profile.family} value "
                    f"(allowed: {sorted(hit[1])}); the Effekseer editor crashes on it"
                )

    walk(node, ())
    return problems


def check_project(project: Elem, profile: Profile) -> list[str]:
    """``<EffekseerProject>`` の全ノードに :func:`check_node` を実行する。
    各メッセージの先頭にはノードの ``[index.path]`` が付く (``show``/``--parent`` と
    同じ指定方式)。
    """
    return [f"{label}: {msg}" for _, label, node in walk_nodes(project)
            for msg in check_node(node, profile)]
