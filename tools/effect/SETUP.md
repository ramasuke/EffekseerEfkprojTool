# `tools/effect` セットアップガイド

Effekseer のパーティクルエフェクト（`.efkproj`）を Python のコマンドで作成・編集し、Effekseer の CUI で
`.efkefc` にコンパイルして、プロジェクトのエフェクト用フォルダへインストールするツールです。
コマンドの詳しい説明と既知の制限は [`README.md`](README.md)（英語）を見てください。

公開リポジトリ: https://github.com/ramasuke/EffekseerEfkprojTool

## 1. Effekseer のバージョン違いによるエラーについて

このツールは **Effekseer 1.7.3.0** で検証しています。これと違うバージョンの Effekseer を使っていると、
作成したエフェクトを**ロードするときにエラーが出る**可能性があります。

その場合は **NiceBody に連絡してください**。
[Issues](https://github.com/ramasuke/EffekseerEfkprojTool/issues) に、使っている Effekseer のバージョンと
エラーの内容を書いてください。そのバージョンに対応したツールを作れるか試します。

## 2. 動作環境

| 項目 | 内容 |
|---|---|
| Python | **Python 3.10 以上**（3.13 / 3.14 で動作確認済み）。Python に最初から入っている標準ライブラリだけを使うので、`pip install` は不要です。**Python が入っていない場合は、下の「Python のインストール」の手順でインストールしてください** |
| OS | Windows（動作確認は Windows 11 のみ）。`compile` は Effekseer の `Effekseer.exe` を使うので Windows が必要です |
| Effekseer | `compile` に必要。検証済みのバージョンは **1.7.3.0**（上の注意を参照） |

Effekseer はこのツールに同梱していません。公式サイトからダウンロードして、好きな場所に展開してください。
使うのは展開したフォルダの中の `Tool/Effekseer.exe` です。

### Python のインストール

まず、コマンドプロンプトか PowerShell で次のコマンドを実行して、Python が入っているか確認します。

```
python --version
```

- `Python 3.10.x` 以上（`3.13.x` など）が表示されたら、インストール済みです。次の章へ進んでください。
- 次のどれかになった場合は、Python が入っていないか古いので、インストールしてください。
  - `Python was not found; run without arguments to install from the Microsoft Store ...` と表示される
  - `'python' は、内部コマンドまたは外部コマンド...として認識されていません` と表示される
  - Microsoft Store が開く
  - `Python 3.9.x` 以下が表示される

インストール手順:

1. https://www.python.org/downloads/ を開いて、最新の Python 3 のインストーラーをダウンロードします。
2. インストーラーを起動し、最初の画面の下にある **「Add python.exe to PATH」にチェックを入れて**から「Install Now」を押します。
   このチェックを忘れると、`python` コマンドが使えません（その場合はインストーラーを起動し直して「Modify」から設定するか、アンインストールしてから入れ直してください）。
3. インストールが終わったら、**コマンドプロンプト / PowerShell を一度閉じて開き直し**、もう一度 `python --version` で確認します。

`winget` が使える場合は、`winget install Python.Python.3.13` でもインストールできます。

Python の標準ライブラリは Python 本体と一緒にインストールされるので、別に入れる必要はありません。
このツールは Python 3.10 より古いバージョンで実行すると、インストールを案内するメッセージを表示して終了します。

## 3. 入手と配置

- **このツールだけを使う場合**: 公開リポジトリを clone します。
- **自分のプロジェクトに組み込む場合**: `tools/` フォルダをプロジェクトの直下にコピーします。

必要なファイルは次のとおりです（公開リポジトリの中身と同じです）。

```
<プロジェクト>/
  tools/
    effect.py                 # python tools/effect.py ... で起動するための入口
    effect/                   # ツール本体（effect_config.json、testdata/ を含む）
    common/
      __init__.py
      cereal_json.py
      meta_base.py
```

- フォルダ名は `tools` のままにしてください（`python -m tools.effect` で読み込むため）。
- コマンドは **`tools/` があるフォルダ**で実行します。

## 4. 設定ファイル `tools/effect/effect_config.json`

PC やプロジェクトによって変わる値は、すべてこのファイルに書きます。自分の環境に合わせて直接編集してください。

```json
{
    "effekseer": {
        "cui_path": "D:/Effekseer1.7.3.0Win/Tool/Effekseer.exe",
        "verified_version": "1.7.3.0"
    },
    "project": {
        "root": "",
        "effect_dir": "Effects",
        "source_subdir": "_Source"
    },
    "meta": {
        "enabled": false,
        "asset_type": "NanamiEngine::Module::Asset::ParticleFile"
    },
    "selftest": {
        "corpus_dir": ""
    }
}
```

| キー | 説明 |
|---|---|
| `effekseer.cui_path` | `Effekseer.exe`（`Tool/` フォルダの中）のパス。`compile` で使います。**最低限ここだけ設定すれば動きます** |
| `effekseer.verified_version` | このツールを検証した Effekseer のバージョン。表示とエラーメッセージに使うだけで、Effekseer の実際のバージョンのチェックはしません |
| `project.root` | プロジェクトのルートフォルダ。空なら `tools/` があるフォルダ。相対パスはこの設定ファイルがあるフォルダが基準です |
| `project.effect_dir` | `install` でエフェクトを置くフォルダ |
| `project.source_subdir` | `install --project` で `.efkproj` を置くフォルダ名（`<effect_dir>/<source_subdir>/` にコピーされます） |
| `meta.enabled` | `true` にすると `install` が NanamiEngine 形式の `.efkefc.meta` を作ります。NanamiEngine 以外のプロジェクトでは `false` にしてください |
| `meta.asset_type` | `.meta` に書くアセット型名（`meta.enabled` が `true` のときだけ使います） |
| `selftest.corpus_dir` | セルフテストで検査する `.efkproj` のサンプル集のフォルダ。空ならそのテストはスキップされます |

書き方の注意:

- **Windows のパスは `/` で区切る**か、`\\` のように `\` を 2 つ重ねて書いてください。`C:\Effekseer\Tool\Effekseer.exe` のように
  `\` を 1 つで書くと JSON のエラーになります。
- `cui_path`・`effect_dir`・`corpus_dir` の相対パスは `project.root` が基準です。空文字は「設定なし」です。
- 一時的に別の `Effekseer.exe` を使いたいときは、`compile --cui-path <パス>` か環境変数 `EFFEKSEER_CUI` でも指定できます
  （優先順位: `--cui-path` > `EFFEKSEER_CUI` > 設定ファイル）。

## 5. 動作確認

```
python -m tools.effect check-env
python -m tools.effect selftest
```

- `check-env` は設定ファイルを読み込んだ結果（パスとそのファイルがあるかどうか）を表示します。`Effekseer.exe` が見つからないと
  エラーで終わります。
- `selftest` の最後が `N/N checks passed` になれば OK です。`skipped` と出るテストは、その PC に無いもの
  （Effekseer やサンプル集など）を使うテストなので問題ありません。

## 6. 使い方の例

```
python -m tools.effect new-project Spark --dir work
python -m tools.effect add-node work/Spark.efkproj --kind ring --name Burst
python -m tools.effect add-node work/Spark.efkproj --kind sprite --name Glow
python -m tools.effect show work/Spark.efkproj
python -m tools.effect compile work/Spark.efkproj
python -m tools.effect install work/Spark.efkefc --dest Effects/Spark.efkefc
```

各コマンドの詳しいオプションは [`README.md`](README.md) か `python -m tools.effect <コマンド> --help` を見てください。

## 7. よくあるエラー

| エラー | 原因と対処 |
|---|---|
| `Python was not found` / `'python' は、内部コマンドまたは外部コマンド...` / Microsoft Store が開く | Python がインストールされていないか、PATH が通っていません。2 章の「Python のインストール」を見てください |
| `tools.effect には Python 3.10 以上が必要です` | Python が古いです。2 章の手順で新しい Python をインストールしてください |
| `No module named tools.effect` | `tools/` があるフォルダ以外でコマンドを実行しています。`tools/` があるフォルダに移動してから実行してください |
| `Effekseer CUI (Tool/Effekseer.exe) not found` | `effekseer.cui_path` が空か、パスが間違っています。`check-env` で試したパスを確認してください |
| `invalid JSON at line N column M` | 設定ファイルの JSON が壊れています。多いのはパスの `\` が 1 つのままになっているケースです（4 章を参照） |
| `config file not found` | `tools/effect/effect_config.json` がありません。公開リポジトリから取り直してください |
| エフェクトをロードするときにエラーが出る | Effekseer のバージョンが 1.7.3.0 と違う可能性があります。1 章のとおり NiceBody に連絡してください |
| テクスチャが表示されない | `compile --out` で `.efkproj` と別のフォルダに出力すると、テクスチャのパスがずれます。`.efkproj` と同じフォルダでコンパイルしてから `install --dest` で配置してください。`install` は足りないテクスチャを警告で表示します |

## 8. NanamiEngine からの更新（メンテナ向け）

このツールの正本は NanamiEngine リポジトリの `tools/effect/` です。公開リポジトリは次の手順で更新します。

```
python -m tools.effect export --out <EffekseerEfkprojTool の clone 先>
```

`export` は配布するファイルだけをコピーし、設定ファイルは個人のパスを含まない配布用（`tools/effect/dist/effect_config.json`）に
差し替えます。そのあと公開リポジトリ側で `selftest` を実行し、commit / push してください。
