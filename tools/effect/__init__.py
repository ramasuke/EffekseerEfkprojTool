"""tools.effect - Effekseer の .efkproj パーティクルエフェクトの原本を生の XML を
手で編集せずに作成し、Effekseer CUI でコンパイルして、結果をテクスチャの隣に
(NanamiEngine では ParticleFile アセットとして) インストールする。

ユーザー向けドキュメント: README.md と docs/ (NanamiEngine では tools/effect/dist/)。
"""

import sys

# どのエントリポイント (python -m tools.effect, tools/effect.py, selftest.py) も
# 最初にこのパッケージを import するので、チェックはここだけに置く。
MIN_PYTHON = (3, 10)

if sys.version_info < MIN_PYTHON:
    sys.exit(
        "tools.effect には Python %d.%d 以上が必要です（今の Python: %d.%d）。\n"
        "https://www.python.org/downloads/ から新しい Python をインストールしてください"
        "（手順は docs/setup.md の「Python のインストール」）。\n"
        "tools.effect requires Python %d.%d or newer (running %d.%d)."
        % (MIN_PYTHON + sys.version_info[:2] + MIN_PYTHON + sys.version_info[:2])
    )
