# セットアップ

このツールを使えるようにするまでの手順と、設定ファイル `tools/effect/effect_config.json` の全項目の説明です。

- [1. 動作環境](#1-動作環境)
- [2. Python のインストール](#python-のインストール)
- [3. Effekseer の用意](#3-effekseer-の用意)
- [4. ツールの入手と配置](#4-ツールの入手と配置)
- [5. 設定ファイル](#5-設定ファイル)
- [6. 動作確認](#6-動作確認)
- [7. 自分のプロジェクトに組み込む](#7-自分のプロジェクトに組み込む)

## 1. 動作環境

| 項目 | 内容 |
|---|---|
| Python | **3.10 以上**（3.13 / 3.14 で動作確認済み）。標準ライブラリだけを使うので `pip install` は不要です |
| OS | **Windows**（動作確認は Windows 11）。`compile` と `upgrade` は Effekseer の `Effekseer.exe` を実行するので Windows が必要です |
| Effekseer | `compile` と `upgrade` に必要。**1.50RC1 〜 1.80.7** の全リリースに対応（[versions.md](versions.md)） |
| AI エージェント | PC 上でコマンドを実行できる版なら使えます。ブラウザで使う AI では使えません |

## Python のインストール

コマンドプロンプトか PowerShell で、Python が入っているか確認します。

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
   このチェックを忘れると `python` コマンドが使えません（その場合はインストーラーを起動し直して「Modify」から設定するか、入れ直してください）。
3. インストールが終わったら、**コマンドプロンプト / PowerShell を一度閉じて開き直し**、もう一度 `python --version` で確認します。

`winget` が使える場合は、`winget install Python.Python.3.13` でもインストールできます。

Python 3.10 より古いバージョンでこのツールを実行すると、インストールを案内するメッセージを表示して終了します。

## 3. Effekseer の用意

Effekseer はこのツールに含まれていません。[Effekseer のリリースページ](https://github.com/effekseer/Effekseer/releases)から、
使いたいバージョンの **Windows 版ツール**（`Effekseer1.80.7Win.zip` のような名前の zip）をダウンロードして、好きな場所に展開してください。

使うのは展開したフォルダの中の `Effekseer.exe` です。

| バージョン | `Effekseer.exe` の場所（展開したフォルダから見て） |
|---|---|
| 1.80 系 | `Tool/Effekseer.exe`（中で `Tool/bin/Effekseer.exe` を起動するランチャーです。どちらを設定してもかまいません） |
| 1.51 〜 1.7 系 | `Tool/Effekseer.exe` |
| 1.50RC1 / RC2 | `Effekseer.exe`（`Tool` フォルダがありません） |

**どのバージョンを使うか**: ゲームで使っている Effekseer のランタイム（Unity 用、DX ライブラリ用などのプラグイン）と**同じ系列**を選んでください。
新しい系列でコンパイルしたエフェクトは、古いランタイムでは読み込めません。

複数のバージョンを別々のフォルダに展開して、設定ファイルに並べて登録できます（次の章）。

## 4. ツールの入手と配置

**このツールだけで使う場合**は、リポジトリを clone します。

```
git clone https://github.com/ramasuke/EffekseerEfkprojTool.git
```

**自分のプロジェクトに組み込む場合**は、`tools/` フォルダをプロジェクトの直下にコピーします。

```
<プロジェクト>/
  tools/
    effect.py           # python tools/effect.py ... で起動するための入口
    effect/             # ツール本体（effect_config.json、testdata/ を含む）
    common/             # 共通モジュール
```

- フォルダ名は `tools` のままにしてください（`python -m tools.effect` で読み込むため）。
- コマンドは **`tools/` があるフォルダ**で実行します（`python tools/effect.py <コマンド>` でも同じです）。
- 自分のプロジェクトにすでに `tools/` フォルダがある場合は、`tools/effect.py`・`tools/effect/`・`tools/common/` をその中に置いてください。
  `tools/common/` に同じ名前のファイルがある場合は中身を比べてください。

## 5. 設定ファイル

PC やプロジェクトによって変わる値は、すべて `tools/effect/effect_config.json` に書きます。直接編集してください。

> [!NOTE]
> **書く必要があるのは `effekseer.version` と `effekseer.cui_paths` の 2 つだけです。** ほかの項目は、変更しなくても使えます。
> 下の表の残りの項目は、ゲームのプロジェクトに組み込むときなど、必要になったときだけ変更してください。

```json
{
    "effekseer": {
        "version": "1.80.7",
        "cui_paths": {
            "1.80.7": "D:/Effekseer1.80.7Win/Tool/Effekseer.exe",
            "1.62e": "D:/Effekseer162eWin/Tool/Effekseer.exe"
        }
    },
    "project": {
        "root": "",
        "effect_dir": "Effects",
        "source_subdir": "_Source",
        "runtime_version": "1.80"
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

### effekseer

| キー | 説明 |
|---|---|
| `effekseer.version` | 使う Effekseer のバージョン（例: `1.62e`、`1.7.3.0`、`1.80.7`）。`compile` / `upgrade` で起動する `Effekseer.exe`、使える設定値の範囲、コンパイル結果のチェック内容がこれで決まります。空欄にすると、見つかった `Effekseer.exe` のバージョンを自動で判定します（それも無ければ `1.7.3.0` として扱います） |
| `effekseer.cui_paths` | バージョンごとの `Effekseer.exe` のパス。`effekseer.version` と同じバージョンのものを使い、無ければ同じ系列のもの（例: `1.80.2` を選んだときの `1.80.7`）を使います。**使うバージョンの 1 つだけ書けば動きます** |
| `effekseer.cui_path` | 以前の書き方（`Effekseer.exe` を 1 つだけ書く）。今も使えます。以前の `effekseer.verified_version` も `effekseer.version` として読みます |

### project

| キー | 説明 |
|---|---|
| `project.root` | プロジェクトのルートフォルダ。空なら `tools/` があるフォルダです。相対パスはこの設定ファイルがあるフォルダが基準です |
| `project.effect_dir` | `install` でエフェクトを置くフォルダ（`project.root` からの相対パス） |
| `project.source_subdir` | `install --project` で `.efkproj` をコピーするフォルダ名（`<effect_dir>/<source_subdir>/` に置かれます） |
| `project.runtime_version` | ゲームで使っている Effekseer ランタイムの系列（`1.5`、`1.6`、`1.7`、`1.80` のどれか）。設定すると、`install` がランタイムで読み込めないエフェクトを拒否します。空ならチェックしません |

### meta / selftest

| キー | 説明 |
|---|---|
| `meta.enabled` | `true` にすると、`install` が NanamiEngine（このツールの開発元のゲームエンジン）形式の `.efkefc.meta` を作ります。**NanamiEngine 以外では `false` のままにしてください** |
| `meta.asset_type` | `.meta` に書くアセット型名（`meta.enabled` が `true` のときだけ使います） |
| `selftest.corpus_dir` | セルフテストで検査する `.efkproj` サンプル集のフォルダ。空ならそのテストはスキップされます |

### 書き方の注意

- **Windows のパスは `/` で区切る**か、`\\` のように `\` を 2 つ重ねてください。`C:\Effekseer\Tool\Effekseer.exe` のように `\` を 1 つで書くと JSON のエラーになります。
- `cui_paths`・`cui_path`・`effect_dir`・`corpus_dir` の相対パスは `project.root` が基準です。空文字は「設定なし」です。

### 一時的に別のバージョンや Effekseer.exe を使う

設定ファイルを書き換えずに、コマンドや環境変数で上書きできます。

| 上書きしたいもの | 優先順位（左ほど優先） |
|---|---|
| 使うバージョン | `--effekseer-version <バージョン>` → 環境変数 `EFFEKSEER_VERSION` → `effekseer.version` |
| `Effekseer.exe` | `--cui-path <パス>` → 環境変数 `EFFEKSEER_CUI` → `effekseer.cui_paths` → `effekseer.cui_path` |

```
python -m tools.effect compile work/Spark.efkproj --effekseer-version 1.62e
```

指定した `Effekseer.exe` が、使うバージョンと違う系列（1.7 と 1.80 など）だと、`compile` と `upgrade` はエラーで止まります。

## 6. 動作確認

```
python -m tools.effect check-env
python -m tools.effect selftest
```

**`check-env`** は、設定を読み込んだ結果を表示します。

- `target version` — 使うバージョンと、それがどこから決まったか
- `Effekseer CUI` — 使う `Effekseer.exe`、実際に実行するファイル（`runs`）、`Effekseer.exe` から判定したバージョン（`CUI version`）
- `runtime version` — `install` のランタイムチェックの設定

最後が `OK.` なら準備完了です。`Effekseer.exe` が見つからない場合や、そのバージョンが設定と違う系列の場合はエラーで終わります。
`--effekseer-version 1.62e` を付けると、別のバージョンの設定を確認できます。

**`selftest`** は、ツールが正しく動くかを確かめるテストです。最後が `N/N checks passed` になれば OK です。

- `skipped` と出るテストは、その PC に無いもの（Effekseer やサンプル集など）を使うテストなので問題ありません。
- `effekseer.cui_paths` に登録した**すべての** `Effekseer.exe` で、実際にコンパイルするテストを行います。
  1 つのバージョンにつき数十秒〜1 分ほどかかります。

## 7. 自分のプロジェクトに組み込む

ゲームのプロジェクトで使う場合は、次のように設定するとコンパイルから配置までが 1 回で済みます。

1. `tools/` をプロジェクト直下にコピーします（[4 章](#4-ツールの入手と配置)）。
2. `project.effect_dir` を、ゲームがエフェクトを読み込むフォルダ（例: `Assets/Effects`）にします。
3. `project.runtime_version` を、ゲームが使う Effekseer ランタイムの系列にします。
4. エフェクトの作業は、`effect_dir` の外（例: `work/`）で行います。
5. できあがったら `install` で配置します。

```
python -m tools.effect compile work/Spark.efkproj
python -m tools.effect install work/Spark.efkefc --dest Assets/Effects/Spark.efkefc --project work/Spark.efkproj
```

- `install` は、エフェクトが使うテクスチャ・モデルも `--dest` の隣に同じフォルダ構成でコピーします。
- `--project` を付けると、ソースの `.efkproj` も `<effect_dir>/<source_subdir>/` にコピーし、中のテクスチャのパスをインストール先を指すように書き換えます。
- 同じ名前で中身の違うテクスチャがすでにある場合は、上書きせずにエラーで止まります。

コマンドの詳しい使い方は [usage.md](usage.md) を見てください。
