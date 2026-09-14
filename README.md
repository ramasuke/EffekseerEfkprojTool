# EffekseerEfkprojTool

[Effekseer](https://effekseer.github.io/) のパーティクルエフェクトを、**GUI エディタを開かずに Python のコマンドで作る**ためのツールです。
エフェクトのソース（`.efkproj`）の作成・編集から、Effekseer 本体を使った `.efkefc` へのコンパイル、ゲームのプロジェクトへの配置までを
コマンドだけで行えます。Python の標準ライブラリだけで動くので、`pip install` は要りません。

```
python -m tools.effect new-project Spark --dir work
python -m tools.effect add-node work/Spark.efkproj --kind ring   --name Burst --life 20 --color 255:200:120:255
python -m tools.effect add-node work/Spark.efkproj --kind sprite --name Glow  --color-texture Texture/Particle01.png
python -m tools.effect compile  work/Spark.efkproj
```

## できること

- **コマンドでエフェクトを作る** — リング・スプライト・リボン・モデル・トラックのノードを追加し、寿命・色・テクスチャ・発生位置・フェードなどを設定できます。
  まとめて編集する JSON（`apply`）や Python の関数（`presets`）も使えるので、スクリプトや AI エージェントから扱いやすくなっています。
- **Effekseer 1.50RC1 〜 1.80.7 の全リリースに対応** — 設定ファイルで使うバージョンを選ぶと、そのバージョンの `Effekseer.exe` でコンパイルします。
  複数のバージョンを並べて登録しておけます。
- **壊れたエフェクトを作らせない** — Effekseer はコンパイル時に何も言わないのに、あとで問題になる書き方を事前に止めます。
  - エディタで開くと**クラッシュする値**（選んだバージョンに存在しない設定値など）
  - 読み込み時に Effekseer に**黙って捨てられる設定**（ファイルの形式に合っていない書き方）
  - **見つからないテクスチャ・モデル・サウンド**、別のフォルダに書き出して**パスがずれた**エフェクト
  - ゲーム側の Effekseer ランタイムより**新しいバージョンでコンパイルした**エフェクト（ランタイムで読み込めません）
- **プロジェクトへの配置** — コンパイルした `.efkefc` を、使っているテクスチャ・モデルと一緒に指定のフォルダへコピーします。

## 対応している Effekseer

| 系列 | リリース |
|---|---|
| 1.5 系 | 1.50RC1、1.50RC2、1.51 |
| 1.6 系 | 1.60、1.60b〜1.60e、1.61a〜1.61e、1.62、1.62a〜1.62e |
| 1.7 系 | 1.70、1.70a、1.70b、1.70e、1.7.3.0 |
| 1.80 系 | 1.80.0（RC1〜RC3）、1.80.1〜1.80.7 |

Windows 版のツールが公開されているこの 33 リリースは、すべて実際にダウンロードしてテストしています。
ベータ版、1.43 以前、1.80.7 より新しいバージョンには対応していません。詳しくは [docs/versions.md](docs/versions.md) を見てください。

> [!WARNING]
> **新しいバージョンの Effekseer でコンパイルしたエフェクトは、古いランタイムでは読み込めません**（例: 1.80 でコンパイル → ゲームが 1.7 のランタイム）。
> 設定ファイルの `effekseer.version` は、**ゲームで使っている Effekseer ランタイムと同じ系列**にしてください。

> [!IMPORTANT]
> **ブラウザで使う AI（Claude・ChatGPT・Gemini など）では、このツールは使えません。**
> このツールは自分の PC で Python と `Effekseer.exe` を実行し、PC 上のファイルを読み書きするためです。
> PC にインストールしてコマンドを実行できる版の AI エージェントなら使えます。

## 必要なもの

- **Python 3.10 以上**（入っていない場合のインストール手順は [docs/setup.md](docs/setup.md#python-のインストール)）
- **Windows**（動作確認は Windows 11。`compile` と `upgrade` は Effekseer の `Effekseer.exe` を実行するので Windows が必要です）
- **Effekseer 本体**（このリポジトリには含まれていません。[Effekseer のリリースページ](https://github.com/effekseer/Effekseer/releases)から Windows 版をダウンロードしてください）

## クイックスタート

1. このリポジトリを clone します。

   ```
   git clone https://github.com/ramasuke/EffekseerEfkprojTool.git
   cd EffekseerEfkprojTool
   ```

2. `tools/effect/effect_config.json` に、使う Effekseer のバージョンと `Effekseer.exe` の場所を書きます。

   ```json
   "effekseer": {
       "version": "1.80.7",
       "cui_paths": {
           "1.80.7": "D:/Effekseer1.80.7Win/Tool/Effekseer.exe"
       }
   },
   ```

   Windows のパスは `/` で区切ってください（`\` を 1 つで書くと JSON のエラーになります）。

3. 設定を確認して、セルフテストを実行します。どちらも `tools/` があるフォルダで実行します。

   ```
   python -m tools.effect check-env
   python -m tools.effect selftest
   ```

   `check-env` の最後が `OK.`、`selftest` の最後が `N/N checks passed` になれば準備完了です。

4. エフェクトを作ってコンパイルします。

   ```
   python -m tools.effect new-project Spark --dir work
   python -m tools.effect add-node work/Spark.efkproj --kind ring --name Burst --life 20 --color 255:200:120:255
   python -m tools.effect add-node work/Spark.efkproj --kind sprite --name Glow --max-generation 30 --generation-shape sphere --radius 0:0.5:1 --fade-out 10
   python -m tools.effect show work/Spark.efkproj
   python -m tools.effect compile work/Spark.efkproj
   ```

   `work/Spark.efkefc` ができます。Effekseer のエディタで開いて見た目を確認できます。

## ドキュメント

| ドキュメント | 内容 |
|---|---|
| [docs/setup.md](docs/setup.md) | インストール、Effekseer の用意、設定ファイルの全項目、自分のプロジェクトへの組み込み |
| [docs/usage.md](docs/usage.md) | 基本の考え方、全コマンドとオプション、JSON でのまとめて編集、Python からの使い方、できないこと |
| [docs/versions.md](docs/versions.md) | Effekseer のバージョン対応の詳細、ランタイムとの互換性、ファイル形式と `upgrade` |
| [docs/troubleshooting.md](docs/troubleshooting.md) | よくあるエラーと対処 |
| [docs/development.md](docs/development.md) | ツールの構成、セルフテスト、検証の方法（開発・改造する人向け） |

## 質問・不具合報告

[Issues](https://github.com/ramasuke/EffekseerEfkprojTool/issues) に書いてください（NiceBody が対応します）。
不具合のときは、使っている Effekseer のバージョン、実行したコマンド、表示されたエラーをそのまま貼ってください。
`python -m tools.effect check-env` の出力もあると助かります。

## ライセンス

[MIT](LICENSE)

---

## English

**EffekseerEfkprojTool** builds [Effekseer](https://effekseer.github.io/) particle effects from the command line
(or Python) instead of the GUI editor: create and edit `.efkproj` sources, compile them to `.efkefc` with
Effekseer's own `Effekseer.exe`, and install the result with its textures. Python 3.10+ standard library only.

- Supports every Effekseer release with a Windows tool from **1.50RC1 to 1.80.7** (all 33 tested). Pick the
  target in `tools/effect/effect_config.json` (`effekseer.version` + `effekseer.cui_paths`).
- Refuses, before anything is written or compiled, values that crash the target editor, fields Effekseer would
  silently drop for the file's `ToolVersion`, missing or misplaced textures/models, and effects too new for your
  runtime (`project.runtime_version`).
- Quick start: `python -m tools.effect check-env`, `python -m tools.effect selftest`, then
  `new-project` → `add-node` → `compile`. `python -m tools.effect <command> --help` lists every option.

The detailed documentation under [`docs/`](docs/) is in Japanese.
