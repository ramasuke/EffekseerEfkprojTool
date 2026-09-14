"""``effect_config.json`` - every machine- or project-specific value the
toolkit needs (Effekseer CUI location, install destination, ``.meta`` output),
kept out of the code so the toolkit can be copied into another project and
adapted by editing that one file. See ``SETUP.md`` for the key reference.

Relative paths: ``project.root`` is relative to the config file's directory
(empty = the folder that contains ``tools/``); ``effekseer.cui_path``,
``project.effect_dir`` and ``selftest.corpus_dir`` are relative to the project
root. An empty string means "not set".
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

CONFIG_PATH = Path(__file__).with_name("effect_config.json")

_DEFAULTS = {
    "effekseer": {"cui_path": "", "verified_version": "1.7.3.0"},
    "project": {"root": "", "effect_dir": "Effects", "source_subdir": "_Source"},
    "meta": {"enabled": False, "asset_type": "NanamiEngine::Module::Asset::ParticleFile"},
    "selftest": {"corpus_dir": ""},
}


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class EffectConfig:
    config_path: Path
    cui_path: Path | None
    verified_version: str
    project_root: Path
    effect_dir: Path
    effect_dir_rel: str
    source_subdir: str
    meta_enabled: bool
    meta_asset_type: str
    corpus_dir: Path | None


def _fail(path: Path, msg: str) -> ConfigError:
    return ConfigError(f"{path}: {msg} (see tools/effect/SETUP.md)")


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
    effect_dir_rel = _value(raw, path, "project", "effect_dir", str) or _DEFAULTS["project"]["effect_dir"]
    corpus_spec = _value(raw, path, "selftest", "corpus_dir", str)
    return EffectConfig(
        config_path=path.resolve(),
        cui_path=_under(project_root, cui_spec) if cui_spec else None,
        verified_version=_value(raw, path, "effekseer", "verified_version", str),
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
    """Temporarily make ``get()`` return ``cfg`` (selftest only)."""
    global _active
    saved = _active
    _active = cfg
    try:
        yield cfg
    finally:
        _active = saved
