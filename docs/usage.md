# 使い方

- [1. 基本の考え方](#1-基本の考え方)
- [2. 基本の流れ](#2-基本の流れ)
- [3. コマンド一覧](#3-コマンド一覧)
- [4. 各コマンド](#4-各コマンド)
- [5. テクスチャ・モデル・サウンド](#5-テクスチャモデルサウンド)
- [6. Python から使う](#6-python-から使う)
- [7. AI エージェントから使う](#7-ai-エージェントから使う)
- [8. できないこと](#8-できないこと)

コマンドはすべて **`tools/` があるフォルダ**で `python -m tools.effect <コマンド>`（または `python tools/effect.py <コマンド>`）として実行します。
`python -m tools.effect <コマンド> --help` で、そのコマンドの全オプションを表示できます。

## 1. 基本の考え方

### ファイルの種類

| ファイル | 内容 | このツールでの扱い |
|---|---|---|
| `.efkproj` | エフェクトのソース（XML） | 作成・表示・検査・編集できます |
| `.efkefc` | コンパイル済みのエフェクト（ゲームが読み込むファイル） | `compile` で作り、`install` で配置します |

Effekseer のエディタで「保存」すると、`.efkproj` という名前でも中身が `.efkefc` 形式になることがあります。その形式はこのツールでは編集できません。

### ノードとパス

エフェクトは、ルートの下にノード（リング、スプライトなど）が木の形に並んだものです。
ノードには決まった ID がないので、このツールでは**ルートからの番号**でノードを指定します。

```
Root
  [0] Burst  [ring]
  [1] Glow  [sprite]
    [1.0] Trail  [ribbon]
```

- `0` はルートの 1 番目の子、`1.0` はルートの 2 番目の子の 1 番目の子です（番号は 0 から数えます）。
- ルート自体は `""`（空文字）または `root` です。
- `show` で、各ノードの番号を確認できます。ノードを追加・削除すると後ろのノードの番号が変わるので、編集の前に `show` で確認してください。

### 対象バージョンと ToolVersion

- **対象バージョン**（設定の `effekseer.version`）で、使える設定値の範囲と、コンパイルに使う `Effekseer.exe` が決まります。
- **ファイルの `ToolVersion`** で、Effekseer がそのファイルをどう読むかが決まります。
  `new-project` は `ToolVersion` を `0.7CTP1` で作ります。この形式は 1.50RC1〜1.80.7 のどのエディタでも開けて、このツールが書いた設定が全部正しく読まれます。
- 1.80 で追加された「トリガーで発生」などの設定だけは、`upgrade` で 1.80 の形式に変換したファイルでないと使えません。

詳しくは [versions.md](versions.md) を見てください。

## 2. 基本の流れ

```
python -m tools.effect new-project Spark --dir work
python -m tools.effect add-node work/Spark.efkproj --kind ring --name Burst --life 20 --color 255:200:120:255
python -m tools.effect add-node work/Spark.efkproj --kind sprite --name Glow --color-texture Texture/Particle01.png --max-generation 30 --generation-shape sphere --radius 0:0.5:1 --fade-out 10:0:-10
python -m tools.effect show work/Spark.efkproj
python -m tools.effect validate work/Spark.efkproj
python -m tools.effect compile work/Spark.efkproj
python -m tools.effect install work/Spark.efkefc --dest Effects/Spark.efkefc --project work/Spark.efkproj
```

`show` の出力例:

```
Root  (StartFrame=0 EndFrame=60 IsLoop=True ToolVersion=0.7CTP1, legacy CommonValues)
  [0] Burst  [ring]
  [1] Glow  [sprite]
```

見た目は、できた `.efkefc`（または `.efkproj`）を Effekseer のエディタで開いて確認してください。

## 3. コマンド一覧

| コマンド | 内容 |
|---|---|
| `new-project` | 空の `.efkproj` を作る |
| `show` | ノードの木とノード番号を表示する |
| `validate` | ファイルに問題がないか検査する |
| `add-node` | ノードを追加する |
| `set-params` | 既存のノードの設定を変える |
| `apply` | JSON に書いた複数の操作をまとめて適用する |
| `compile` | `.efkproj` を `.efkefc` にコンパイルする |
| `upgrade` | `.efkproj` を対象バージョンのエディタの形式に変換する |
| `install` | `.efkefc` をテクスチャなどと一緒にプロジェクトへ配置する |
| `check-env` | 設定と `Effekseer.exe` を確認する |
| `selftest` | ツールのセルフテストを実行する |
| `export` | ツールの配布用ファイルを別のフォルダにコピーする（メンテナ向け） |

書き込むコマンド（`add-node`・`set-params`・`apply`）は、問題が見つかると**ファイルを一切変更せずに**エラーで終わります。
`apply` は、途中の操作が 1 つでも失敗すると、それまでの操作も含めて何も書き込みません。

## 4. 各コマンド

### new-project

```
python -m tools.effect new-project <名前> [--dir フォルダ] [--start 0] [--end 60] [--loop true|false] [--force]
```

`<フォルダ>/<名前>.efkproj` を作ります。`--start`/`--end` は再生範囲のフレーム、`--loop` はループ再生するかどうかです。
同じ名前のファイルがあると止まります（`--force` で上書き）。

### show

```
python -m tools.effect show <ファイル>
```

ノードの木を、ノード番号・名前・種類付きで表示します。1 行目には `ToolVersion` と、そのファイルの形式（`legacy` / `v180`）も表示します。

### validate

```
python -m tools.effect validate <ファイル> [--effekseer-version バージョン]
```

次の点を検査し、問題があれば一覧を表示して終了コード 1 で終わります。

- XML として壊れていないか、必要な要素があるか
- 対象バージョンのエディタで**クラッシュする設定値**がないか（例: 1.7 向けに Billboard=4）
- ファイルの `ToolVersion` に合わない書き方で、Effekseer に**黙って捨てられる・上書きされる設定**がないか
- `ToolVersion` が対象バージョンのエディタより新しくないか
- 参照しているテクスチャ・モデル・サウンドが、`.efkproj` から見た場所に存在するか
- このツールが扱っていない種類のノードがないか

選んだバージョンに存在しない機能（1.7 向けに GPU パーティクルなど）は、エラーではなく警告になります（そのバージョンでは無視されます）。

### add-node

```
python -m tools.effect add-node <ファイル> --kind <種類> [--name 名前] [--parent ノード番号] [オプション...]
```

`--parent` のノードの子として、新しいノードを最後に追加します（省略するとルートの子）。

`--kind` の種類:

| 種類 | 内容 |
|---|---|
| `sprite` | 板ポリゴン（パーティクルの基本） |
| `ring` | リング（衝撃波など） |
| `ribbon` | リボン（軌跡） |
| `model` | モデル（`--model` でモデルファイルの指定が必須） |
| `track` | トラック（軌跡） |
| `group` | 何も描画しない、子ノードをまとめるためのノード |

**値の書き方**

| 書き方 | 意味 | 例 |
|---|---|---|
| `中央値` または `最小:中央:最大` | 固定値、または範囲からランダム | `--life 30`、`--life 20:30:40` |
| `R:G:B[:A]` | 色（0〜255、A を省略すると 255） | `--color 255:200:120` |
| `FRAME[:開始の速さ[:終了の速さ]]` | フェードのフレーム数と、かかり方 | `--fade-out 10:0:-10` |
| トリガー | `none`、`trigger0`〜`trigger3`、`parent-removed`・`parent-collided`（1.80 のみ）、または数値 | `--trigger-to-remove trigger1` |

フェードやイージングの「速さ」は、`-30,-20,-10,0,10,20,30` の 7 つだけです（負はゆっくり、正は急に、0 は一定）。
これ以外の値は Effekseer がコンパイルできてもエディタがクラッシュするので、このツールは受け付けません。

**オプション**

| オプション | 設定される項目 | 使える種類 |
|---|---|---|
| `--life` | 寿命（フレーム） | すべて |
| `--max-generation`、`--infinite true\|false` | 生成数、無限に生成するか | すべて |
| `--generation-time` | 生成間隔 | すべて |
| `--trigger-to-start`、`--trigger-to-stop`、`--trigger-to-remove` | 生成開始・停止・削除のトリガー | すべて |
| `--generation-timing continuous\|trigger`、`--trigger`、`--trigger-count` | トリガーで発生させる設定 | すべて（**1.80 形式のファイルのみ**。`upgrade` してから使います） |
| `--color-texture` | 色テクスチャのパス（`.efkproj` からの相対パス） | すべて |
| `--fade-in`、`--fade-out` | フェードイン・フェードアウト | すべて |
| `--uv-scroll SX:SY` | UV スクロールの速さ | すべて |
| `--generation-shape circle\|sphere\|point` | 生成位置の形 | すべて |
| `--radius`、`--division`、`--angle-start`、`--angle-end` | 生成位置の半径（circle/sphere）、分割数・角度（circle） | すべて |
| `--billboard N` | ビルボード（0=常にカメラを向く、1=Y 軸固定、2=固定、3=回転ビルボード、4=方向ビルボード（1.80 のみ）） | `sprite` |
| `--color R:G:B[:A]` | 色（ring は外側・中央・内側すべて） | `sprite`・`ribbon`・`ring`・`model` |
| `--color-random R,G,B[,A]` | ランダムな色（各チャンネルを `中央値` または `最小:中央:最大` で指定） | `sprite` |
| `--model`、`--lighting true\|false` | モデルファイル、ライティング | `model` |
| `--track-color R:G:B[:A]` | 6 本のレールすべての色 | `track` |
| `--set パス=値` | 上にない任意の項目（何回でも指定可） | すべて |

`upgrade` で 1.80 の形式に変換したファイルでは、古い形式でしか書けないオプション（`sprite`/`model` の `--color`、`--track-color` など）が使えません。
その場合は `--set` で 1.80 の形式の項目名を指定してください（例: `--set DrawingValues.ColorAll.Fixed.R=255`）。

**`--set` の書き方**

`--set` のパスは、Effekseer の `.efkproj` の XML のタグ名を `.` でつないだものです。

```
--set DrawingValues.Ring.CenterRatio_Fixed=0.85
--set RendererCommonValues.AlphaBlend=2
--set CommonValues.MaxGeneration.Infinite=True
```

- タグ名は**大文字・小文字を区別します**（`center` と書くと Effekseer に無視されます）。
- 真偽値は `True` / `False` です。
- どんなタグ名でも書き込めてしまうので、実在する項目名かどうかは、Effekseer のエディタで保存したファイルやサンプルの `.efkproj` で確認してください。
  設定値の範囲（選択肢の番号）と、ファイル形式に合っているかは、ツールがチェックします。

### set-params

```
python -m tools.effect set-params <ファイル> --path <ノード番号> --set パス=値 [--set パス=値 ...]
```

既存のノードの項目を設定します。`--set` の書き方は `add-node` と同じです。

### apply

```
python -m tools.effect apply <ファイル> <操作.json>
```

複数の操作を JSON の配列にまとめて、一度に適用します。スクリプトや AI エージェントから使うのに向いています。

```json
[
  {"op": "add-node", "kind": "sprite", "name": "Smoke",
   "set": {"RendererCommonValues.ColorTexture": "Texture/Particle01.png", "DrawingValues.Sprite.Billboard": 0}},
  {"op": "add-node", "parent": "0", "kind": "group", "name": "Children"},
  {"op": "add-node", "kind": "model", "name": "Rock", "model": "Model/rock.efkmodel"},
  {"op": "set-params", "path": "0", "set": {"CommonValues.MaxGeneration.Value": 12}}
]
```

| 操作 | キー |
|---|---|
| `add-node` | `kind`（必須）、`name`、`parent`（省略するとルート）、`model`（`kind` が `model` のとき必須）、`set` |
| `set-params` | `path`（必須）、`set` |

操作は上から順に実行されるので、後の操作では、前の操作で追加したノードの番号を使えます。
1 つでも失敗すると、ファイルは一切変更されません。

### compile

```
python -m tools.effect compile <ファイル> [--out 出力.efkefc] [--effekseer-version バージョン] [--cui-path Effekseer.exe]
```

対象バージョンの `Effekseer.exe` で `.efkefc` にコンパイルします（省略すると `.efkproj` と同じ場所・同じ名前）。

Effekseer 自体は次のような場合でもエラーを出さずに終わってしまうので、このツールは**コンパイルする前に止めます**。

- 参照しているテクスチャ・モデル・サウンドが存在しない（そのままだと、それが表示されないエフェクトになります）
- `--out` が `.efkproj` と別のフォルダ（テクスチャのパスがずれます）
- ファイルの形式に合わない書き方の設定がある（その設定が捨てられます）
- ファイルの `ToolVersion` が `Effekseer.exe` より新しい（Effekseer は何も出力せずに終わります）
- `Effekseer.exe` のバージョンが対象バージョンと違う系列

コンパイル後は、出力が対象バージョンの形式になっているか（バイナリのバージョン番号）を確認します。

### upgrade

```
python -m tools.effect upgrade <ファイル> [--out 出力.efkproj] [--effekseer-version バージョン] [--cui-path Effekseer.exe]
```

`.efkproj` を、対象バージョンのエディタの形式に変換します（`--out` を省略すると上書き）。
変換は Effekseer 自身が行います（`.efkefc` の中に保存されるエディタ用データを取り出します）。

主な用途は、1.80 で追加された「トリガーで発生」などを使うことです。

```
python -m tools.effect upgrade work/Spark.efkproj --effekseer-version 1.80.7
python -m tools.effect add-node work/Spark.efkproj --kind sprite --name Burst --generation-timing trigger --trigger trigger0 --trigger-count 5
```

変換後のファイルは、そのバージョン以降のエディタでしか開けません。また、古い形式でしか書けないオプションは使えなくなります（`add-node` の説明を参照）。

### install

```
python -m tools.effect install <.efkefc> --dest <配置先.efkefc> [--project <元の.efkproj>]
```

`.efkefc` を `--dest` にコピーします。

- エフェクトが使うテクスチャ・モデルも、`--dest` の隣に同じフォルダ構成でコピーします。
- `--project` を付けると、`.efkproj` も `<effect_dir>/<source_subdir>/` にコピーし、中のパスをインストールしたテクスチャを指すように書き換えます。
- `project.runtime_version` が設定されていると、そのランタイムで読み込めないエフェクト（新しいバージョンでコンパイルしたもの）を拒否します。
- 次の場合は、何もコピーせずに止まります: テクスチャが見つからない、テクスチャのパスがエフェクトのフォルダの外（`../`）を指している、同じ名前で中身の違うファイルがすでにある。
- `meta.enabled` が `true` のときは、NanamiEngine 用の `.meta` も作ります（すでにあればそのまま残します）。

### check-env

```
python -m tools.effect check-env [--effekseer-version バージョン] [--cui-path Effekseer.exe]
```

設定の読み込み結果、使う `Effekseer.exe`、そこから判定したバージョンなどを表示します（[setup.md](setup.md#6-動作確認)）。

### selftest

```
python -m tools.effect selftest
```

ツールのセルフテストです。`effekseer.cui_paths` に登録したすべての `Effekseer.exe` でコンパイルのテストも行います（[development.md](development.md#セルフテスト)）。

## 5. テクスチャ・モデル・サウンド

- パスは、**`.efkproj` から見た相対パス**で書きます。`work/Spark.efkproj` から `work/Texture/Particle01.png` を使うなら `Texture/Particle01.png` です。
- 存在しないファイルを指していると、`add-node` などは警告を出し、`validate` と `compile` はエラーになります。
- Effekseer はコンパイル結果の中に、`.efkefc` から見た相対パスでテクスチャの場所を記録します。
  そのため、`.efkefc` だけを別の場所にコピーするとテクスチャが見つからなくなります。配置には `install` を使ってください。
- サンプル素材の `.efkproj` には、作者の PC のパス（`../` から始まるパスなど）が残っていることがあります。`validate` で確認できます。

## 6. Python から使う

たくさんの設定を組み合わせるときは、コマンドを並べるより、Python から `tools.effect.presets` の関数でノードを組み立てるほうが簡単です。

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # tools/ があるフォルダ

from tools.effect import presets as p, xmlio

burst = p.ring_node(
    "Burst",
    ring_block=p.ring(
        outer=p.xyz("Location", x=2.0),
        inner=p.xyz("Location", x=1.6),
        outer_color=p.color("OuterColor_Fixed", r=255, g=200, b=120, a=0),
        center_color=p.color("CenterColor_Fixed", r=255, g=220, b=160, a=255),
        inner_color=p.color("InnerColor_Fixed", r=255, g=200, b=120, a=0),
    ),
    common=p.common_values(layout="legacy", max_generation=1,
                           life={"center": 20, "max": 20, "min": 20}),
    scaling=p.scaling_values(single_easing=p.easing(
        "SingleEasing",
        start=p.pva("Start", center=0.2, max=0.2, min=0.2),
        end=p.pva("End", center=1.5, max=1.5, min=1.5),
        start_speed=0, end_speed=-20)),
)

sparks = p.sprite_node(
    "Sparks",
    sprite_block=p.sprite(color_all=p.color("ColorAll_Fixed", r=255, g=230, b=180, a=255)),
    common=p.common_values(layout="legacy", max_generation=30,
                           life={"center": 30, "max": 40, "min": 20}),
    generation_location=p.generation_location_sphere(radius={"center": 0.5, "max": 1.0, "min": 0.0}),
    renderer_common=p.renderer_common(color_texture="Texture/Particle01.png", alpha_blend=2,
                                      fade_out={"frame": 10, "start_speed": 0, "end_speed": -10}),
)

project = p.new_project(end_frame=60, root_children=[burst, sparks])
xmlio.write(Path("work/SparkFromPython.efkproj"), project)
```

作ったファイルは、`validate` → `compile` してください（Python の関数がチェックするのはイージングの速さなど一部だけで、設定値の範囲やファイル形式の検査は `validate` で行います）。

```
python scripts/make_spark.py
python -m tools.effect validate work/SparkFromPython.efkproj
python -m tools.effect compile work/SparkFromPython.efkproj
```

主な関数:

| 関数 | 作るもの |
|---|---|
| `new_project(root_children=[...], start_frame=, end_frame=, is_loop=)` | プロジェクト全体 |
| `sprite_node` / `ring_node` / `ribbon_node` / `model_node` / `track_node` / `group_node` / `node` | ノード |
| `sprite` / `ring` / `ribbon` / `model` / `track` | 種類ごとの描画設定 |
| `common_values(layout=...)` | 寿命・生成数・生成間隔・削除条件など。`layout` はファイルの形式（`new-project` で作ったファイルなら `"legacy"`、`upgrade` した 1.80 のファイルなら `"v180"`） |
| `location_values` / `rotation_values` / `scaling_values` / `location_abs_values` | 位置・回転・拡大・重力や引力 |
| `generation_location_point` / `generation_location_circle` / `generation_location_sphere` | 生成位置 |
| `renderer_common` | テクスチャ・ブレンド・フェード・UV |
| `sound_values` | サウンド |
| `pva` / `easing` / `color` / `random_color` / `xyz` / `elem` | 値の組み立て |

各関数の引数は、`tools/effect/presets.py` の docstring に説明があります。

## 7. AI エージェントから使う

このツールは、PC 上でコマンドを実行できる AI エージェントに使わせることを前提に作っています。
セットアップやエフェクトの頼み方の例は、[README のクイックスタート](../README.md#クイックスタート)にあります。うまくいくコツ:

- `.efkproj` の XML を直接書き換えさせず、`add-node`・`set-params`・`apply` を使わせてください（値の範囲やファイル形式のチェックが働きます）。
- 複数の変更は、`apply` の JSON にまとめさせると確実です（途中で失敗しても何も書き込まれません）。
- 編集の前後に `show` でノード番号を、編集の後に `validate` で問題がないことを確認させてください。
- エラーメッセージには、原因と直し方が書いてあります。そのまま読ませてください。
- 見た目は AI には確認できないので、最後は Effekseer のエディタで人が確認してください。

## 8. できないこと

- **ノードの種類**: 扱えるのは sprite・ring・ribbon・model・track と、何も描画しないノードです。
  それ以外の描画の種類や、GPU パーティクル・衝突（1.80）は `--set` で項目を直接書けますが、専用のオプションはありません。
- **F カーブ（キーフレーム）**: 位置・回転・拡大・色の F カーブは作れません。
- **`.efkefc` から `.efkproj` への逆変換**: できません。このツールは新しいエフェクトを作るためのものです。
  （`upgrade` は `.efkproj` をコンパイルした結果からエディタ用データを取り出しますが、既存の `.efkefc` を編集可能にする機能ではありません。）
- **エディタで保存した `.efkefc` 形式の `.efkproj`**: 編集できません。
- **すべての項目名のチェック**: 設定値の範囲とファイル形式はチェックしますが、`--set` で書いた項目名が実在するかまではチェックしません。
- **見た目の確認**: エフェクトの見た目は、Effekseer のエディタで確認してください。
- **Effekseer の同時実行**: `Effekseer.exe` を同時に複数動かすと、まれに何も出力せずに失敗することがあります（[troubleshooting.md](troubleshooting.md)）。
