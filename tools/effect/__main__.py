"""``python -m tools.effect <command>`` entry point."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


def _cmd_selftest(_args: argparse.Namespace) -> int:
    from tools.effect.config import ConfigError
    try:
        from tools.effect.selftest import main as selftest_main
        return selftest_main()
    except ConfigError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="tools.effect", description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("selftest", help="run the correctness gate")
    sp.set_defaults(func=_cmd_selftest)

    from tools.effect import cli
    cli.register(sub)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
