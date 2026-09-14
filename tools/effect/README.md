# `tools/effect` — Effekseer `.efkproj` particle-effect toolkit

Stdlib-only Python 3. Lets you create new Effekseer particle effects
(`.efkproj` source), compile them to `.efkefc` via the Effekseer CUI, and
install the result as a `Assets/Art/Effect/**/*.efkefc` `ParticleFile` asset
— **without** hand-editing raw XML or opening the Effekseer GUI editor.

**Setting it up on another machine or in another project:** see
[`SETUP.md`](SETUP.md) (Japanese). Everything machine- or project-specific
(Effekseer CUI path, install destination, `.meta` output) lives in
`tools/effect/effect_config.json`. The toolkit is also published standalone at
https://github.com/ramasuke/EffekseerEfkprojTool (synced from here with `export`).

Run from the repo root:

```
python -m tools.effect <command>        # or: python tools/effect.py <command>
```

## Commands

| command | purpose |
|---|---|
| `selftest` | correctness gate — run after touching `model.py` / `xmlio.py` / `presets.py` / `enums.py` / `meta.py` |
| `new-project NAME` | create `NAME.efkproj` (empty project skeleton) |
| `show FILE` | print the node tree as an outline, with `[index.path]` addresses |
| `validate FILE` | structural sanity checks (well-formed XML, required top-level elements, known `DrawingValues` kinds, **Effekseer enum-domain check** — see below, and texture/model/sound paths that don't resolve relative to the file; `add-node`/`set-params`/`apply` warn about the latter) |
| `add-node` | add a `sprite` / `ring` / `ribbon` / `model` / `track` / `group` node under an existing node or the root |
| `set-params` | set fields on an existing node via dotted tag paths |
| `apply FILE OPS.json` | apply a batch of `add-node`/`set-params` ops atomically (primary agent interface) |
| `compile FILE` | compile `.efkproj` → `.efkefc` via the Effekseer CUI set in `effect_config.json`. **Refuses** (before running the CUI) when a referenced texture/model/sound doesn't exist relative to the `.efkproj`, or when `--out` is in another folder — the CUI itself compiles both without complaint |
| `install EFKEFC --dest ...` | copy a compiled `.efkefc` into `project.effect_dir` (`Assets/Art/Effect/` here) **together with every texture/model it references** (same relative paths next to `--dest`), mint a fresh-GUID `.meta` when `meta.enabled` (an existing `.meta` at `--dest` is kept as-is, GUID included, so re-installing never breaks prefab references), and (with `--project`) commit the source under `<effect_dir>/<source_subdir>/` (`Assets/Art/Effect/_Source/` here) with its asset paths **rewritten to point at the installed files**. Refuses, writing nothing, when a reference points outside the effect's folder (`../...` — exported into another folder than its `.efkproj`), can't be found, or would overwrite a different same-named file |
| `check-env` | print the resolved `effect_config.json` settings; exit 1 if the Effekseer CUI can't be found |
| `export --out DIR` | copy the distributable files (`export.MANIFEST`, with `dist/effect_config.json` swapped in) into DIR — how the public EffekseerEfkprojTool repository is updated |

Nodes have no stable id in the `.efkproj` format itself (unlike `tools/bt`'s
per-node GUIDs), so `--parent`/`--path` address a node by a dot-separated
0-based child-index path from the root, e.g. `"1.0"` = the root's 2nd child
node's 1st child node. `""` (or `"root"`) means the root itself. `show`
prints these paths next to each node.

### Typical flow

```
python -m tools.effect new-project Spark --dir <scratch dir>
python -m tools.effect add-node Spark.efkproj --kind ring --name Burst --set DrawingValues.Ring.CenterRatio_Fixed=0.85
python -m tools.effect add-node Spark.efkproj --kind sprite --name Glow
python -m tools.effect show Spark.efkproj
python -m tools.effect compile Spark.efkproj
python -m tools.effect install Spark.efkefc --project Spark.efkproj --dest Assets/Art/Effect/MyPack/Spark.efkefc
```

(The paths above are NanamiEngine's; elsewhere use your own
`project.effect_dir`.) In NanamiEngine, bind the printed GUID to a `ParticleFile`-typed field (see
`Assets/Art/Effect/Laser01.efkefc.meta` for the shape) the same way any other
asset GUID is wired into a prefab/component.

### `add-node`'s dedicated flags

Beyond `--kind`/`--name`/`--parent`, `add-node` has dedicated flags for the
fields most real effects touch (still backed by `--set dotted.path=value`
for anything not listed here):

| flag | maps to | applies to |
|---|---|---|
| `--life`, `--max-generation`, `--infinite` | `CommonValues` | any kind |
| `--color-texture`, `--fade-in`, `--fade-out`, `--uv-scroll` | `RendererCommonValues` (fade speeds: `-30,-20,-10,0,10,20,30` only, see below) | any kind |
| `--generation-shape circle\|sphere\|point` + `--radius`/`--division`/`--angle-start`/`--angle-end` | `GenerationLocationValues` | any kind |
| `--billboard` | `Sprite.Billboard` | `sprite` |
| `--color R:G:B[:A]` | fixed color (`ColorAll_Fixed` for sprite/ribbon, all 3 ring colors, `Color_Fixed` for model) | `sprite`/`ribbon`/`ring`/`model` |
| `--color-random R,G,B[,A]` (each channel `CENTER` or `MIN:CENTER:MAX`) | `Sprite.ColorAll_Random` | `sprite` |
| `--model` (required), `--lighting` | `Model` block | `model` |
| `--track-color R:G:B[:A]` | all 6 `Track` rails, same fixed color | `track` |

PVA-shaped values accept `CENTER` (fixed) or `MIN:CENTER:MAX` (a range).

**Easing speeds are enums, not floats.** `--fade-in`/`--fade-out`'s
`START_SPEED`/`END_SPEED`, and `start_speed`/`end_speed` on `presets.easing()`
/ `axis_easing()` / `renderer_common(fade_in=/fade_out=)`, map to Effekseer's
`EasingStart`/`EasingEnd` enums: only `-30,-20,-10,0,10,20,30` exist
(negative = *Slowly1-3*, positive = *Rapidly1-3*, `0` = linear). Any other
value compiles fine via the CUI but **crashes the Effekseer editor**
(`NullReferenceException` in `GUI.Component.Enum.Update`) the moment the
Basic Render Settings dock shows that node — which is how the first three
toolkit-built effects were shipped. The toolkit now rejects such values at
build time (`ValueError` / `CliError`), and `validate` / every `add-node` /
`set-params` / `apply` write runs the same enum-domain check (`enums.py`)
over the other enum-typed leaves it knows about (`Filter`, `AlphaBlend`,
`Billboard`, `UV`, the `Type` selectors, ...), refusing to write a violation.
Per-corner Sprite offsets/colors, per-rail Track differentiation, Easing/
AxisPVA variants, `ColorAll_Easing`/Ring's per-position (`OuterColor`/
`CenterColor`/`InnerColor`) Random+Easing color modes, `LocationAbsValues`
(gravity/attractive force), and `SoundValues` have no dedicated flags yet -
build them via `tools.effect.presets` directly (see below) or `--set`.

