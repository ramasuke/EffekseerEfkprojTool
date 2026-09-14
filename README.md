# EffekseerEfkprojTool

Effekseer のパーティクルエフェクト（`.efkproj`）を、Effekseer の GUI エディタを開かずに
Python のコマンドで作成・編集し、Effekseer の CUI で `.efkefc` にコンパイルするツールです。
Python の標準ライブラリだけで動きます。

> [!WARNING]
> このツールは **Effekseer 1.7.3.0** で検証しています。これと違うバージョンの Effekseer を使っていると、
> 作成したエフェクトを**ロードするときにエラーが出る**可能性があります。
> その場合は **NiceBody に連絡してください**（[Issues](https://github.com/ramasuke/EffekseerEfkprojTool/issues)
> に、使っている Effekseer のバージョンとエラーの内容を書いてください）。そのバージョンに対応したツールを作れるか試します。

## クイックスタート

1. このリポジトリを clone します（自分のプロジェクトで使う場合は `tools/` フォルダをプロジェクト直下にコピーします）。
2. `tools/effect/effect_config.json` の `effekseer.cui_path` に、自分の PC の `Effekseer.exe` のパスを書きます。

   ```json
   "effekseer": {
       "cui_path": "D:/Effekseer1.7.3.0Win/Tool/Effekseer.exe",
       "verified_version": "1.7.3.0"
   },
   ```

3. `tools/` があるフォルダで、設定を確認してからセルフテストを実行します。

   ```
   python -m tools.effect check-env
   python -m tools.effect selftest
   ```

4. エフェクトを作ります。

   ```
   python -m tools.effect new-project Spark --dir work
   python -m tools.effect add-node work/Spark.efkproj --kind ring --name Burst
   python -m tools.effect add-node work/Spark.efkproj --kind sprite --name Glow
   python -m tools.effect show work/Spark.efkproj
   python -m tools.effect compile work/Spark.efkproj
   python -m tools.effect install work/Spark.efkefc --dest Effects/Spark.efkefc
   ```

## ドキュメント

- [`tools/effect/SETUP.md`](tools/effect/SETUP.md) — セットアップ、設定ファイルの全項目、よくあるエラー（日本語）
- [`tools/effect/README.md`](tools/effect/README.md) — コマンドの詳しい説明と既知の制限（英語）

## ライセンス

[MIT](LICENSE)
