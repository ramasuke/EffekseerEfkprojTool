"""tools.common - tools.bt と tools.scene が共有する形式非依存のプリミティブ。

標準ライブラリのみ。バイト単位で正確な cereal-JSON コーデック、モデル化されていない
cereal サブツリーを無損失でラウンドトリップするためのタグ付き blob 表現、構造差分
ヘルパー、EnviroHunter.vcxproj のテキスト差し込みエディタ、汎用の ".meta"
サイドカーコーデック。BehaviourTree の action や Scene/GameObject/Component の
形については何も知らない - それらは利用側のパッケージにある。
"""

__version__ = "0.1.0"
