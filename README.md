# EffekseerEfkprojTool

[Effekseer](https://effekseer.github.io/) のパーティクルエフェクトを、**AI エージェントにコマンドで作らせる**ためのツールです。

「赤い火花が飛び散るヒットエフェクトを作って」と頼むと、AI がエフェクトを組み立てて `.efkefc` にコンパイルします。
人は、できたエフェクトを Effekseer のエディタで見て、直してほしいところを伝えます。

> [!IMPORTANT]
> - **Windows** 専用です（動作確認は Windows 11）。
> - **PC 上でコマンドを実行できる AI エージェント**が必要です。ブラウザで使う AI（Claude・ChatGPT・Gemini など）では使えません。

## クイックスタート

**この手順だけでエフェクトを作れます。** `docs/` のドキュメントは、詳しく知りたくなったときに読めば十分です。

### 1. 準備する

1. **Python 3.10 以上**を入れる（`python --version` で確認。入っていなければ[インストール手順](docs/setup.md#python-のインストール)）
2. **このリポジトリ**を clone する（または「Code」→「Download ZIP」）

### 2. セットアップする

`tools/effect/effect_config.json` を開いて、**Effekseer のバージョン（`version`）と `Effekseer.exe` の場所（`cui_paths`）の 2 つだけ**を書きます。
ほかの項目は変更しなくても使えます。

```json
"effekseer": {
    "version": "1.80.7",
    "cui_paths": {
        "1.80.7": "D:/Effekseer1.80.7Win/Tool/Effekseer.exe"
    }
},
```

パスは `/` で区切ってください。

次の 2 つを実行して確認します。**先に `cd` でこのリポジトリのフォルダに移動してください**（`tools/` があるフォルダで実行しないと、`No module named tools.effect` のエラーになり確認できません）。

```
cd EffekseerEfkprojTool
python -m tools.effect check-env
python -m tools.effect selftest
```

`check-env` の最後が `OK.`、`selftest` の最後が `N/N checks passed` なら完了です。

### 3. AI にエフェクトを頼む

このリポジトリのフォルダで AI エージェントを起動して、作りたいエフェクトを伝えます。

```
docs/usage.md を読んで、赤い火花が飛び散るヒットエフェクトを
work/HitSpark.efkproj に作って、コンパイルまでして。
```

テクスチャは AI が用意して設定するので、気にしなくてかまいません（使いたい画像があれば、その場所を伝えてください）。

### 4. 見た目を確認して、直してもらう

できた `work/HitSpark.efkefc` を Effekseer のエディタで開いて確認し、直してほしいことを伝えます。

```
火花をもっと大きくして、数を倍にして。
```

あとは 3 と 4 を繰り返すだけです。必要になったら、次も見てください。

- ゲームのプロジェクトに組み込む方法は [docs/setup.md](docs/setup.md#7-自分のプロジェクトに組み込む)
- コマンドを自分で実行する方法は [docs/usage.md](docs/usage.md)

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
