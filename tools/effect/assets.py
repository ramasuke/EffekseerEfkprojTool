"""エフェクト内のアセット参照 (テクスチャ、モデル、マテリアル、サウンド)。

Effekseer はこうした参照をすべて *それを持つファイルからの相対パス* で保存する:
原本では ``.efkproj`` からの相対、コンパイル済み ``.efkefc`` では出力ファイルからの
相対 (CUI / エディタが書き出し時に書き換える)。壊れ方は 3 通りあり、どれも
ツールキットが防いでいる:

1. ``.efkproj`` と別のディレクトリにコンパイル/書き出しすると、``.efkefc`` の
   フォルダの外を指すパスが残る (``../OneDrive/...``)。
2. パスを書き換えずに ``.efkproj`` を別の場所へコピーする。
3. サンプルプロジェクトに作者のローカルパスが残ったままになっている。

CUI はどれもエラー無しでコンパイルしてしまうので、``compile`` / ``install`` が
事前にチェックする。
"""

from __future__ import annotations

import os
from pathlib import Path, PurePosixPath

from .model import Elem

ASSET_EXTS = ("png", "jpg", "jpeg", "bmp", "tga", "dds", "efkmodel", "efkmat", "efkcurve", "wav")

_NOT_ASSET_TAGS = {"Name"}


def is_asset_path(text: str | None) -> bool:
    return bool(text) and text.strip().lower().endswith(tuple("." + e for e in ASSET_EXTS))


def project_asset_elems(proj: Elem) -> list[Elem]:
    """``.efkproj`` ツリー内で、テキストがアセットパスになっている全リーフ。"""
    found: list[Elem] = []

    def walk(e: Elem) -> None:
        if e.children:
            for c in e.children:
                walk(c)
        elif e.tag not in _NOT_ASSET_TAGS and is_asset_path(e.text):
            found.append(e)

    walk(proj)
    return found


def missing_project_assets(proj: Elem, proj_dir: Path) -> list[str]:
    """``proj_dir`` から解決できないアセットパス (重複除去、ファイル内の順)。"""
    missing: list[str] = []
    for e in project_asset_elems(proj):
        if e.text not in missing and not (Path(proj_dir) / e.text).is_file():
            missing.append(e.text)
    return missing


def escapes(rel: str) -> bool:
    """絶対パス、または基準フォルダの外に出るパス (``../x``) なら True。"""
    p = rel.replace("\\", "/")
    if PurePosixPath(p).is_absolute() or (len(p) > 1 and p[1] == ":"):
        return True
    return os.path.normpath(p).replace("\\", "/").split("/")[0] == ".."


def relpath_posix(target: Path, start: Path) -> str:
    return os.path.relpath(Path(target).resolve(), Path(start).resolve()).replace("\\", "/")


def describe_missing(paths: list[str]) -> str:
    lines = []
    for rel in paths:
        hint = ("  (points outside the folder - likely a path left over from another PC, e.g. "
                "a sample pack author's; put the file near the .efkproj and fix the path)"
                if escapes(rel) else "")
        lines.append(f"  - {rel}{hint}")
    return "\n".join(lines)
