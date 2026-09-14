"""tools.common - format-generic primitives shared by tools.bt and tools.scene.

Stdlib-only. Byte-exact cereal-JSON codec, the tagged-blob representation for
losslessly round-tripping unmodeled cereal sub-trees, structural diff helpers,
the NanamiEngine.vcxproj text-splice editor, and the generic ".meta" sidecar
codec. Nothing here knows about BehaviourTree actions or Scene/GameObject/
Component shapes - those live in the consuming packages.
"""

__version__ = "0.1.0"