### Building nodes programmatically

For anything beyond a couple of `--set` flags, it's usually easier to import
`tools.effect.presets` directly and build the tree in a small Python script
than to chain many CLI calls — see `presets.py`'s docstrings, or
`selftest.py`'s `stage_presets_roundtrip` for a worked example (builds a
ring + sprite node purely through the preset functions, no hand XML).

## Known limitations

* **Node kinds**: `Sprite` / `Ring` / `Ribbon` / `Model` / `Track`
  `DrawingValues` are modeled (`DRAWING_TYPE` in `presets.py`), plus the two
  `Node`-level sibling blocks `SoundValues` and `LocationAbsValues`
  (gravity/attractive force) — evidenced across a 310-file corpus spanning
  11 real asset packs (AndrewFM01, MAGICALxSPIRAL, NextSoft01, NitoriBox,
  Pierre01_130, Pierre02_130, ProjectDanmakuGirls, Suzuki01, TouhouStrategy,
  tktk01, tktk02). Still unmodeled, same reasoning as before (rare and/or no
  confirmed-*active* real example to crib from):
  * FCurve (keyframed) variants — Scaling/Rotation `Type=5`, Sprite
    `ColorAll`/GenerationLocationValues `Type=3`/`4` FCurve modes.
  * `RotationValues` `Type=4`/`AxisEasing` (`presets.axis_easing()` exists,
    built by structural analogy with `AxisPVA`/`Easing`, but never appears
    *actively selected* in any of the 310 samples — treat as unverified).
  * Project-root `Behavior`/`TargetLocation`/`Culling` (camera/viewer
    metadata, siblings of `<Root>` under `<EffekseerProject>`, unrelated to
    per-node particle motion).
  * A `Field`/turbulence/collision node concept — searched for across all
    310 samples, zero matches; likely absent from this Effekseer version.
  * `GenerationLocationValues`'s `Model`-shaped emission (spawn from another
    model's surface) — real but rare (concentrated in one effect family),
    unlike the `Point`/`Circle`/`Sphere` shapes which are modeled.

  Ring's `OuterColor`/`CenterColor`/`InnerColor` and Sprite/Ribbon's
  `ColorAll` all support the same Fixed/Random/Easing triad (each an
  independent 0/1/2 selector, confirmed real) — see `presets._append_color_mode`.

  Add any of these the same way the rest of this toolkit was built — from a
  real `.efkproj` sample that actively uses the feature — in `presets.py`
  (a new builder + `DRAWING_TYPE` entry for a new `DrawingValues` kind) and
  `cli.py` (`_KIND_BUILDERS` / `_build_drawing()`).
