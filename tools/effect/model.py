"""Generic order-preserving element tree for Effekseer's ``.efkproj`` format.

Effekseer's ``.efkproj`` serializes its editor object graph directly as nested
XML elements: no attributes anywhere, every element is either a text leaf
(``<X>1.8</X>``) or a pure container of child elements (``<Ring>...</Ring>``),
never both. An empty container and an empty-text leaf are the same thing on
disk (``<Children />``), so this model does not distinguish them either.

This intentionally does **not** model the full Effekseer schema - hundreds of
fields across dozens of node kinds, most only sparsely present in any given
file. See ``tools/effect/presets.py`` for the curated, sample-derived builder
functions that sit on top of this generic tree.

``Elem.text`` always holds the *literal* string content exactly as parsed -
never re-derived from a typed value - so a file read with :mod:`xmlio` and
written back out round-trips byte-for-byte. Formatting a fresh Python value
(``int``/``float``/``bool``) into element text is :mod:`presets`'s job, not
this module's.
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
        """Resolve a dotted tag path, e.g. ``"DrawingValues.Ring.CenterRatio_Fixed"``."""
        node = self
        for part in path.split("."):
            node = node.child(part)
            if node is None:
                return None
        return node

    def set_path(self, path: str, text: str) -> "Elem":
        """Set a leaf's text at a dotted tag path, creating intermediate elements
        as needed. Overwrites any existing children at the leaf (it becomes a
        pure text leaf).
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
