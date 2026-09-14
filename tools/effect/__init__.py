"""tools.effect - author Effekseer .efkproj particle-effect sources without
hand-editing raw XML, compile them via the Effekseer CUI, and install the
result as a NanamiEngine ParticleFile asset.

See tools/effect/README.md for the command reference.
"""

import sys

# Every entry point (python -m tools.effect, tools/effect.py, selftest.py)
# imports this package first, so the check lives only here.
MIN_PYTHON = (3, 10)

if sys.version_info < MIN_PYTHON:
    sys.exit(
        "tools.effect には Python %d.%d 以上が必要です（今の Python: %d.%d）。\n"
        "https://www.python.org/downloads/ から新しい Python をインストールしてください"
        "（手順は tools/effect/SETUP.md の「Python のインストール」）。\n"
        "tools.effect requires Python %d.%d or newer (running %d.%d)."
        % (MIN_PYTHON + sys.version_info[:2] + MIN_PYTHON + sys.version_info[:2])
    )
