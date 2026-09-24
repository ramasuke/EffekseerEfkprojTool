"""Effekseer の ``.efkproj`` 形式向けの、順序を保つ汎用要素ツリー。

Effekseer の ``.efkproj`` はエディタのオブジェクトグラフをそのまま入れ子の XML 要素
としてシリアライズする: 属性はどこにも無く、各要素はテキストのリーフ
(``<X>1.8</X>``) か子要素だけのコンテナ (``<Ring>...</Ring>``) のどちらかで、
両方ということは無い。空のコンテナと空テキストのリーフはディスク上で同じもの
(``<Children />``) なので、このモデルでも区別しない。

Effekseer の完全なスキーマは意図的にモデル化 **していない** - 数十のノード種別に
わたる数百のフィールドがあり、ほとんどはどのファイルにもまばらにしか現れない。
この汎用ツリーの上に載る、サンプル由来の厳選したビルダー関数は
``tools/effect/presets.py`` を参照。

``Elem.text`` は常に解析した文字列内容を *そのまま* 保持する - 型付きの値から
作り直すことは無い - ので、:mod:`xmlio` で読んだファイルを書き戻すとバイト単位で
一致する。新しい Python の値 (``int``/``float``/``bool``) を要素テキストに
整形するのは :mod:`presets` の仕事で、このモジュールの仕事ではない。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Elem:
    tag: str
    text: str | None = None
    children: list["Elem"] = field(default_factory=list)

    def is_container(self) -> bool:
        return bool(self.children)

    def child(self, tag: str) -> "Elem | None":
        return next((c for c in self.children if c.tag == tag), None)

    def all(self, tag: str) -> list["Elem"]:
        return [c for c in self.children if c.tag == tag]

    def require(self, tag: str) -> "Elem":
        c = self.child(tag)
        if c is None:
            raise KeyError(f"<{self.tag}> has no <{tag}> child")
        return c

    def child_or_add(self, tag: str) -> "Elem":
        c = self.child(tag)
        if c is None:
            c = Elem(tag)
            self.children.append(c)
        return c

    def add(self, elem: "Elem") -> "Elem":
        self.children.append(elem)
        return elem

    def get(self, path: str) -> "Elem | None":
        """ドット区切りのタグパスを解決する。例: ``"DrawingValues.Ring.CenterRatio_Fixed"``。"""
        node = self
        for part in path.split("."):
            node = node.child(part)
            if node is None:
                return None
        return node

    def set_path(self, path: str, text: str) -> "Elem":
        """ドット区切りのタグパスにあるリーフのテキストを設定し、途中の要素は必要に
        応じて作る。そのリーフに既存の子があれば上書きする (純粋なテキストリーフに
        なる)。
        """
        node = self
        parts = path.split(".")
        for part in parts[:-1]:
            node = node.child_or_add(part)
        leaf = node.child_or_add(parts[-1])
        leaf.text = text
        leaf.children = []
        return leaf

    def clone(self) -> "Elem":
        return Elem(self.tag, self.text, [c.clone() for c in self.children])
