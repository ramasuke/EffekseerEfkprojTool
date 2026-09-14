# EffekseerEfkprojTool

[Effekseer](https://effekseer.github.io/) のパーティクルエフェクトを、**GUI エディタを開かずに Python のコマンドで作る**ためのツールです。
エフェクトのソース（`.efkproj`）の作成・編集から、Effekseer 本体を使った `.efkefc` へのコンパイル、ゲームのプロジェクトへの配置までを
コマンドだけで行えます。

**AI エージェントに使わせることを前提に作っています。** 「赤い火花が飛び散るヒットエフェクトを作って」のように AI に頼むと、
AI がこのツールのコマンドでエフェクトを組み立ててコンパイルします。人は、できたエフェクトを Effekseer のエディタで見て、直してほしいところを伝えます。
Effekseer のエディタがクラッシュする値や、Effekseer に黙って無視される書き方は、ツールがエラーにして AI に直させます。

> [!IMPORTANT]
> **PC 上でコマンドを実行できる AI エージェントが必要です。ブラウザで使う AI（Claude・ChatGPT・Gemini など）では使えません。**
> このツールは自分の PC で Python と `Effekseer.exe` を実行し、PC 上のファイルを読み書きするためです。
> Claude・ChatGPT・Gemini のどれでも、PC にインストールしてコマンドを実行できる版なら使えます。

## クイックスタート

Windows で使います（動作確認は Windows 11）。

### 1. 準備する（人がやること）

1. **Python 3.10 以上をインストールします。**
   コマンドプロンプトか PowerShell で `python --version` を実行し、`Python 3.10.x` 以上（`3.13.x` など）が表示されればインストール済みです。
   入っていない（`Python was not found` などと表示される、Microsoft Store が開く）か 3.9 以下の場合は、
   https://www.python.org/downloads/ から最新の Python 3 のインストーラーをダウンロードし、
   最初の画面の下にある **「Add python.exe to PATH」にチェックを入れて**から「Install Now」を押してください
   （[詳しい手順](docs/setup.md#python-のインストール)）。
2. **Effekseer をダウンロードします。**
   [Effekseer のリリースページ](https://github.com/effekseer/Effekseer/releases)から、
   **ゲームで使っている Effekseer ランタイムと同じ系列**のバージョンの Windows 版ツール（`Effekseer1.80.7Win.zip` のような名前の zip）をダウンロードし、
   好きな場所に展開します。展開した場所は次の手順で AI に伝えるので、メモしておいてください。
3. **このツールをダウンロードします。** 次のどちらかです。
   - このツールだけで使う: `git clone https://github.com/ramasuke/EffekseerEfkprojTool.git`（git を使わない場合は、このページの「Code」→「Download ZIP」）
   - ゲームのプロジェクトで使う: ダウンロードした中の `tools/` フォルダを、プロジェクトの直下にコピー
4. **AI エージェントを起動します。** 手順 3 のフォルダ（`tools/` があるフォルダ）を作業フォルダにして起動してください。

### 2. AI にセットアップを頼む

次のように頼みます（`<>` の部分は自分の環境に書き換えてください）。

```
EffekseerEfkprojTool（tools/effect）を使えるようにしてください。
README.md と docs/setup.md を読んで、tools/effect/effect_config.json を設定し、
python -m tools.effect check-env と python -m tools.effect selftest が通るまで確認してください。

- Effekseer は <D:/Effekseer1.80.7Win> に展開してあります
- ゲームで使っている Effekseer ランタイムは <1.80> 系です
- エフェクトを配置するフォルダは <Assets/Effects> です（配置まで頼む場合）
```

ゲームのプロジェクトに `tools/` をコピーした場合は、`README.md` と `docs/` もそのプロジェクトに置くか、AI にこのリポジトリの場所を伝えてください。

### 3. AI にエフェクトを頼む

テクスチャ画像はこのツールに含まれていないので、使いたい画像（パーティクル用の PNG など）を用意して、場所を伝えてください。
Effekseer の zip の `Sample` フォルダにある画像も使えます（使うときは、それぞれのライセンスを確認してください）。

作りたいエフェクトを言葉で伝えます。

```
docs/usage.md を読んで、tools/effect を使ってエフェクトを作ってください。
.efkproj を直接書き換えず、コマンド（add-node・set-params・apply）で作り、validate と compile まで通してください。

作ってほしいもの: <敵に攻撃が当たったときの、赤とオレンジの火花が 0.5 秒くらいで飛び散るヒットエフェクト>
保存先: <work/HitSpark.efkproj>
テクスチャ: <work/Texture/Particle01.png を使ってよい>
```

AI がコンパイルまで終えたら、できた `.efkefc` を **Effekseer のエディタで開いて見た目を確認**し、直してほしいところをそのまま伝えます。

```
火花をもっと大きく、数を倍にして、消えるのを少しゆっくりにしてください。
```

仕上がったら、プロジェクトへの配置も頼めます。

```
work/HitSpark.efkefc を install で <Assets/Effects/HitSpark.efkefc> に配置してください。
```

コマンドを自分で実行したい場合は、[docs/usage.md](docs/usage.md) にすべてのコマンドと使い方があります。

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