* **Not a schema validator**: `validate` checks structure plus the enum
  domains in `enums.py` (int values of the enum-typed leaves the toolkit
  writes, verified against a 310-file real corpus), not every field's
  legality — Effekseer's real schema is hundreds of fields across dozens of
  node kinds, most only present because they differ from the editor's
  default. `add-node`/`set-params` will happily write a field name that
  isn't real (Effekseer's loader is also **case-sensitive**: `<center>` is
  silently ignored where `<Center>` is meant — `presets.pva()` used to do
  exactly that for per-axis dicts); the only hard check for anything not in
  `enums.py` is the CUI compile step — and the CUI does *not* catch enum
  values the editor will crash on.
* **The CUI compile step is machine-specific.** The CUI is looked up via
  `--cui-path`, then `$EFFEKSEER_CUI`, then `effekseer.cui_path` in
  `effect_config.json`. The toolkit is verified with Effekseer **1.7.3.0**
  (`effekseer.verified_version`) — its `.efkefc` output's `INFO`-chunk
  version matches assets already shipped in `Assets/Art/Effect/`
  byte-for-byte. Other versions (e.g. 1.80.2) were **not** verified: effects
  built with a different Effekseer version may fail to load. In that case,
  contact NiceBody via
  [Issues](https://github.com/ramasuke/EffekseerEfkprojTool/issues) — we'll
  try to build a toolkit for that version. `Effekseer.exe`'s file-version
  resource reads `1.0.0.0`, so the actual version can't be detected
  automatically.
* **Reverse direction (`.efkefc` → `.efkproj`) is not supported** — no local
  CUI build can do it (confirmed dead end, matches an upstream GitHub
  issue). This toolkit is for authoring new effects, not round-tripping
  ones already shipped as compiled binaries.

## After changing the codec or presets

* `.py` files here are plain UTF-8/ASCII — not subject to the Shift-JIS
  conversion hook that applies to `.h`/`.cpp`.
* Always run `python tools/effect/selftest.py` after editing `model.py`,
  `xmlio.py`, `presets.py`, `enums.py`, `meta.py`, `config.py`, or
  `export.py`. Its CUI-compile stage and the real-corpus enum sweep
  (`$EFFEKSEER_CORPUS`, else `selftest.corpus_dir` in `effect_config.json`)
  are best-effort and skip cleanly on a machine without them; the stages
  reading shipped `Assets/Art/Effect/` assets skip outside NanamiEngine.
* A new file the toolkit needs at runtime must also be added to
  `export.MANIFEST`, or the public repository won't get it.
