"""``effect_config.json`` - ツールキットが必要とするマシン固有・プロジェクト固有の
値 (Effekseer CUI の場所、インストール先、``.meta`` 出力) をすべて持つ。
コードから切り離してあるので、ツールキットを別プロジェクトにコピーしても
このファイル 1 つを編集すれば合わせられる。キーの説明は ``docs/setup.md``
(ここでは ``tools/effect/dist/docs/setup.md``) を参照。

相対パス: ``project.root`` は設定ファイルのディレクトリからの相対
(空 = ``tools/`` を含むフォルダ)。``effekseer.cui_paths`` /
``effekseer.cui_path``、``project.effect_dir``、``selftest.corpus_dir`` は
プロジェクトルートからの相対。空文字列は「未設定」を表す。

``effekseer.version`` はツールキットが対象とする Effekseer のバージョンで、
``effekseer.cui_paths`` はバージョンからその ``Effekseer.exe`` への対応表
(探索順は ``cli.resolve_effekseer`` 参照)。旧来の単一の
``effekseer.cui_path`` と ``effekseer.verified_version`` キーも引き続き使える。
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from . import versions

CONFIG_PATH = Path(__file__).with_name("effect_config.json")

_DEFAULTS = {
    "effekseer": {"version": "", "cui_paths": {}, "cui_path": "", "verified_version": ""},
    "project": {"root": "", "effect_dir": "Effects", "source_subdir": "_Source", "runtime_version": ""},
    "meta": {"enabled": False, "asset_type": "NanamiEngine::Module::Asset::ParticleFile"},
    "selftest": {"corpus_dir": ""},
}


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class EffectConfig:
    config_path: Path
    version: str
    cui_paths: dict[str, Path]
    cui_path: Path | None
    runtime_version: str
    project_root: Path
    effect_dir: Path
    effect_dir_rel: str
    source_subdir: str
    meta_enabled: bool
    meta_asset_type: str
    corpus_dir: Path | None


def _fail(path: Path, msg: str) -> ConfigError:
    return ConfigError(f"{path}: {msg} (see docs/setup.md)")


def _value(raw: dict, path: Path, section: str, key: str, typ: type):
    sec = raw.get(section, {})
    if not isinstance(sec, dict):
        raise _fail(path, f'"{section}" must be an object')
    value = sec.get(key, _DEFAULTS[section][key])
    if not isinstance(value, typ):
        raise _fail(path, f'"{section}.{key}" must be a {typ.__name__}, got {value!r}')
    return value


def _under(base: Path, spec: str) -> Path:
    p = Path(spec)
    return (p if p.is_absolute() else base / p).resolve()


def load(path: Path) -> EffectConfig:
    path = Path(path)
    if not path.is_file():
        raise _fail(path, "config file not found")
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as e:
        raise _fail(path, f"invalid JSON at line {e.lineno} column {e.colno}: {e.msg}. "
                          'Write Windows paths with "/" or "\\\\", not a single "\\"') from e
    if not isinstance(raw, dict):
        raise _fail(path, "top level must be a JSON object")

    root_spec = _value(raw, path, "project", "root", str)
    project_root = _under(path.parent, root_spec) if root_spec else path.resolve().parents[2]

    cui_spec = _value(raw, path, "effekseer", "cui_path", str)
    cui_paths_spec = _value(raw, path, "effekseer", "cui_paths", dict)
    for key, value in cui_paths_spec.items():
        if not isinstance(value, str):
            raise _fail(path, f'"effekseer.cui_paths.{key}" must be a str, got {value!r}')
        try:
            versions.profile_for(key)
        except ValueError as e:
            raise _fail(path, f'"effekseer.cui_paths" key {key!r}: {e}') from e
    version = (_value(raw, path, "effekseer", "version", str)
               or _value(raw, path, "effekseer", "verified_version", str))
    if version:
        try:
            versions.profile_for(version)
        except ValueError as e:
            raise _fail(path, f'"effekseer.version": {e}') from e
    runtime_version = _value(raw, path, "project", "runtime_version", str)
    if runtime_version:
        try:
            versions.runtime_max_binary_version(runtime_version)
        except ValueError as e:
            raise _fail(path, f'"project.runtime_version": {e}') from e
    effect_dir_rel = _value(raw, path, "project", "effect_dir", str) or _DEFAULTS["project"]["effect_dir"]
    corpus_spec = _value(raw, path, "selftest", "corpus_dir", str)
    return EffectConfig(
        config_path=path.resolve(),
        version=version,
        cui_paths={k: _under(project_root, v) for k, v in cui_paths_spec.items() if v},
        cui_path=_under(project_root, cui_spec) if cui_spec else None,
        runtime_version=runtime_version,
        project_root=project_root,
        effect_dir=_under(project_root, effect_dir_rel),
        effect_dir_rel=effect_dir_rel.replace("\\", "/"),
        source_subdir=_value(raw, path, "project", "source_subdir", str) or _DEFAULTS["project"]["source_subdir"],
        meta_enabled=_value(raw, path, "meta", "enabled", bool),
        meta_asset_type=_value(raw, path, "meta", "asset_type", str),
        corpus_dir=_under(project_root, corpus_spec) if corpus_spec else None,
    )


_active: EffectConfig | None = None


def get() -> EffectConfig:
    global _active
    if _active is None:
        _active = load(CONFIG_PATH)
    return _active


@contextmanager
def override(cfg: EffectConfig):
    """一時的に ``get()`` が ``cfg`` を返すようにする (selftest 専用)。"""
    global _active
    saved = _active
    _active = cfg
    try:
        yield cfg
    finally:
        _active = saved
