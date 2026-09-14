# よくあるエラーと対処

エラーメッセージは英語で表示されます。メッセージの一部で検索してください。

- [環境・設定](#環境設定)
- [Effekseer のバージョン](#effekseer-のバージョン)
- [設定値・ファイルの形式](#設定値ファイルの形式)
- [テクスチャ・モデルの参照](#テクスチャモデルの参照)
- [コンパイル・配置](#コンパイル配置)
- [エフェクトの見た目・読み込み](#エフェクトの見た目読み込み)

## 環境・設定

| エラー | 原因と対処 |
|---|---|
| `Python was not found` / `'python' は、内部コマンドまたは外部コマンド...` / Microsoft Store が開く | Python がインストールされていないか、PATH が通っていません。[setup.md の「Python のインストール」](setup.md#python-のインストール)を見てください |
| `tools.effect には Python 3.10 以上が必要です` | Python が古いです。新しい Python をインストールしてください |
| `No module named tools.effect` | `tools/` があるフォルダ以外でコマンドを実行しています。`tools/` があるフォルダに移動してから実行してください |
| `config file not found` | `tools/effect/effect_config.json` がありません。リポジトリから取り直してください |
| `invalid JSON at line N column M` | 設定ファイルの JSON が壊れています。多いのは、パスの `\` を 1 つで書いているケースです。`/` で区切ってください |
| `"meta.enabled" must be a bool` など | 設定ファイルの値の型が違います（`true`/`false` を `"yes"` と書いた、など） |
| `Effekseer <バージョン> CUI (Tool/Effekseer.exe) not found` | `effekseer.cui_paths` にそのバージョンの `Effekseer.exe` が無いか、パスが間違っています。`check-env` で試したパスを確認してください |

## Effekseer のバージョン

| エラー | 原因と対処 |
|---|---|
| `unsupported Effekseer version` | 指定したバージョンが 1.50RC1〜1.80.7 の範囲外です（`effekseer.version`、`effekseer.cui_paths` のキー、`--effekseer-version`、`EFFEKSEER_VERSION` を確認してください） |
| `the Effekseer CUI ... is Effekseer X, but the target version is Y` | 使おうとした `Effekseer.exe` のバージョンが、使うバージョンと違う系列です。`effekseer.cui_paths` の対応を直すか、使うバージョンを変えてください |
| `unknown Effekseer runtime version` | `project.runtime_version` は `1.5`・`1.6`・`1.7`・`1.80` のどれかにしてください |
| `ToolVersion '...' is newer than Effekseer ...` | ファイルが、使う `Effekseer.exe` より新しいエディタの形式です（`upgrade` したファイルなど）。新しいバージョンの `Effekseer.exe` を使ってください。Effekseer はこの場合エラーを出さずに何も出力しないので、ツールが先に止めています |
| `OK, but the CUI's version could not be detected` | `Effekseer.exe` と同じフォルダ（または `bin` フォルダ）に `EffekseerCore.dll` がありません。Effekseer の zip を展開したフォルダ構成のまま使ってください |

## 設定値・ファイルの形式

| エラー | 原因と対処 |
|---|---|
| `... is not a valid Effekseer X value (allowed: [...]); the Effekseer editor crashes on it` | その値は、選んだ系列の Effekseer に存在しません（エディタで開くとクラッシュします）。`allowed` の中の値にするか、その値がある新しいバージョンを使ってください |
| `... is not a valid Effekseer easing speed` | フェード・イージングの速さは `-30,-20,-10,0,10,20,30` のどれかだけです |
| `... is ignored in a file with ToolVersion ...` | 古い書き方の設定を、`ToolVersion` が新しいファイル（`upgrade` したファイルなど）に書こうとしました。Effekseer はその値を無視します。新しい書き方の項目名を `--set` で指定してください（[versions.md](versions.md#5-ファイルの-toolversion-と自動変換)） |
| `... is overwritten in a file with ToolVersion ...` | 新しい書き方の設定を、`ToolVersion` が古いファイル（`new-project` で作ったファイル）に書こうとしました。読み込み時の変換で上書きされます。古い書き方（`add-node` のオプション）を使うか、先に `upgrade` してください |
| `generation_timing/trigger/trigger_count only exist in Effekseer 1.80's CommonValues layout` | 「トリガーで発生」は 1.80 の形式のファイルでだけ使えます。`upgrade --effekseer-version 1.80.7` で変換してから実行してください |
| `WARNING: ... only exists in Effekseer X+; Effekseer Y ignores it` | 選んだバージョンに存在しない項目です（エラーではありません）。そのバージョンのエディタでは無視されます |
| `no node at index N in path ...` | ノード番号が存在しません。`show` で番号を確認してください。ノードを追加・削除すると番号が変わります |
| `is in the compiled .efkefc format, not an XML .efkproj` | Effekseer のエディタで保存したファイルは `.efkefc` 形式になり、このツールでは編集できません |
| `unsupported DrawingValues type=N` | このツールが扱っていない種類のノードです。コンパイルはできますが、このツールでは専用のオプションで編集できません |

## テクスチャ・モデルの参照

| エラー | 原因と対処 |
|---|---|
| `references N texture/model/sound file(s) that don't exist` | `.efkproj` が存在しないファイルを指しています（名前の打ち間違い、ファイルの置き忘れなど）。`.efkproj` から見て書かれている場所にファイルを置くか、パスを直してください。`../` から始まるパスは、サンプル素材の作者の PC のパスが残っていることが多いです |
| `--out must be in the same folder as ...` | `compile` / `upgrade` の出力先は `.efkproj` と同じフォルダにしてください。Effekseer は出力先を基準にテクスチャのパスを保存するので、別のフォルダに出すとパスがずれます。配置は `install --dest` で行います |
| `references file(s) outside its own folder` | その `.efkefc` は、`.efkproj` と別のフォルダに書き出されていて、テクスチャのパスがフォルダの外を指しています。`.efkproj` と同じフォルダでコンパイルし直してください |
| `found neither next to it nor next to --dest` | インストールしようとした `.efkefc` が使うテクスチャが、`.efkefc` の隣にも配置先にもありません |
| `a different file with the same name is already installed` | 配置先に、同じ名前で中身の違うテクスチャがあります（他のエフェクトが使っているかもしれないので上書きしません）。自分のエフェクトのテクスチャの名前を変えてください |

## コンパイル・配置

| エラー | 原因と対処 |
|---|---|
| `CUI exited 1 with no output` | `Effekseer.exe` を同時に複数動かしていると、まれに何も出力せずに失敗します。他の Effekseer（エディタや別のコンパイル）を終了してから、もう一度実行してください |
| `CUI exited 0 but ... was not created` | Effekseer がファイルを読み込めませんでした。表示された Effekseer の出力を確認してください。`validate` で問題が見つかることもあります |
| `has binary version N, but Effekseer X writes M` | 実行された `Effekseer.exe` が、設定したバージョンと違います。`check-env` で確認してください |
| `has binary version N ... project.runtime_version is ...` | そのエフェクトは、設定したランタイムより新しいバージョンでコンパイルされています。ランタイムと同じ系列の Effekseer でコンパイルし直してください |

## エフェクトの見た目・読み込み

| 症状 | 原因と対処 |
|---|---|
| ゲームでエフェクトが読み込めない・表示されない | ゲームの Effekseer ランタイムより新しいバージョンでコンパイルしている可能性があります（[versions.md](versions.md#4-ゲームのランタイムとの互換性)）。`project.runtime_version` を設定すると `install` で気づけます |
| テクスチャが表示されない | `.efkefc` だけを別の場所にコピーしていないか確認してください。配置は `install` で行うと、テクスチャも一緒にコピーされます |
| 何も描画しないはずのノードに白い四角が表示される | Effekseer では、描画の種類を指定していないノードはスプライトになります。以前のバージョンのこのツールで作った `group` ノードがこの状態です。`set-params --path <番号> --set DrawingValues.Type=0` で直せます |
| Effekseer のエディタで開くとクラッシュする | 選択肢にない値が入っている可能性があります。`validate` で確認してください（他のツールで作ったファイルでも検査できます） |
| 設定したはずの色・重力などが反映されない | ファイルの `ToolVersion` に合わない書き方をしている可能性があります。`validate` で確認してください |

解決しない場合は、[Issues](https://github.com/ramasuke/EffekseerEfkprojTool/issues) に、Effekseer のバージョン、実行したコマンド、エラーの全文、`check-env` の出力を書いてください。
