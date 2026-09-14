# 開発者向け

ツールを改造したい人、仕組みを知りたい人向けの説明です。

- [構成](#構成)
- [セルフテスト](#セルフテスト)
- [バージョン対応の仕組みと確かめ方](#バージョン対応の仕組みと確かめ方)
- [機能を追加するとき](#機能を追加するとき)
- [このリポジトリの更新方法](#このリポジトリの更新方法)

## 構成

Python 3.10 以上の標準ライブラリだけで書かれています。外部パッケージを追加しないでください。

| ファイル | 役割 |
|---|---|
| `tools/effect.py` | `python tools/effect.py ...` 用の入口 |
| `tools/effect/__main__.py` | `python -m tools.effect ...` の入口（コマンドの登録） |
| `tools/effect/__init__.py` | Python のバージョンチェック |
| `tools/effect/cli.py` | 全コマンドの実装。対象バージョンと `Effekseer.exe` の決定（`resolve_effekseer`）もここ |
| `tools/effect/config.py` | `effect_config.json` の読み込みと検査 |
| `tools/effect/versions.py` | バージョン番号の解釈（Effekseer の `Core.ParseVersion` の移植）、系列ごとの設定（`Profile`）、`Effekseer.exe` のバージョン判定、`ToolVersion` と自動変換のルール（`MIGRATIONS`） |
| `tools/effect/enums.py` | 系列ごとの設定値の範囲の表と、その検査 |
| `tools/effect/presets.py` | ノードや値を組み立てる関数（`.efkproj` の実物のサンプルから作ったもの） |
| `tools/effect/model.py` | `.efkproj` の XML を表す汎用の木（`Elem`） |
| `tools/effect/xmlio.py` | `.efkproj` の読み書き（Effekseer と同じ書式で、読んで書き戻すとバイト単位で一致します） |
| `tools/effect/efkefc.py` | `.efkefc` の読み取り（`INFO`＝参照ファイル一覧、`EDIT`＝エディタ用データ、`BIN_`＝ランタイム用データ） |
| `tools/effect/assets.py` | テクスチャ・モデル・サウンドの参照の検査 |
| `tools/effect/meta.py` | NanamiEngine 用の `.meta` の作成 |
| `tools/effect/export.py` | 配布用ファイルのコピー（下記） |
| `tools/effect/selftest.py` | セルフテスト |
| `tools/effect/testdata/` | テストに使う実物の `.efkproj` |
| `tools/common/` | 開発元のプロジェクトの他のツールと共有しているモジュール（`.meta` の書式など） |

### .efkefc の中身

`.efkefc` は `EFKE` のヘッダーの後に、4 文字の名前とサイズを持つチャンクが並んだファイルです（Effekseer の `IO/EfkEfc.cs`）。

| チャンク | 内容 |
|---|---|
| `INFO` | バージョン番号と、参照するテクスチャ・モデル・サウンドなどの一覧（1610 以前は文字列のリスト、それより後は種類付きのリスト） |
| `EDIT` | エディタ用データ。コンパイル時に Effekseer が読み込んだ（変換後の）プロジェクトの XML を、zlib 圧縮したキー・値の表の形式で保存したもの |
| `BIN_` | ランタイムが読むデータ（`SKFE` ＋バージョン番号） |

`EDIT` は「そのバージョンの Effekseer が実際にどう読んだか」の正解データとして、テストと `upgrade` で使っています（`efkefc.edit_project`）。

## セルフテスト

```
python -m tools.effect selftest
```

| ステージ | 内容 | 必要なもの |
|---|---|---|
| 1 | `xmlio` の書式の再現（テストデータを読んで書き戻すと一致するか） | なし |
| 2 | `presets` で組み立てた木の読み書き | なし |
| 3・4 | NanamiEngine の `.meta` の書式 | NanamiEngine のアセット（無ければスキップ） |
| 5 | `Effekseer.exe` でのコンパイルと、出力のバージョン番号 | `effekseer.cui_paths` の `Effekseer.exe`（登録したものすべてで実行） |
| 6 | 設定値の範囲のチェック、コマンドの書き込み拒否、`install` | なし |
| 7 | サンプル集・既存の `.efkefc` での誤検出がないか | `selftest.corpus_dir` / NanamiEngine のアセット（無ければスキップ） |
| 8 | 設定ファイルの読み込み、`export` | なし |
| 9 | テクスチャ参照の検査、`install` のコピー | なし |
| 10 | バージョン番号の解釈、変換のルール、`Effekseer.exe` の決定、`.efkefc` の読み取り | なし |
| 11 | 変換のルールの完全性、1.80 の書き方、`upgrade` の往復（`EDIT` チャンクとの照合） | `effekseer.cui_paths` の `Effekseer.exe`（登録したものすべてで実行） |

ステージ 5・11 は、`Effekseer.exe` 1 つにつき数十秒〜1 分ほどかかります。
**`Effekseer.exe` は同時に複数動かさないでください**（まれに何も出力せずに失敗します）。

## バージョン対応の仕組みと確かめ方

### 設定値の範囲（enums.py）

Effekseer のエディタは、列挙型の設定のコンボボックスに、その列挙型の**すべての値**を並べます（`GUI/BindableComponent/Enum.cs`）。
選択肢にない値が入っていると、その欄を表示した瞬間にクラッシュします。

表は、各リリースの `EffekseerCore.dll` を .NET のリフレクションで読み、`Effekseer.Data.Node` からたどれるすべての `Value.Enum<T>` の値を列挙して照合しました
（1.5〜1.7 系は .NET Framework なので PowerShell、1.80 系は .NET 9 なので小さな C# のプログラムで読みました）。
同じ系列のリリースはすべて同じ結果で、表と一致しています。

表の各項目は「ノードからのタグのパスの末尾」で指定し、一番長く一致したものが使われます（`enums.py` の先頭のコメント）。

### ToolVersion と自動変換（versions.MIGRATIONS）

Effekseer の読み込み処理（`Core.LoadFromXml` と `Utils/ProjectVersionUpdater.cs`）は、ファイルの `ToolVersion` がしきい値より古いときだけ、古い書き方を新しい書き方に変換します。
`MIGRATIONS` は、このツールが書く項目に関係する変換を、しきい値・古い書き方・新しい書き方の組で持っています。

ステージ 11 は、`_migration_trees()` の各木を、`0.7CTP1` と各しきい値の `ToolVersion` でコンパイルし、`EDIT` チャンクを比べます。
**違いが出た（設定が消えた）のに `MIGRATIONS` が検出しない**、または**違いが出ないのに検出する**とテストが失敗します。
新しい書き方の項目を追加したら、`_migration_trees()` にも木を追加してください。

### バージョン判定

`Effekseer.exe` のファイルのバージョン情報は `1.0.0.0` なので使えません。
`EffekseerCore.dll` の UTF-16 文字列には、エディタ自身のバージョン（`Core.Version`）と、変換のしきい値（`1.60α9` など、必ず自身より古い）が入っているので、
`Core.ParseVersion` で一番新しいものを選んでいます（`versions.detect_cui_version`）。

## 機能を追加するとき

### 新しい Effekseer のバージョンに対応する

1. そのバージョンの Windows 版ツールを用意して、`effekseer.cui_paths` に登録します。
2. 新しい系列なら `versions.py` に `Profile`（系列名とバイナリのバージョン番号）を追加し、`_family` と `profile_for` を更新します。
3. `EffekseerCore.dll` から列挙型の値を読み出し、`enums.py` に表を追加します（前の系列との差分で書くと読みやすくなります）。
4. Effekseer のソースの `Core.cs`・`ProjectVersionUpdater.cs` で、新しい変換が増えていないか確認し、このツールが書く項目に関係するものを `MIGRATIONS` に追加します。
5. `selftest` を、そのバージョンと既存のバージョンの両方で通します。

### ノードの種類や設定の組み立てを追加する

- `presets.py` の関数は、**実物の `.efkproj`（エディタで作られたサンプル）で実際に使われている形**から作ってください。推測で作ると、Effekseer に黙って無視される形になりがちです。
- タグ名は大文字・小文字を区別します。
- 追加したら、ステージ 2 に読み書きのテストを、ステージ 11 の `_migration_trees()` に木を追加し、`Effekseer.exe` を登録した状態で `selftest` を通してください。
- コマンドのオプションを追加するときは `cli.py` の `register` と、書き込み前のチェック（`_reject_write_problems`）を通る経路にしてください。

## このリポジトリの更新方法

このリポジトリは、開発元のプロジェクト（NanamiEngine）の `tools/effect/` を正本として、`export` コマンドで配布用のファイルをコピーして更新しています。

```
python -m tools.effect export --out <このリポジトリの clone>
```

`export` は `tools/effect/export.py` の `MANIFEST` に書かれたファイルだけをコピーし、設定ファイルは個人のパスを含まない配布用のものに差し替えます。

不具合の報告や改善の提案は [Issues](https://github.com/ramasuke/EffekseerEfkprojTool/issues) にお願いします。
Pull Request を送っていただいた場合は、内容を開発元に取り込んでから、このリポジトリに反映します。
