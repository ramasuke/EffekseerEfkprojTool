"""Self-test / correctness gate for tools.effect.

Run:  python tools/effect/selftest.py         (from repo root)
      python -m tools.effect selftest

Exit 0 = all good, 1 = failure. No third-party dependencies.

Stages:
  1. xmlio formatting fidelity: serialize(parse(text)) == text for every real
     fixture (copied from the AndrewFM01 samples this toolkit was built from).
  2. presets/model round trip: build a tree purely via presets.py (no hand
     XML), parse -> serialize -> reparse, assert structurally stable.
  3. .meta round trip against real, already-shipped ParticleFile assets
     (proves the base_class_count=2 fix in tools/common/meta_base.py holds).
  4. install() path-convention check against a real nested asset.
  5. best-effort CUI compile: runs once per Effekseer CUI found on this
     machine (every effekseer.cui_paths entry, plus the one the target version
     resolves to); compiles a fixture and presets-built trees, checks exit 0,
     the EFKE container and the binary version that Effekseer version writes.
     Skipped elsewhere.
  6. Effekseer enum domains (enums.py): out-of-range easing speeds are
     rejected at build time and by `validate`, pva() per-axis blocks come out
     with the capitalised <Center>/<Max>/<Min> Effekseer actually reads, and
     `install` keeps an existing asset's GUID.
  7. best-effort corpus sweep: every real .efkproj under $EFFEKSEER_CORPUS
     (default: selftest.corpus_dir in effect_config.json) must produce zero
     enum-domain violations for both Effekseer 1.7 and 1.80, and zero
     CommonValues layout problems - the false-positive guard for enums.py's
     tables. The editor-written EDIT chunks of every shipped .efkefc are swept
     the same way (with the profile of the editor that saved them).
  8. effect_config.json loading (defaults, relative paths, JSON errors,
     meta.enabled=false install) and `export` (manifest complete, no
     user-profile paths, distributed config has no CUI path).
  9. texture/model references: validate/compile refuse missing files and
     --out in another folder; install copies referenced files next to --dest,
     rebases the --project copy, refuses missing / conflicting / ../ refs; every
     real _Source/ .efkproj resolves.
 10. Effekseer versions (versions.py / efkefc.py): ToolVersion parsing, the
     per-file migration rules (versions.MIGRATIONS) and their guards,
     per-family enum domains, version/CUI resolution (cui_paths, CUI version
     detection, mismatch refusal), INFO chunk layouts (string lists vs
     dependency list) and install's project.runtime_version guard.
 11. best-effort Effekseer 1.80 ground truth: with a 1.80 CUI, compile
     presets-built trees under several ToolVersions and decode the EDIT
     chunk: every value Effekseer drops is caught by versions.MIGRATIONS,
     presets' v180 CommonValues matches what 1.80 itself migrates to, 1.80-only
     enum values survive, and `upgrade` produces a native file that compiles
     to the same effect.

Stages 3/4 and parts of 6 read real assets under project.effect_dir and skip
when they are absent (e.g. outside NanamiEngine).
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import sys
import traceback
from pathlib import Path

_HERE = Path(__file__).resolve()
_REPO = _HERE.parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from tools.effect import assets, cli, config, efkefc, enums, export, meta, presets as p, versions, xmlio  # noqa: E402
from tools.effect.model import Elem  # noqa: E402
from tools.common import cereal_json as cj  # noqa: E402

CONFIG = config.get()

TESTDATA = _HERE.parent / "testdata"
FIXTURES = [
    "actionLines_shockwave", "smallTexturesRibbon", "drill",
    # Added when Model/Track/LocationAbsValues/RotationValues-AxisPVA support
    # was built from a wider 310-file real-sample corpus (Effekseer素材/):
    "blue_laser",       # AndrewFM01 - Circle (Type=3) generation + AttractiveForce
    "Gohlem1",          # MAGICALxSPIRAL - Model (Type=5) DrawingValues
    "Sylph2",           # MAGICALxSPIRAL - Track (Type=6) DrawingValues
    "Water_Impact",     # MAGICALxSPIRAL - RotationValues AxisPVA (Type=3)
]

REAL_EFFECT_DIR = CONFIG.effect_dir
# The 310-file real sample corpus the toolkit was built from (11 asset packs);
# machine-specific like the CUI, so the sweep skips cleanly when absent.
DEFAULT_CORPUS_DIR = CONFIG.corpus_dir
REAL_META_FIXTURES = [
    REAL_EFFECT_DIR / "Laser01.efkefc.meta",
    REAL_EFFECT_DIR / "tktk01" / "fireSpark.efkefc.meta",
    REAL_EFFECT_DIR / "MAGICALxSPIRAL" / "Salamander11.efkefc.meta",
]


def _efkefc_bytes(version: int, paths: list[str]) -> bytes:
    """A minimal .efkefc: EFKE header, an INFO chunk in the layout ``version``
    uses (string lists up to 1610, one dependency list after) and a BIN_
    chunk with just the SKFE header."""
    import struct

    def utf16(text: str) -> bytes:
        return struct.pack("<i", len(text) + 1) + (text + "\x00").encode("utf-16-le")

    if version <= 1610:
        info = struct.pack("<ii", version, len(paths)) + b"".join(utf16(x) for x in paths)
    else:
        info = struct.pack("<ii", version, len(paths)) + b"".join(
            struct.pack("<ii", 1, 1) + utf16(x) for x in paths)
    body = b"SKFE" + struct.pack("<i", version)
    return (b"EFKE\x00\x00\x00\x00INFO" + struct.pack("<I", len(info)) + info
            + b"BIN_" + struct.pack("<I", len(body)) + body)


_EMPTY_EFKEFC = _efkefc_bytes(1710, [])


class Reporter:
    def __init__(self) -> None:
        self.failed = 0
        self.passed = 0

    def ok(self, name: str) -> None:
        self.passed += 1
        print(f"  PASS  {name}")

    def fail(self, name: str, err: str) -> None:
        self.failed += 1
        lines = err.strip().splitlines() or [err]
        print(f"  FAIL  {name}\n        {lines[0]}")
        for line in lines[1:]:
            print(f"        {line}")

    def section(self, title: str) -> None:
        print(f"\n=== {title} ===")

    def finish(self) -> int:
        total = self.passed + self.failed
        print(f"\n{self.passed}/{total} checks passed"
              + (f", {self.failed} FAILED" if self.failed else ""))
        return 1 if self.failed else 0


def stage_formatting(r: Reporter) -> None:
    r.section("stage 1: xmlio formatting fidelity")
    for name in FIXTURES:
        path = TESTDATA / f"{name}.efkproj"
        try:
            xmlio.self_check_roundtrip(path)
            r.ok(path.name)
        except Exception:  # noqa: BLE001
            r.fail(path.name, traceback.format_exc())


def _assert_roundtrip_stable(proj: Elem) -> None:
    text = xmlio.serialize(proj)
    rt_text = xmlio.serialize(xmlio.parse(text))
    if rt_text != text:
        raise AssertionError("presets-built tree is not stable under parse -> serialize")


def stage_presets_roundtrip(r: Reporter) -> None:
    r.section("stage 2: presets/model round trip")
    try:
        ring_block = p.ring(
            vertex_count=36,
            outer=p.xyz("Location", x=1.8), inner=p.xyz("Location", x=0),
            center_ratio=0.8,
            outer_color=p.color("OuterColor_Fixed", r=0, g=0, b=0),
            inner_color=p.color("InnerColor_Fixed", r=0, g=0, b=0, a=255),
        )
        n1 = p.ring_node("Node", ring_block=ring_block)
        sprite_block = p.sprite(billboard=2, color_all=p.color("ColorAll_Fixed", r=255, g=200, b=100))
        n2 = p.sprite_node(
            "Node", sprite_block=sprite_block,
            common=p.common_values(layout="legacy", max_generation=50,
                                    generation_time={"center": 0.02, "max": 0.02, "min": 0.02}),
            scaling=p.scaling_values(fixed=p.xyz("Scale", x=1.0)),
        )
        proj = p.new_project(root_children=[n1, n2])
        _assert_roundtrip_stable(proj)
        r.ok("presets-built ring+sprite tree stable")
    except Exception:  # noqa: BLE001
        r.fail("presets-built ring+sprite tree", traceback.format_exc())

    try:
        # Regression check: generation_location_circle() used to hardcode
        # Type="0" (should be "3" - every real Circle-shaped sample uses the
        # outer Type=3 selector; Type=0 is Point).
        circle = p.generation_location_circle(division=8, circle_type=1,
                                               radius={"center": 2, "max": 2, "min": 2})
        if circle.require("Type").text != "3":
            raise AssertionError(f"generation_location_circle() Type = {circle.require('Type').text!r}, expected '3'")
        r.ok("generation_location_circle() writes outer Type=3")
    except Exception:  # noqa: BLE001
        r.fail("generation_location_circle() Type", traceback.format_exc())

    try:
        model_block = p.model(
            model_path="Model/rock.efkmodel", lighting=False,
            color_fixed=p.color("Color_Fixed", r=24, g=16, b=32),
            color_easing=p.easing(
                "Color_Easing",
                start=p.random_color("Start", r={"center": 112, "max": 112, "min": 112}),
                end=p.random_color("End", r={"center": 60, "max": 60, "min": 60}),
                start_speed=20, end_speed=-30,
            ),
        )
        track_block = p.track(
            color_left=p.color("ColorLeft_Fixed", a=0),
            color_center=p.easing(
                "ColorCenter_Easing",
                start=p.random_color("Start", a={"center": 0, "max": 0, "min": 0}),
                end=p.random_color("End", a={"center": 192, "max": 192, "min": 192}),
            ),
        )
        n_model = p.model_node("Node", model_block=model_block)
        n_track = p.track_node(
            "Node", track_block=track_block,
            sound=p.sound_values(wave="Sound/x.wav", volume={"center": 1, "max": 1, "min": 1},
                                  pan_type=0, distance=10),
            location_abs=p.location_abs_values(attractive_force=0.025),
            generation_location=p.generation_location_point(
                location={"x": {"center": 0, "max": 1, "min": -1}}),
        )
        proj = p.new_project(root_children=[n_model, n_track])
        _assert_roundtrip_stable(proj)
        r.ok("presets-built model+track+sound+location_abs tree stable")
    except Exception:  # noqa: BLE001
        r.fail("presets-built model+track+sound+location_abs tree", traceback.format_exc())

    try:
        rotation = p.rotation_values(axis_pva=p.axis_pva(
            axis=p.xyz("Axis", y=p.pva("Y", center=0, max=0, min=0), z=p.pva("Z", center=1, max=1, min=1)),
            rotation={"center": 0, "max": 1808, "min": -1808},
            velocity={"center": 0, "max": 1, "min": -1},
        ))
        rotation2 = p.rotation_values(axis_easing=p.axis_easing(
            axis=p.xyz("Axis", z=p.pva("Z", center=1, max=1, min=1)),
            start={"center": 0, "max": 0, "min": 0}, end={"center": 90, "max": 90, "min": 90},
            start_speed=10, end_speed=-10,
        ))
        scaling = p.scaling_values(easing=p.easing(
            "Easing",
            start=p.elem("Start", Z=p.pva("Z", max=180, min=-180)),
            end=p.elem("End", Z=p.pva("Z", max=0, min=0)),
        ))
        scaling2 = p.scaling_values(single_easing=p.easing(
            "SingleEasing", start=p.pva("Start", center=0, max=0, min=0),
            end=p.pva("End", center=1.5, max=1.75, min=1.25), start_speed=30, end_speed=-30,
        ))
        location = p.location_values(easing=p.easing(
            "Easing",
            start=p.elem("Start", X=p.pva("X", max=0.2, min=-0.2)),
            end=p.elem("End", X=p.pva("X", max=3, min=-3)),
        ))
        n1 = p.node("Node", rotation=rotation, scaling=scaling, location=location,
                    common=p.common_values(layout="legacy", location_effect_type=1, rotation_effect_type=1,
                                            scale_effect_type=1,
                                            remove_when_all_children_removed=False))
        n2 = p.node("Node", rotation=rotation2, scaling=scaling2,
                    generation_location=p.generation_location_sphere(
                        radius={"center": 2, "max": 2, "min": 2}))
        proj = p.new_project(root_children=[n1, n2])
        _assert_roundtrip_stable(proj)
        r.ok("presets-built Easing/AxisPVA/AxisEasing/SinglePVA tree stable")
    except Exception:  # noqa: BLE001
        r.fail("presets-built Easing/AxisPVA/AxisEasing/SinglePVA tree", traceback.format_exc())

    try:
        sprite_block = p.sprite(
            rendering_order=1,
            color_all_random=p.random_color("ColorAll_Random",
                                             r={"center": 0, "max": 255, "min": 0},
                                             a={"center": 255, "max": 255, "min": 255}),
            position_corners={"ll": {"x": -0.5, "y": 0}, "lr": {"x": 0.5, "y": 0},
                               "ul": {"x": -0.5, "y": 1}, "ur": {"x": 0.5, "y": 1}},
            color_corners={"ll": {"r": 255, "g": 0, "b": 0}, "ur": {"r": 0, "g": 0, "b": 255}},
        )
        renderer = p.renderer_common(
            color_texture="Texture/t.png",
            fade_in={"frame": 4, "start_speed": 0, "end_speed": 0}, fade_out={"frame": 8},
            ztest=False, color_inherit_type=2, distortion=True, distortion_intensity=0.3,
            uv_scroll={"speed": {"x": 16, "y": 0}},
        )
        n1 = p.sprite_node("Node", sprite_block=sprite_block, renderer_common=renderer)
        n2 = p.node("Node", renderer_common=p.renderer_common(
            uv_fixed={"start": {"x": 0, "y": 0}, "size": {"x": 0.5, "y": 0.5}}),
            drawing=p.drawing_values("sprite", p.sprite()))
        n3 = p.node("Node", renderer_common=p.renderer_common(
            uv_animation={"size": {"x": 64, "y": 64}, "frame_length": 2,
                          "frame_count_x": 4, "frame_count_y": 4, "loop_type": 1}),
            drawing=p.drawing_values("sprite", p.sprite()))
        proj = p.new_project(root_children=[n1, n2, n3])
        _assert_roundtrip_stable(proj)
        r.ok("presets-built Sprite corners/random-color + RendererCommonValues UV/fade tree stable")
    except Exception:  # noqa: BLE001
        r.fail("presets-built Sprite/RendererCommonValues tree", traceback.format_exc())

    try:
        # ColorAll_Easing (Sprite/Ribbon) and Ring's independent per-position
        # OuterColor/CenterColor/InnerColor Random/Easing selectors - found
        # after the initial Model/Track/Sound pass, via a second look at the
        # same 310-file corpus (confirmed real: MAGICALxSPIRAL/AquaPoint.efkproj
        # for ColorAll_Easing + the block-level DrawnAs/ColorSpace siblings on
        # *_Random; AndrewFM01/boss_death.efkproj for Ribbon's ColorAll=2).
        sprite_easing = p.sprite(color_all_easing=p.easing(
            "ColorAll_Easing",
            start=p.random_color("Start", r={"center": 255, "max": 255, "min": 255}, drawn_as=1),
            end=p.random_color("End", r={"center": 0, "max": 0, "min": 0}, drawn_as=1),
        ))
        ribbon_random = p.ribbon(color_all_random=p.random_color(
            "ColorAll_Random", r={"center": 127, "max": 255, "min": 0},
            drawn_as=1, color_space=0))
        ring_modes = p.ring(
            center_ratio=0.8,
            outer_color_random=p.random_color("OuterColor_Random", a={"center": 200, "max": 255, "min": 150}),
            center_color_easing=p.easing(
                "CenterColor_Easing",
                start=p.random_color("Start", g={"center": 0, "max": 0, "min": 0}),
                end=p.random_color("End", g={"center": 255, "max": 255, "min": 255}),
            ),
            inner_color=p.color("InnerColor_Fixed", r=0, g=0, b=0, a=255),
        )
        proj = p.new_project(root_children=[
            p.sprite_node("Node", sprite_block=sprite_easing),
            p.ribbon_node("Node", ribbon_block=ribbon_random),
            p.ring_node("Node", ring_block=ring_modes),
        ])
        _assert_roundtrip_stable(proj)
        r.ok("presets-built ColorAll_Easing + Ring per-position color-mode tree stable")
    except Exception:  # noqa: BLE001
        r.fail("presets-built ColorAll_Easing/Ring color-mode tree", traceback.format_exc())


def stage_meta_roundtrip(r: Reporter) -> None:
    r.section("stage 3: .meta round trip (real shipped ParticleFile assets)")
    for path in REAL_META_FIXTURES:
        try:
            if not path.exists():
                r.ok(f"{path.name} (skipped: not present)")
                continue
            orig = cj.loads(cj.read_text(path))
            info = meta.read_meta(path)
            rt = cj.loads(meta.render_meta(info["name"], info["guid"], info["content_path"]))
            if cj.dumps(rt) != cj.dumps(orig):
                raise AssertionError("re-rendered .meta does not match the original byte-for-byte")
            r.ok(path.relative_to(CONFIG.project_root).as_posix())
        except Exception:  # noqa: BLE001
            r.fail(path.name, traceback.format_exc())


def stage_content_path_convention(r: Reporter) -> None:
    r.section("stage 4: content_path_for() convention check")
    try:
        target_dir = REAL_EFFECT_DIR / "tktk01"
        if not (target_dir / "fireSpark.efkefc.meta").exists():
            r.ok("content_path_for() convention (skipped: tktk01/fireSpark.efkefc.meta not present)")
            return
        got = meta.content_path_for("fireSpark", target_dir, CONFIG.project_root)
        want = meta.read_meta(target_dir / "fireSpark.efkefc.meta")["content_path"]
        if got != want:
            raise AssertionError(f"content_path_for() = {got!r}, real asset has {want!r}")
        r.ok("content_path_for() matches real fireSpark.efkefc.meta (all-backslash)")
    except Exception:  # noqa: BLE001
        r.fail("content_path_for() convention", traceback.format_exc())


def _compile_check(cui: Path, profile: versions.Profile, in_path: Path, out_path: Path) -> None:
    import subprocess
    result = subprocess.run(
        [str(versions.resolve_cui_exe(cui)), "-cui", "-in", str(in_path), "-o", str(out_path)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise AssertionError(f"CUI exited {result.returncode}: {result.stderr[:300]}")
    if not out_path.exists():
        raise AssertionError(f"CUI exited 0 but produced no output file: {result.stdout[-300:]}")
    data = out_path.read_bytes()
    if efkefc.info_version(data) != profile.binary_version or efkefc.bin_version(data) != profile.binary_version:
        raise AssertionError(f"binary version INFO={efkefc.info_version(data)} BIN_={efkefc.bin_version(data)}, "
                             f"expected {profile.binary_version} for Effekseer {profile.family}")


def available_cuis() -> list[tuple[str, Path, versions.Profile]]:
    """``(version, exe, profile)`` for every distinct Effekseer CUI present:
    each ``effekseer.cui_paths`` entry plus whatever the target version
    resolves to (``$EFFEKSEER_CUI`` / ``effekseer.cui_path`` included)."""
    found: list[tuple[str, Path]] = [(k, v) for k, v in CONFIG.cui_paths.items() if v.is_file()]
    eff = cli.resolve_effekseer(None, None)
    if eff.cui is not None:
        found.append((eff.detected or eff.version, eff.cui))
    out: list[tuple[str, Path, versions.Profile]] = []
    seen: set[Path] = set()
    for version, exe in found:
        real = versions.resolve_cui_exe(exe).resolve()
        if real in seen:
            continue
        seen.add(real)
        version = versions.detect_cui_version(exe) or version
        out.append((version, exe, versions.profile_for(version)))
    return out


def stage_cui_compile(r: Reporter) -> None:
    r.section("stage 5: CUI compile (best-effort, machine-specific)")
    cuis = available_cuis()
    if not cuis:
        r.ok(f"skipped: no Effekseer CUI found (checked $EFFEKSEER_CUI and effekseer.cui_paths / cui_path in "
             f"{CONFIG.config_path.name})")
        return
    for version, cui, profile in cuis:
        _stage_cui_compile_one(r, version, cui, profile)


def _stage_cui_compile_one(r: Reporter, version: str, cui: Path, profile: versions.Profile) -> None:
    import tempfile
    tag = f"[Effekseer {version}]"
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        try:
            fixture = TESTDATA / "actionLines_shockwave.efkproj"
            out = tmp_path / "fixture.efkefc"
            _compile_check(cui, profile, fixture, out)
            r.ok(f"{tag} compiled fixture {fixture.name}")
        except Exception:  # noqa: BLE001
            r.fail(f"{tag} compile real fixture", traceback.format_exc())

        try:
            proj = p.new_project(root_children=[
                p.ring_node("Node", ring_block=p.ring(vertex_count=36, center_ratio=0.8)),
            ])
            in_path = tmp_path / "presets_demo.efkproj"
            xmlio.write(in_path, proj)
            out = tmp_path / "presets_demo.efkefc"
            _compile_check(cui, profile, in_path, out)
            r.ok(f"{tag} compiled presets-built tree")
        except Exception:  # noqa: BLE001
            r.fail(f"{tag} compile presets-built tree", traceback.format_exc())

        try:
            # Model/Track are the two DrawingValues kinds added from the
            # wider 310-file corpus (DRAWING_TYPE 5/6) - confirm the real
            # CUI still accepts them (and the LocationAbsValues/SoundValues/
            # generation_location_point blocks alongside), not just that our
            # own xmlio round-trips them.
            model_node = p.model_node(
                "Node", model_block=p.model(model_path="Model/rock.efkmodel"),
                location_abs=p.location_abs_values(attractive_force=0.025))
            track_node = p.track_node(
                "Node", track_block=p.track(color_left=p.color("ColorLeft_Fixed", a=128)),
                sound=p.sound_values(wave="Sound/x.wav", distance=10),
                generation_location=p.generation_location_point())
            proj = p.new_project(root_children=[model_node, track_node])
            in_path = tmp_path / "model_track_demo.efkproj"
            xmlio.write(in_path, proj)
            out = tmp_path / "model_track_demo.efkefc"
            _compile_check(cui, profile, in_path, out)
            r.ok(f"{tag} compiled Model+Track presets-built tree")
        except Exception:  # noqa: BLE001
            r.fail(f"{tag} compile Model+Track presets-built tree", traceback.format_exc())

        try:
            proj = p.new_project(root_children=[
                p.sprite_node("Node", sprite_block=p.sprite(color_all_easing=p.easing(
                    "ColorAll_Easing",
                    start=p.random_color("Start", r={"center": 255, "max": 255, "min": 255}),
                    end=p.random_color("End", r={"center": 0, "max": 0, "min": 0}),
                ))),
                p.ring_node("Node", ring_block=p.ring(
                    center_ratio=0.8,
                    outer_color_random=p.random_color("OuterColor_Random",
                                                       a={"center": 200, "max": 255, "min": 150}))),
            ])
            in_path = tmp_path / "color_modes_demo.efkproj"
            xmlio.write(in_path, proj)
            out = tmp_path / "color_modes_demo.efkefc"
            _compile_check(cui, profile, in_path, out)
            r.ok(f"{tag} compiled ColorAll_Easing/Ring-color-mode presets-built tree")
        except Exception:  # noqa: BLE001
            r.fail(f"{tag} compile ColorAll_Easing/Ring-color-mode presets-built tree", traceback.format_exc())

        try:
            # Regression check for DRAWING_TYPE["sprite"]: a Sprite node's
            # RendererCommonValues.ColorTexture must actually reach the
            # compiled INFO chunk (as a UTF-16LE string) - it silently didn't
            # when "sprite" mapped to node-type 0 (which Effekseer treats as
            # "no drawing", not Sprite; the real value is 2), so nothing
            # referenced the texture and the CUI dropped it with no error.
            renderer = Elem("RendererCommonValues")
            renderer.set_path("ColorTexture", "Texture/selftestRegressionTex.png")
            node = p.sprite_node("Node", sprite_block=p.sprite(billboard=2),
                                  common=p.common_values(layout="legacy", life={"center": 60, "max": 60, "min": 60}),
                                  renderer_common=renderer)
            proj = p.new_project(root_children=[node])
            in_path = tmp_path / "sprite_texture_demo.efkproj"
            xmlio.write(in_path, proj)
            out = tmp_path / "sprite_texture_demo.efkefc"
            _compile_check(cui, profile, in_path, out)
            compiled_text = out.read_bytes().decode("utf-16-le", errors="ignore")
            if "selftestRegressionTex" not in compiled_text:
                raise AssertionError(
                    "Sprite node's ColorTexture did not survive CUI compile - "
                    "DRAWING_TYPE['sprite'] regressed back to node-type 0 (\"none\")?"
                )
            got = efkefc.parse_asset_paths(out.read_bytes())
            if got != ["Texture/selftestRegressionTex.png"]:
                raise AssertionError(f"parse_asset_paths() = {got!r}, expected the one ColorTexture")
            r.ok(f"{tag} Sprite node's ColorTexture survives CUI compile (and the INFO chunk parses strictly)")
        except Exception:  # noqa: BLE001
            r.fail(f"{tag} sprite texture reaches compiled INFO chunk", traceback.format_exc())


def _add_node_args(proj_path: Path, **overrides) -> argparse.Namespace:
    """``add-node``'s parsed arguments with every flag unset."""
    ns = argparse.Namespace(file=str(proj_path), parent="", kind="sprite", name="N",
                            life=None, max_generation=None, infinite=None, generation_time=None,
                            generation_timing=None, trigger=None, trigger_count=None,
                            trigger_to_start=None, trigger_to_stop=None, trigger_to_remove=None,
                            color_texture=None, fade_in=None, fade_out=None, uv_scroll=None,
                            generation_shape=None, radius=None, division=None,
                            angle_start=None, angle_end=None, billboard=None, color=None,
                            color_random=None, model=None, lighting=None, track_color=None,
                            set=None, effekseer_version=None)
    for key, value in overrides.items():
        if not hasattr(ns, key):
            raise AttributeError(f"add-node has no argument {key!r}")
        setattr(ns, key, value)
    return ns


def _assert_raises_value_error(fn, what: str) -> None:
    try:
        fn()
    except ValueError:
        return
    raise AssertionError(f"{what} was accepted; expected ValueError")


def stage_enum_domains(r: Reporter) -> None:
    r.section("stage 6: Effekseer enum domains (editor-crash guard) + pva() casing + install GUID reuse")
    try:
        # FadeIn/FadeOut StartSpeed/EndSpeed and every Easing block's
        # StartSpeed/EndSpeed are Enum<EasingStart>/<EasingEnd> in Effekseer
        # (-30..30 step 10). The shipped DragonDefeatSparkle/FootstepDust/
        # DragonFireBall sources were built with EndSpeed=-50..-100, which the
        # CUI compiled happily and Effekseer's editor then crashed on
        # (NullReferenceException in GUI.Component.Enum.Update) as soon as the
        # Basic Render Settings dock showed such a node.
        _assert_raises_value_error(
            lambda: p.renderer_common(fade_out={"frame": 4, "start_speed": 0, "end_speed": -90}),
            "renderer_common(fade_out end_speed=-90)")
        _assert_raises_value_error(
            lambda: p.renderer_common(fade_in={"frame": 4, "start_speed": 15}),
            "renderer_common(fade_in start_speed=15)")
        _assert_raises_value_error(
            lambda: p.easing("Easing", start_speed=0, end_speed=-100),
            "easing(end_speed=-100)")
        _assert_raises_value_error(
            lambda: p.axis_easing(axis=p.xyz("Axis", z=p.pva("Z", center=1, max=1, min=1)), start_speed=5),
            "axis_easing(start_speed=5)")
        ok = p.renderer_common(fade_out={"frame": 4, "start_speed": 0, "end_speed": -30.0})
        got = (ok.get("FadeOut.StartSpeed").text, ok.get("FadeOut.EndSpeed").text)
        if got != ("0", "-30"):
            raise AssertionError(f"legal speeds serialised as {got!r}")
        for v in enums.EASING_SPEEDS:
            p.easing("Easing", start_speed=v, end_speed=v)
        r.ok("presets reject out-of-range easing speeds and accept the 7 legal ones")
    except Exception:  # noqa: BLE001
        r.fail("presets easing-speed validation", traceback.format_exc())

    try:
        try:
            cli._parse_fade("4:0:-90")
        except cli.CliError as e:
            if "-30" not in str(e):
                raise AssertionError(f"CliError does not list the legal values: {e}")
        else:
            raise AssertionError("_parse_fade('4:0:-90') was accepted")
        if cli._parse_fade("4:10:-30") != {"frame": 4.0, "start_speed": 10, "end_speed": -30}:
            raise AssertionError("_parse_fade('4:10:-30') parsed wrong")
        r.ok("--fade-in/--fade-out reject out-of-range speeds")
    except Exception:  # noqa: BLE001
        r.fail("cli _parse_fade", traceback.format_exc())

    try:
        # Regression: pva() per-axis dicts used to write the dict keys verbatim
        # (<center>/<max>/<min>), which Effekseer's case-sensitive loader
        # ignores - every shipped effect with a random Scale silently ran at
        # scale 1.0.
        scale = p.pva("Scale", x={"center": 0.6, "max": 0.9, "min": 0.4},
                      y={"center": 0.6, "max": 0.9, "min": 0.4}, drawn_as=0)
        text = xmlio.serialize(scale)
        for bad in ("<center>", "<max>", "<min>"):
            if bad in text:
                raise AssertionError(f"pva() still writes lowercase {bad}")
        if scale.get("X.Center").text != "0.6" or scale.get("Y.Min").text != "0.4" or scale.get("DrawnAs").text != "0":
            raise AssertionError(f"pva() per-axis shape wrong:\n{text}")
        point = p.generation_location_point(location={"x": {"center": 0, "max": 1, "min": -1}})
        if point.get("Point.Location.X.Max") is None:
            raise AssertionError("generation_location_point() per-axis Location lost its Max")
        r.ok("pva() per-axis dicts serialise as <Center>/<Max>/<Min>")
    except Exception:  # noqa: BLE001
        r.fail("pva() per-axis casing", traceback.format_exc())

    try:
        for name in FIXTURES:
            for profile in versions.PROFILES:
                problems = enums.check_project(xmlio.read(TESTDATA / f"{name}.efkproj"), profile)
                if problems:
                    raise AssertionError(f"false positive(s) in real fixture {name} ({profile.family}): {problems[:3]}")
        node = p.sprite_node("Node", sprite_block=p.sprite(),
                             renderer_common=p.renderer_common(fade_out={"frame": 4}))
        node.set_path("RendererCommonValues.FadeOut.EndSpeed", "-90")
        node.set_path("DrawingValues.Sprite.Billboard", "7")
        node.set_path("CommonValues.MaxGeneration.Value", "-90")  # plain int, not an enum: must not be flagged
        problems = enums.check_node(node, versions.PROFILE_180)
        if len(problems) != 2 or "EndSpeed=-90" not in problems[0] or "Billboard=7" not in problems[1]:
            raise AssertionError(f"check_node() = {problems!r}, expected exactly the EndSpeed and Billboard hits")
        proj = p.new_project(root_children=[p.group_node("G", children=[node])])
        got = enums.check_project(proj, versions.PROFILE_17)
        if len(got) != 2 or not got[0].startswith("[0.0] Node:"):
            raise AssertionError(f"check_project() = {got!r}")
        only_180 = p.sprite_node("Node", sprite_block=p.sprite(billboard=4),
                                 renderer_common=p.renderer_common(wrap=2))
        only_180.set_path("RotationValues.Type", "7")
        only_180.set_path("RotationValues.Velocity.Axis", "5")
        only_180.set_path("CommonValues.Generation.Trigger", "3")
        if enums.check_node(only_180, versions.PROFILE_180):
            raise AssertionError(f"1.80-only values flagged for 1.80: {enums.check_node(only_180, versions.PROFILE_180)}")
        hits_17 = enums.check_node(only_180, versions.PROFILE_17)
        if sorted(h.split("=")[0] for h in hits_17) != ["DrawingValues/Sprite/Billboard", "RendererCommonValues/Wrap",
                                                        "RotationValues/Type"]:
            raise AssertionError(f"1.80-only values for 1.7: {hits_17}")
        only_180.set_path("RotationValues.Velocity.Axis", "6")
        if len(enums.check_node(only_180, versions.PROFILE_180)) != 1:
            raise AssertionError("RotationValues/Velocity/Axis=6 not flagged for 1.80")
        older = p.node("N", location=p.location_values(fixed_xyz={"x": 1}),
                       renderer_common=p.renderer_common(fade_out={"frame": 4}))
        older.set_path("LocationValues.Type", "5")
        older.set_path("RendererCommonValues.FadeOutType", "2")
        older.set_path("DrawingValues.TextureUVType.Type", "2")
        got = {prof.family: sorted(h.split("=")[0] for h in enums.check_node(older, prof))
               for prof in versions.PROFILES}
        want = {"1.5": ["DrawingValues/TextureUVType/Type", "LocationValues/Type", "RendererCommonValues/FadeOutType"],
                "1.6": ["DrawingValues/TextureUVType/Type", "RendererCommonValues/FadeOutType"],
                "1.7": ["DrawingValues/TextureUVType/Type"], "1.80": []}
        if got != want:
            raise AssertionError(f"per-family domains: {got!r}")
        r.ok("enums.check_node()/check_project(): 0 hits on 7 real fixtures (every family), 2 on a doctored "
             "node; Billboard=4/Wrap=2/RotateToVelocity only for 1.80, FadeOutType=2 from 1.7, "
             "LocationValues Type=5 from 1.6, TextureUVType=2 only for 1.80")
    except Exception:  # noqa: BLE001
        r.fail("enums.check_node()/check_project()", traceback.format_exc())

    try:
        # CLI paths refuse to *write* a violating node (apply stays atomic).
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            proj_path = Path(tmp) / "t.efkproj"
            xmlio.write(proj_path, p.new_project())
            before = proj_path.read_bytes()
            ns = _add_node_args(proj_path, set=["RendererCommonValues.FadeOut.EndSpeed=-90"])
            try:
                cli.cmd_add_node(ns)
            except cli.CliError:
                pass
            else:
                raise AssertionError("add-node --set EndSpeed=-90 was written")
            if proj_path.read_bytes() != before:
                raise AssertionError("add-node modified the file despite the violation")
            ops = Path(tmp) / "ops.json"
            ops.write_text(json.dumps([
                {"op": "add-node", "kind": "sprite", "name": "A"},
                {"op": "set-params", "path": "0", "set": {"DrawingValues.Sprite.Billboard": 9}},
            ]), encoding="utf-8")
            try:
                cli.cmd_apply(argparse.Namespace(file=str(proj_path), ops=str(ops), effekseer_version=None))
            except cli.CliError:
                pass
            else:
                raise AssertionError("apply with Billboard=9 was written")
            if proj_path.read_bytes() != before:
                raise AssertionError("apply modified the file despite the violation (not atomic)")
        r.ok("add-node/apply refuse to write enum-domain violations, file untouched")
    except Exception:  # noqa: BLE001
        r.fail("cli write-time enum guard", traceback.format_exc())

    try:
        import dataclasses
        import tempfile
        with tempfile.TemporaryDirectory() as tmp, \
                config.override(dataclasses.replace(CONFIG, meta_enabled=True, runtime_version="")):
            src = Path(tmp) / "src.efkefc"
            src.write_bytes(_EMPTY_EFKEFC)
            dest = Path(tmp) / "out" / "Spark.efkefc"
            ns = argparse.Namespace(efkefc=str(src), project=None, dest=str(dest))
            cli.cmd_install(ns)
            meta_path = dest.with_suffix(dest.suffix + ".meta")
            first = meta.read_meta(meta_path)
            meta_bytes = meta_path.read_bytes()
            cli.cmd_install(ns)
            second = meta.read_meta(meta_path)
            if first["guid"] != second["guid"] or meta_path.read_bytes() != meta_bytes:
                raise AssertionError("re-install re-minted the GUID / rewrote the .meta")
            if cli.efkefc_asset_paths(dest) != []:
                raise AssertionError("empty INFO chunk should yield no asset paths")
        r.ok("install keeps an existing asset's .meta/GUID on re-install")
    except Exception:  # noqa: BLE001
        r.fail("install GUID reuse", traceback.format_exc())

    try:
        shipped = REAL_EFFECT_DIR / "tktk01" / "DragonFireBall.efkefc"
        if not shipped.exists():
            r.ok(f"{shipped.name} asset paths (skipped: not present)")
        else:
            # The effect is re-saved from the Effekseer editor now and then, so
            # don't pin exact texture names - just that real paths come back.
            got = cli.efkefc_asset_paths(shipped)
            if not got or not all((shipped.parent / rel).is_file() for rel in got):
                raise AssertionError(f"efkefc_asset_paths({shipped.name}) = {got!r}")
            r.ok(f"efkefc_asset_paths() lists {len(got)} asset(s) of shipped {shipped.name}")
    except Exception:  # noqa: BLE001
        r.fail("efkefc_asset_paths() on a shipped asset", traceback.format_exc())


# Shipped effects (relative to project.effect_dir) whose EDIT chunk really does
# carry values the editor crashes on - true positives, kept visible in the
# stage 7 output instead of failing the sweep.
_KNOWN_BAD_SHIPPED_EFFECTS = {
    "tktk01/DragonFireBall.efkefc": "FadeOut EndSpeed -55..-100 from before the easing-speed guard, "
                                    "same in its _Source copy",
}


def _profile_of_editor(tool_version: str) -> versions.Profile:
    """The profile for the editor that wrote an EDIT chunk (``ToolVersion``
    is that editor's own version)."""
    return versions.profile_for(tool_version)


def stage_corpus_sweep(r: Reporter) -> None:
    r.section("stage 7: enum-domain / layout sweep over real effects (best-effort, machine-specific)")
    corpus_spec = os.environ.get("EFFEKSEER_CORPUS") or DEFAULT_CORPUS_DIR
    corpus = Path(corpus_spec) if corpus_spec else None
    files = sorted(corpus.rglob("*.efkproj")) if corpus and corpus.is_dir() else []
    if not files:
        r.ok(f"skipped: no corpus at {corpus or '(not set)'} "
             "(set selftest.corpus_dir in effect_config.json or $EFFEKSEER_CORPUS)")
    else:
        swept = 0
        unreadable: list[str] = []
        hits: list[str] = []
        for path in files:
            try:
                proj = xmlio.read(path)
            except Exception as e:  # noqa: BLE001
                unreadable.append(f"{path.name}: {type(e).__name__}")
                continue
            swept += 1
            rel = path.relative_to(corpus).as_posix()
            for profile in versions.PROFILES:
                hits.extend(f"{rel} ({profile.family}): {msg}" for msg in enums.check_project(proj, profile))
            hits.extend(f"{rel}: {msg}" for msg in versions.project_migration_problems(proj))
        if hits:
            r.fail("enum-domain / layout false positives in real corpus",
                   "\n".join(hits[:20]) + (f"\n... {len(hits)} total" if len(hits) > 20 else ""))
        else:
            r.ok(f"0 enum-domain (every family) / migration hits across {swept} real .efkproj file(s)"
                 + (f" ({len(unreadable)} unreadable, skipped)" if unreadable else ""))

    shipped = sorted(REAL_EFFECT_DIR.rglob("*.efkefc")) if REAL_EFFECT_DIR.is_dir() else []
    if not shipped:
        r.ok(f"shipped .efkefc EDIT sweep (skipped: no .efkefc under {REAL_EFFECT_DIR})")
        return
    try:
        hits = []
        known: list[str] = []
        editors: set[str] = set()
        for path in shipped:
            proj = efkefc.edit_project(path.read_bytes())
            tool_version = versions.tool_version_of(proj)
            editors.add(tool_version)
            rel = path.relative_to(REAL_EFFECT_DIR).as_posix()
            found = [f"{rel}: {msg}" for msg in enums.check_project(proj, _profile_of_editor(tool_version))]
            found += [f"{rel}: {msg}" for msg in versions.project_migration_problems(proj)]
            if found and rel in _KNOWN_BAD_SHIPPED_EFFECTS:
                known.append(f"{rel} ({len(found)} hit(s): {_KNOWN_BAD_SHIPPED_EFFECTS[rel]})")
                continue
            hits.extend(found)
        if hits:
            raise AssertionError("\n".join(hits[:20]))
        r.ok(f"0 enum-domain / migration hits in the editor-written EDIT chunks of {len(shipped)} shipped .efkefc "
             f"(editors: {', '.join(sorted(editors))})"
             + (f"; known-bad, not counted: {'; '.join(known)}" if known else ""))
    except Exception:  # noqa: BLE001
        r.fail("shipped .efkefc EDIT sweep", traceback.format_exc())


def _assert_raises_config_error(cfg_path: Path, needle: str) -> None:
    try:
        config.load(cfg_path)
    except config.ConfigError as e:
        if needle not in str(e):
            raise AssertionError(f"ConfigError does not mention {needle!r}: {e}")
        return
    raise AssertionError(f"config.load() accepted {cfg_path.read_text(encoding='utf-8')!r}")


def stage_config_and_export(r: Reporter) -> None:
    r.section("stage 8: effect_config.json loading + export")
    import dataclasses
    import tempfile

    try:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp).resolve()
            cfg_path = tmp_path / "effect_config.json"
            cfg_path.write_text(json.dumps({
                "effekseer": {"cui_path": "Effekseer/Tool/Effekseer.exe"},
                "project": {"root": "proj"},
            }), encoding="utf-8")
            cfg = config.load(cfg_path)
            want = {
                "project_root": tmp_path / "proj",
                "cui_path": tmp_path / "proj" / "Effekseer" / "Tool" / "Effekseer.exe",
                "effect_dir": tmp_path / "proj" / "Effects",
                "source_subdir": "_Source",
                "meta_enabled": False,
                "corpus_dir": None,
                "version": "",
                "cui_paths": {},
                "runtime_version": "",
            }
            got = {k: getattr(cfg, k) for k in want}
            if got != want:
                raise AssertionError(f"config.load() = {got!r}, expected {want!r}")

            abs_cui = tmp_path / "abs" / "Effekseer.exe"
            cfg_path.write_text(json.dumps({"effekseer": {"cui_path": abs_cui.as_posix()}}), encoding="utf-8")
            if config.load(cfg_path).cui_path != abs_cui:
                raise AssertionError("absolute cui_path was not kept as-is")

            cfg_path.write_text(json.dumps({
                "effekseer": {"version": "1.80.7", "cui_paths": {"1.80.7": "E/Tool/Effekseer.exe", "1.7.3.0": ""}},
                "project": {"root": "proj", "runtime_version": "1.80"},
            }), encoding="utf-8")
            cfg = config.load(cfg_path)
            if (cfg.version, cfg.cui_paths, cfg.runtime_version) != (
                    "1.80.7", {"1.80.7": tmp_path / "proj" / "E" / "Tool" / "Effekseer.exe"}, "1.80"):
                raise AssertionError(f"version/cui_paths/runtime_version = {cfg.version!r}, {cfg.cui_paths!r}, "
                                     f"{cfg.runtime_version!r}")
            cfg_path.write_text(json.dumps({"effekseer": {"verified_version": "1.7.3.0"}}), encoding="utf-8")
            if config.load(cfg_path).version != "1.7.3.0":
                raise AssertionError("the older effekseer.verified_version key is not used as the version")
        r.ok("config.load(): defaults for missing keys, relative paths resolve against project.root, "
             "version/cui_paths/runtime_version (+ older verified_version key)")
    except Exception:  # noqa: BLE001
        r.fail("config.load() defaults/paths", traceback.format_exc())

    try:
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "effect_config.json"
            cfg_path.write_text('{"effekseer": {"cui_path": "C:\\Effekseer\\Tool\\Effekseer.exe"}}',
                                encoding="utf-8")
            _assert_raises_config_error(cfg_path, "line 1")
            cfg_path.write_text('{"meta": {"enabled": "yes"}}', encoding="utf-8")
            _assert_raises_config_error(cfg_path, "meta.enabled")
            _assert_raises_config_error(Path(tmp) / "missing.json", "not found")
            cfg_path.write_text('{"effekseer": {"version": "1.90"}}', encoding="utf-8")
            _assert_raises_config_error(cfg_path, "effekseer.version")
            cfg_path.write_text('{"effekseer": {"cui_paths": {"2.0": "x.exe"}}}', encoding="utf-8")
            _assert_raises_config_error(cfg_path, "cui_paths")
            cfg_path.write_text('{"project": {"runtime_version": "9"}}', encoding="utf-8")
            _assert_raises_config_error(cfg_path, "runtime_version")
        r.ok("config.load(): single-backslash JSON, wrong type, missing file, unsupported version / "
             "cui_paths key / runtime_version raise ConfigError")
    except Exception:  # noqa: BLE001
        r.fail("config.load() errors", traceback.format_exc())

    try:
        with tempfile.TemporaryDirectory() as tmp, \
                config.override(dataclasses.replace(CONFIG, meta_enabled=False, runtime_version="")):
            src = Path(tmp) / "src.efkefc"
            src.write_bytes(_EMPTY_EFKEFC)
            dest = Path(tmp) / "out" / "Spark.efkefc"
            cli.cmd_install(argparse.Namespace(efkefc=str(src), project=None, dest=str(dest)))
            if not dest.exists():
                raise AssertionError("install did not copy the .efkefc")
            if dest.with_suffix(dest.suffix + ".meta").exists():
                raise AssertionError("install wrote a .meta with meta.enabled=false")
        r.ok("install with meta.enabled=false copies the .efkefc and writes no .meta")
    except Exception:  # noqa: BLE001
        r.fail("install with meta.enabled=false", traceback.format_exc())

    if not (_HERE.parent / "dist").is_dir():
        r.ok("export (skipped: tools/effect/dist/ only exists in the NanamiEngine source tree)")
        return
    try:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "EffekseerEfkprojTool"
            written = export.export(out, verbose=False)
            if len(written) != len(export.MANIFEST) or not all(p.is_file() for p in written):
                raise AssertionError("export did not write every manifest entry")
            user_dir = re.compile(rb"[A-Za-z]:[\\/]+Users[\\/]", re.IGNORECASE)
            personal = [p.relative_to(out).as_posix() for p in written if user_dir.search(p.read_bytes())]
            if personal:
                raise AssertionError(f"exported file(s) contain a personal path: {personal}")
            dist_cfg = config.load(out / "tools" / "effect" / "effect_config.json")
            if (dist_cfg.cui_path is not None or dist_cfg.cui_paths or dist_cfg.version or dist_cfg.runtime_version
                    or dist_cfg.meta_enabled or dist_cfg.corpus_dir is not None):
                raise AssertionError(f"distributed effect_config.json is not neutral: {dist_cfg!r}")
            if dist_cfg.project_root != out.resolve():
                raise AssertionError(f"distributed project root = {dist_cfg.project_root}, expected {out}")
        r.ok(f"export writes all {len(export.MANIFEST)} manifest files, no personal paths, neutral config")
    except Exception:  # noqa: BLE001
        r.fail("export", traceback.format_exc())


def _efkefc_with_assets(paths: list[str]) -> bytes:
    """A minimal 1.7-format .efkefc whose INFO chunk lists ``paths``."""
    return _efkefc_bytes(1710, paths)


def _assert_cli_error(fn, needle: str, what: str) -> None:
    try:
        fn()
    except cli.CliError as e:
        if needle not in str(e):
            raise AssertionError(f"{what}: CliError does not mention {needle!r}: {e}")
        return
    raise AssertionError(f"{what} was accepted")


def stage_asset_references(r: Reporter) -> None:
    r.section("stage 9: texture/model references (missing / outside-folder guards, install copies)")
    import contextlib
    import dataclasses
    import io
    import tempfile

    try:
        proj = p.new_project(root_children=[
            p.sprite_node("Tex.png", sprite_block=p.sprite(),
                          renderer_common=p.renderer_common(color_texture="Texture/a.png")),
            p.model_node("M", model_block=p.model(model_path="Model/m.efkmodel")),
            p.sprite_node("NoTex", sprite_block=p.sprite(), renderer_common=p.renderer_common()),
        ])
        got = sorted((e.tag, e.text) for e in assets.project_asset_elems(proj))
        if got != [("ColorTexture", "Texture/a.png"), ("Model", "Model/m.efkmodel")]:
            raise AssertionError(f"project_asset_elems() = {got!r}")
        if [assets.escapes(s) for s in ("Texture/a.png", "../x.png", "a/../../x.png", "C:/x.png", "a/../x.png")] \
                != [False, True, True, True, False]:
            raise AssertionError("escapes() misclassified a path")
        r.ok("project_asset_elems() finds ColorTexture/Model (not <Name>), escapes() spots ../ and absolute paths")
    except Exception:  # noqa: BLE001
        r.fail("assets helpers", traceback.format_exc())

    try:
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp) / "work"
            work.mkdir()
            proj_path = work / "Fx.efkproj"
            xmlio.write(proj_path, p.new_project(root_children=[p.sprite_node(
                "N", sprite_block=p.sprite(),
                renderer_common=p.renderer_common(color_texture="Texture/missing.png"))]))
            with contextlib.redirect_stdout(io.StringIO()):
                if cli.cmd_validate(argparse.Namespace(file=str(proj_path), effekseer_version=None)) != 1:
                    raise AssertionError("validate accepted a missing texture")
            _assert_cli_error(lambda: cli.cmd_compile(argparse.Namespace(
                file=str(proj_path), out=None, cui_path=None, effekseer_version=None)),
                "missing.png", "compile with a missing texture")
            (work / "Texture").mkdir()
            (work / "Texture" / "missing.png").write_bytes(b"png")
            _assert_cli_error(lambda: cli.cmd_compile(argparse.Namespace(
                file=str(proj_path), out=str(Path(tmp) / "elsewhere" / "Fx.efkefc"), cui_path=None,
                effekseer_version=None)),
                "same folder", "compile --out into another folder")
        r.ok("validate reports and compile refuses missing textures; compile refuses --out in another folder")
    except Exception:  # noqa: BLE001
        r.fail("validate/compile asset guards", traceback.format_exc())

    try:
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            tmp_path = Path(tmp)
            effect_dir = tmp_path / "Effects"
            cfg = dataclasses.replace(CONFIG, project_root=tmp_path, effect_dir=effect_dir,
                                      effect_dir_rel="Effects", source_subdir="_Source", meta_enabled=False,
                                      runtime_version="")
            with config.override(cfg):
                work = tmp_path / "work"
                (work / "Texture").mkdir(parents=True)
                (work / "Texture" / "a.png").write_bytes(b"texture-a")
                proj_path = work / "Fx.efkproj"
                xmlio.write(proj_path, p.new_project(root_children=[p.sprite_node(
                    "N", sprite_block=p.sprite(),
                    renderer_common=p.renderer_common(color_texture="Texture/a.png"))]))
                src = work / "Fx.efkefc"
                src.write_bytes(_efkefc_with_assets(["Texture/a.png"]))
                dest = effect_dir / "Sub" / "Fx.efkefc"

                cli.cmd_install(argparse.Namespace(efkefc=str(src), project=str(proj_path), dest=str(dest)))
                if (dest.parent / "Texture" / "a.png").read_bytes() != b"texture-a":
                    raise AssertionError("install did not copy the referenced texture next to --dest")
                source_dest = effect_dir / "_Source" / "Sub" / "Fx.efkproj"
                copied = xmlio.read(source_dest)
                if assets.missing_project_assets(copied, source_dest.parent):
                    raise AssertionError("the _Source copy's texture path does not resolve")
                if [e.text for e in assets.project_asset_elems(copied)] != ["../../Sub/Texture/a.png"]:
                    raise AssertionError(f"_Source path = {[e.text for e in assets.project_asset_elems(copied)]}")
                cli.cmd_install(argparse.Namespace(efkefc=str(src), project=None, dest=str(dest)))

                (work / "Texture" / "a.png").write_bytes(b"texture-a-changed")
                _assert_cli_error(lambda: cli.cmd_install(argparse.Namespace(
                    efkefc=str(src), project=None, dest=str(dest))), "already installed", "install over a different texture")

                dest2 = effect_dir / "Other" / "Fx.efkefc"
                src.write_bytes(_efkefc_with_assets(["Texture/gone.png"]))
                _assert_cli_error(lambda: cli.cmd_install(argparse.Namespace(
                    efkefc=str(src), project=None, dest=str(dest2))), "gone.png", "install with a missing texture")
                src.write_bytes(_efkefc_with_assets(["../OneDrive/Texture/a.png"]))
                _assert_cli_error(lambda: cli.cmd_install(argparse.Namespace(
                    efkefc=str(src), project=None, dest=str(dest2))), "outside", "install with a ../ path")
                if dest2.parent.exists():
                    raise AssertionError("a refused install still wrote files")
        r.ok("install copies textures next to --dest, rebases the _Source copy, refuses missing / "
             "conflicting / outside-folder references without writing anything")
    except Exception:  # noqa: BLE001
        r.fail("install asset handling", traceback.format_exc())

    source_dir = REAL_EFFECT_DIR / CONFIG.source_subdir
    projects = sorted(source_dir.rglob("*.efkproj")) if source_dir.is_dir() else []
    if not projects:
        r.ok(f"real _Source sweep (skipped: no .efkproj under {source_dir})")
        return
    try:
        broken = []
        unreadable = []
        for path in projects:
            name = path.relative_to(source_dir).as_posix()
            try:
                proj = cli._read_project(path)
            except cli.CliError:
                unreadable.append(name)
                continue
            missing = assets.missing_project_assets(proj, path.parent)
            if missing:
                broken.append(f"{name}: {missing}")
        if broken:
            raise AssertionError("\n".join(broken))
        r.ok(f"all {len(projects) - len(unreadable)} readable real {CONFIG.source_subdir}/ .efkproj file(s) "
             "reference existing files"
             + (f" (skipped, not XML .efkproj: {', '.join(unreadable)})" if unreadable else ""))
    except Exception:  # noqa: BLE001
        r.fail("real _Source .efkproj references", traceback.format_exc())


@contextlib.contextmanager
def _without_env(*names: str):
    saved = {n: os.environ.pop(n) for n in names if n in os.environ}
    try:
        yield
    finally:
        os.environ.update(saved)


def _fake_cui(root: Path, version: str, launcher: bool) -> Path:
    """A stand-in Effekseer install whose EffekseerCore.dll carries ``version``
    the way the real ones do (a UTF-16 string among others)."""
    tool = root / "Tool"
    real_dir = tool / "bin" if launcher else tool
    real_dir.mkdir(parents=True)
    (tool / "Effekseer.exe").write_bytes(b"MZ")
    if launcher:
        (real_dir / "Effekseer.exe").write_bytes(b"MZ")
    # like the real DLLs: the editor's own version among older migration
    # thresholds, "1.0.0.0" and version-like text inside longer strings
    older = [x for x in ("1.50", "1.60α9", "1.70α2", "1.80β2")
             if versions.parse_tool_version(x) < versions.parse_tool_version(version)]
    blob = "\x00".join(("1.0.0.0", "Effekseer1.99", *older, version)).encode("utf-16-le")
    (real_dir / "EffekseerCore.dll").write_bytes(b"MZ\x00\x00" + blob + b"\x00\x00")
    return tool / "Effekseer.exe"


def stage_versions(r: Reporter) -> None:
    r.section("stage 10: Effekseer versions (ToolVersion layout rule, version/CUI resolution, INFO layouts, "
              "runtime guard)")
    import dataclasses
    import io
    import tempfile

    try:
        want = {"1.80": 180030, "1.80β2": 180012, "1.80β1": 180011, "1.80.7": 180730, "1.80.2": 180230,
                "1.7.3.0": 173030, "1.70e": 170030, "1.52j": 152030, "1.50RC1": 150021, "1.60α3": 160003,
                "0.7CTP1": 30, "": 30}
        got = {k: versions.parse_tool_version(k) for k in want}
        if got != want:
            raise AssertionError(f"parse_tool_version() = {got!r}")
        if (versions.profile_for("1.7.3.0"), versions.profile_for("1.80.2")) != (versions.PROFILE_17, versions.PROFILE_180):
            raise AssertionError("profile_for() picked the wrong profile")
        if [versions.profile_for(v).family for v in ("1.50RC1", "1.51", "1.6", "1.62e", "1.70e", "1.80.0")] \
                != ["1.5", "1.5", "1.6", "1.6", "1.7", "1.80"]:
            raise AssertionError("profile_for() families wrong")
        for bad in ("1.43", "1.90", "2.0", "x"):
            _assert_raises_value_error(lambda: versions.profile_for(bad), f"profile_for({bad!r})")
        if [versions.runtime_max_binary_version(v) for v in ("1.5", "1.6", "1.7", "1.7.3.0", "1.80", "1.80.7")] \
                != [1500, 1610, 1710, 1710, 1810, 1810]:
            raise AssertionError("runtime_max_binary_version() wrong")
        r.ok("parse_tool_version() matches Effekseer's Core.ParseVersion; profile / runtime lookups")
    except Exception:  # noqa: BLE001
        r.fail("version parsing", traceback.format_exc())

    try:
        layouts = {tv: versions.layout_of(p.new_project(tool_version=tv))
                   for tv in ("0.7CTP1", "1.7.3.0", "1.80β1", "1.80β2", "1.80", "1.80.7")}
        if layouts != {"0.7CTP1": "legacy", "1.7.3.0": "legacy", "1.80β1": "legacy", "1.80β2": "v180",
                       "1.80": "v180", "1.80.7": "v180"}:
            raise AssertionError(f"layout_of() = {layouts!r}")
        kwargs = dict(max_generation=7, generation_time={"center": 2, "max": 2, "min": 2},
                      remove_when_parent_removed=True, trigger_to_start=257, trigger_to_remove=769)
        legacy = p.common_values(layout="legacy", **kwargs)
        v180 = p.common_values(layout="v180", generation_timing=1, trigger=2,
                               trigger_count={"center": 3, "max": 3, "min": 3}, **kwargs)
        if [c.tag for c in legacy.children] != ["MaxGeneration", "RemoveWhenParentIsRemoved", "GenerationTime",
                                                "TriggerParam"]:
            raise AssertionError(f"legacy common_values(): {[c.tag for c in legacy.children]}")
        if ([c.tag for c in v180.children] != ["MaxGeneration", "Generation", "Removal"]
                or [c.tag for c in v180.require("Generation").children]
                != ["Timing", "GenerationTime", "ToStartGeneration", "Trigger", "TriggerCount"]
                or [c.tag for c in v180.require("Removal").children] != ["WhenParentIsRemoved", "TriggerToRemove"]):
            raise AssertionError(f"v180 common_values():\n{xmlio.serialize(v180)}")
        _assert_raises_value_error(lambda: p.common_values(layout="legacy", generation_timing=1),
                                   "common_values(layout='legacy', generation_timing=1)")
        _assert_raises_value_error(lambda: p.common_values(layout="1.80"), "common_values(layout='1.80')")
        n_legacy, n_v180 = p.node("N", common=legacy), p.node("N", common=v180)
        if (versions.node_migration_problems(n_legacy, "0.7CTP1") or versions.node_migration_problems(n_v180, "1.80")
                or len(versions.node_migration_problems(n_legacy, "1.80")) != 3
                or len(versions.node_migration_problems(n_v180, "1.7.3.0")) != 2):
            raise AssertionError("node_migration_problems() misjudged the CommonValues migration")
        sprite = p.sprite_node("N", sprite_block=p.sprite(color_all=p.color("ColorAll_Fixed", r=1)))
        if (versions.node_migration_problems(sprite, "1.62e")
                or len(versions.node_migration_problems(sprite, "1.70α1")) != 1):
            raise AssertionError("node_migration_problems() misjudged the 1.70α1 color migration")
        native_color = p.node("N")
        native_color.set_path("DrawingValues.ColorAll.Fixed.R", "1")
        ribbon_color = p.ribbon_node("N", ribbon_block=p.ribbon())
        ribbon_color.set_path("DrawingValues.ColorAll.Fixed.R", "1")
        if (len(versions.node_migration_problems(native_color, "0.7CTP1")) != 1
                or versions.node_migration_problems(native_color, "1.80")
                or versions.node_migration_problems(ribbon_color, "0.7CTP1")):
            raise AssertionError("native DrawingValues/ColorAll overwrite check wrong (sprites only)")
        group = p.group_node("G")
        if group.get("DrawingValues.Type").text != "0" or cli._drawing_kind(group) is not None \
                or cli._drawing_kind(p.node("N")) != "sprite":
            raise AssertionError("group_node() must draw nothing; a node without DrawingValues is a Sprite")
        new_file = p.new_project(tool_version="1.80")
        if (versions.too_new_problem(new_file, "1.7.3.0") is None or versions.too_new_problem(new_file, "1.80.2")
                or versions.too_new_problem(p.new_project(tool_version="1.80.7"), "1.80.2") is None):
            raise AssertionError("too_new_problem() wrong")
        n_gpu = p.node("N", common=p.common_values(layout="legacy", trigger_to_start=1))
        n_gpu.set_path("GpuParticles.Enabled", "True")
        if ([len(versions.node_unsupported_blocks(n_gpu, prof)) for prof in versions.PROFILES] != [2, 2, 1, 0]):
            raise AssertionError("node_unsupported_blocks() wrong")
        r.ok("layout_of() follows ToolVersion (>= 1.80β2 -> v180); common_values() writes each layout; "
             "migration / too-new / newer-family-block checks; group_node() draws nothing")
    except Exception:  # noqa: BLE001
        r.fail("CommonValues layout rule", traceback.format_exc())

    try:
        with tempfile.TemporaryDirectory() as tmp, _without_env("EFFEKSEER_VERSION", "EFFEKSEER_CUI"), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            tmp_path = Path(tmp)
            cui17 = _fake_cui(tmp_path / "E173", "1.7.3.0", launcher=False)
            cui180 = _fake_cui(tmp_path / "E1807", "1.80.7", launcher=True)
            base = dataclasses.replace(CONFIG, version="1.7.3.0", cui_path=None,
                                       cui_paths={"1.7.3.0": cui17, "1.80.7": cui180})
            with config.override(base):
                eff = cli.resolve_effekseer(None, None)
                if (eff.version, eff.cui, eff.detected, eff.profile) != ("1.7.3.0", cui17, "1.7.3.0", versions.PROFILE_17):
                    raise AssertionError(f"default resolution: {eff!r}")
                eff = cli.resolve_effekseer(None, "1.80.7")
                if (eff.cui, eff.detected, eff.profile) != (cui180, "1.80.7", versions.PROFILE_180):
                    raise AssertionError(f"--effekseer-version 1.80.7: {eff!r}")
                if versions.resolve_cui_exe(cui180) != cui180.parent / "bin" / "Effekseer.exe":
                    raise AssertionError("1.80 launcher not resolved to Tool/bin/Effekseer.exe")
                os.environ["EFFEKSEER_VERSION"] = "1.80.2"
                eff = cli.resolve_effekseer(None, None)
                del os.environ["EFFEKSEER_VERSION"]
                if (eff.version, eff.cui) != ("1.80.2", cui180):
                    raise AssertionError(f"$EFFEKSEER_VERSION=1.80.2 should fall back to the 1.80.7 CUI: {eff!r}")

                work = tmp_path / "work"
                work.mkdir()
                proj17 = work / "Fx17.efkproj"
                xmlio.write(proj17, p.new_project())
                _assert_cli_error(lambda: cli.cmd_compile(argparse.Namespace(
                    file=str(proj17), out=None, cui_path=str(cui17), effekseer_version="1.80.7")),
                    "is Effekseer 1.7.3.0", "compile with a 1.7.3.0 CUI for target 1.80.7")
                proj180 = work / "Fx180.efkproj"
                xmlio.write(proj180, p.new_project(tool_version="1.80"))
                _assert_cli_error(lambda: cli.cmd_compile(argparse.Namespace(
                    file=str(proj180), out=None, cui_path=None, effekseer_version=None)),
                    "newer than Effekseer 1.7.3.0", "compile a ToolVersion 1.80 file with 1.7.3.0")
                bad180 = p.new_project(tool_version="1.80", root_children=[
                    p.node("N", common=p.common_values(layout="legacy", remove_when_parent_removed=True))])
                xmlio.write(proj180, bad180)
                _assert_cli_error(lambda: cli.cmd_compile(argparse.Namespace(
                    file=str(proj180), out=None, cui_path=None, effekseer_version="1.80.7")),
                    "RemoveWhenParentIsRemoved", "compile legacy CommonValues in a ToolVersion 1.80 file")
                if list(work.glob("*.efkefc")):
                    raise AssertionError("a refused compile produced output")

            for fake, want in (("1.62e", "1.62e"), ("1.51", "1.51"), ("1.6", "1.6")):
                exe = _fake_cui(tmp_path / f"E{fake}", fake, launcher=False)
                got = versions.detect_cui_version(exe)
                if got != want:
                    raise AssertionError(f"detect_cui_version() on a {fake} DLL = {got!r}")
            with config.override(dataclasses.replace(base, version="", cui_paths={"1.80.7": cui180})):
                eff = cli.resolve_effekseer(None, None)
                if (eff.version, eff.profile) != ("1.80.7", versions.PROFILE_180):
                    raise AssertionError(f"version not detected from the only CUI: {eff!r}")
            with config.override(dataclasses.replace(base, version="", cui_paths={})):
                eff = cli.resolve_effekseer(None, None)
                if (eff.version, eff.cui) != (versions.FALLBACK_VERSION, None):
                    raise AssertionError(f"fallback resolution: {eff!r}")
        r.ok("resolve_effekseer(): version from flag/env/config/CUI/fallback, cui_paths per version, CUI "
             "version detection; compile refuses a mismatched CUI, a too-new ToolVersion and dropped fields")
    except Exception:  # noqa: BLE001
        r.fail("version / CUI resolution", traceback.format_exc())

    try:
        with tempfile.TemporaryDirectory() as tmp, _without_env("EFFEKSEER_VERSION"), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            v180_path = Path(tmp) / "v180.efkproj"
            xmlio.write(v180_path, p.new_project(tool_version="1.80"))
            cli.cmd_add_node(_add_node_args(v180_path, generation_timing="trigger", trigger="parent-collided",
                                            trigger_count="3:5:7", trigger_to_remove="trigger2",
                                            billboard="4", effekseer_version="1.80.7"))
            common = xmlio.read(v180_path).get("Root.Children.Node.CommonValues")
            if (common.get("Generation.Timing").text, common.get("Generation.Trigger").text,
                    common.get("Generation.TriggerCount.Max").text, common.get("Removal.TriggerToRemove").text) \
                    != ("1", "3", "7", "513"):
                raise AssertionError(f"add-node on a 1.80 file wrote:\n{xmlio.serialize(common)}")
            before = v180_path.read_bytes()
            _assert_cli_error(lambda: cli.cmd_set_params(argparse.Namespace(
                file=str(v180_path), path="0", set=["CommonValues.GenerationTime.Center=2"],
                effekseer_version="1.80.7")), "GenerationTime", "set-params legacy field on a 1.80 file")
            _assert_cli_error(lambda: cli.cmd_add_node(_add_node_args(v180_path, billboard="4",
                                                                      effekseer_version="1.7.3.0")),
                              "Billboard=4", "add-node Billboard=4 targeting 1.7.3.0")
            legacy_path = Path(tmp) / "legacy.efkproj"
            xmlio.write(legacy_path, p.new_project())
            legacy_before = legacy_path.read_bytes()
            _assert_cli_error(lambda: cli.cmd_add_node(_add_node_args(legacy_path, generation_timing="trigger",
                                                                      effekseer_version="1.80.7")),
                              "ToolVersion", "add-node --generation-timing on a legacy file")
            if v180_path.read_bytes() != before or legacy_path.read_bytes() != legacy_before:
                raise AssertionError("a refused write modified the file")
            cli.cmd_add_node(_add_node_args(legacy_path, trigger_to_start="trigger1", generation_time="2",
                                            effekseer_version="1.7.3.0"))
            common = xmlio.read(legacy_path).get("Root.Children.Node.CommonValues")
            if (common.get("TriggerParam.ToStartGeneration").text, common.get("GenerationTime.Center").text) != ("257", "2"):
                raise AssertionError(f"add-node on a legacy file wrote:\n{xmlio.serialize(common)}")
        r.ok("add-node/set-params write the file's own CommonValues layout and refuse the other one / "
             "enum values the target version lacks, file untouched")
    except Exception:  # noqa: BLE001
        r.fail("CLI layout-aware writes", traceback.format_exc())

    try:
        paths = ["Texture/a.png", "Model/m.efkmodel", "Sound/s.wav"]
        for version in (1500, 1610, 1710, 1810):
            data = _efkefc_bytes(version, paths)
            if efkefc.parse_asset_paths(data) != paths or efkefc.info_version(data) != version \
                    or efkefc.bin_version(data) != version:
                raise AssertionError(f"INFO layout for version {version} not parsed")
        garbled = _efkefc_bytes(1710, paths)
        garbled = garbled.replace(b"SKFE", b"SKFX")
        try:
            efkefc.bin_version(garbled)
        except efkefc.EfkefcError:
            pass
        else:
            raise AssertionError("bin_version() accepted a BIN_ chunk without SKFE")
        import struct
        i = garbled.find(b"INFO") + 12
        garbled = garbled[:i] + struct.pack("<i", 99) + garbled[i + 4:]  # dependency count
        try:
            efkefc.parse_asset_paths(garbled)
        except efkefc.EfkefcError:
            pass
        else:
            raise AssertionError("parse_asset_paths() accepted a broken dependency list")
        if efkefc.asset_paths(garbled) != paths:
            raise AssertionError(f"asset_paths() fallback = {efkefc.asset_paths(garbled)!r}")
        real = [(REAL_EFFECT_DIR / "tktk01" / "fireSpark.efkefc", 1710),
                (REAL_EFFECT_DIR / "NitoriBox" / "Explosion.efkefc", 1810),
                (REAL_EFFECT_DIR / "Laser01.efkefc", 1500)]
        present = [(f, v) for f, v in real if f.exists()]
        for f, version in present:
            data = f.read_bytes()
            if efkefc.info_version(data) != version or not efkefc.parse_asset_paths(data):
                raise AssertionError(f"{f.name}: INFO version {efkefc.info_version(data)}, "
                                     f"assets {efkefc.asset_paths(data)!r}")
            efkefc.edit_project(data)
        r.ok(f"INFO chunk: string lists (<=1610) and dependency list (1710/1810) parse strictly, broken ones "
             f"fall back; {len(present)} real shipped .efkefc (1500/1710/1810) parse strictly + EDIT decodes")
    except Exception:  # noqa: BLE001
        r.fail("efkefc INFO/EDIT parsing", traceback.format_exc())

    try:
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            cfg = dataclasses.replace(CONFIG, meta_enabled=False, runtime_version="1.7")
            with config.override(cfg):
                src = Path(tmp) / "fx.efkefc"
                dest = Path(tmp) / "out" / "fx.efkefc"
                src.write_bytes(_efkefc_bytes(1810, []))
                _assert_cli_error(lambda: cli.cmd_install(argparse.Namespace(efkefc=str(src), project=None,
                                                                             dest=str(dest))),
                                  "runtime_version", "install a 1810 effect for runtime 1.7")
                if dest.parent.exists():
                    raise AssertionError("a refused install wrote files")
                src.write_bytes(_efkefc_bytes(1710, []))
                cli.cmd_install(argparse.Namespace(efkefc=str(src), project=None, dest=str(dest)))
                if not dest.is_file():
                    raise AssertionError("install of a 1710 effect for runtime 1.7 did not copy it")
        r.ok("install refuses an effect newer than project.runtime_version, accepts one it loads")
    except Exception:  # noqa: BLE001
        r.fail("install runtime_version guard", traceback.format_exc())


def _canonical(e: Elem) -> str:
    """``e`` serialized with sibling order ignored except under ``<Children>``
    (Effekseer reads elements by name; 1.5x editors keep migrated elements
    where the migration appended them)."""
    def canon(x: Elem) -> Elem:
        kids = [canon(c) for c in x.children]
        if x.tag != "Children":
            kids.sort(key=lambda c: c.tag)
        return Elem(x.tag, x.text, kids)
    return xmlio.serialize(canon(e))


def _compile_edit(cui: Path, profile: versions.Profile, proj: Elem, work: Path, name: str) -> Elem:
    in_path = work / f"{name}.efkproj"
    out = work / f"{name}.efkefc"
    xmlio.write(in_path, proj)
    _compile_check(cui, profile, in_path, out)
    return efkefc.edit_project(out.read_bytes())


def _migration_trees() -> dict[str, list[Elem]]:
    """Presets output covering every block the toolkit builds, for the
    ToolVersion sweep in stage 11."""
    return {
        "ring": [p.ring_node("Node", ring_block=p.ring(
            vertex_count=36, outer=p.xyz("Location", x=1.8), inner=p.xyz("Location", x=0.2), center_ratio=0.8,
            outer_color=p.color("OuterColor_Fixed", r=10, g=20, b=30),
            center_color_random=p.random_color("CenterColor_Random", a={"center": 200, "max": 255, "min": 150})))],
        "sprite_fixed_color": [p.sprite_node("Node", sprite_block=p.sprite(
            billboard=1, color_all=p.color("ColorAll_Fixed", r=255, g=200, b=100, a=128)))],
        "sprite_easing_color": [p.sprite_node("Node", sprite_block=p.sprite(color_all_easing=p.easing(
            "ColorAll_Easing", start=p.random_color("Start", r={"center": 255, "max": 255, "min": 255}),
            end=p.random_color("End", r={"center": 0, "max": 0, "min": 0}))))],
        "sprite_corners": [p.sprite_node("Node", sprite_block=p.sprite(
            rendering_order=1, position_corners={"ll": {"x": -0.5, "y": 0}, "ur": {"x": 0.5, "y": 1}},
            color_corners={"ll": {"r": 255, "g": 0, "b": 0}}))],
        "ribbon": [p.ribbon_node("Node", ribbon_block=p.ribbon(
            viewpoint_dependent=False,
            color_all_random=p.random_color("ColorAll_Random", r={"center": 127, "max": 255, "min": 0})))],
        "model": [p.model_node("Node", model_block=p.model(
            model_path="Model/rock.efkmodel", lighting=True,
            color_fixed=p.color("Color_Fixed", r=24, g=16, b=32)),
            renderer_common=p.renderer_common(color_texture="Texture/t.png"))],
        "model_without_renderer_common": [p.model_node("Node", model_block=p.model(
            model_path="Model/rock.efkmodel", lighting=True))],
        "track": [p.track_node("Node", track_block=p.track(color_left=p.color("ColorLeft_Fixed", a=0)))],
        "location_abs": [p.node("Node", location_abs=p.location_abs_values(gravity={"x": 0, "y": -0.01, "z": 0})),
                         p.node("Node", location_abs=p.location_abs_values(attractive_force=0.025))],
        "sound_generation": [p.node(
            "Node", sound=p.sound_values(wave="Sound/x.wav", volume={"center": 0.5, "max": 0.5, "min": 0.5}),
            generation_location=p.generation_location_circle(division=8, radius={"center": 2, "max": 2, "min": 2}))],
        "transforms": [p.node(
            "Node", location=p.location_values(velocity=p.xyz("Velocity", x=p.pva("X", center=1, max=2, min=0))),
            rotation=p.rotation_values(axis_pva=p.axis_pva(
                axis=p.xyz("Axis", z=p.pva("Z", center=1, max=1, min=1)), rotation={"center": 0, "max": 180, "min": -180})),
            scaling=p.scaling_values(single_pva={"center": 2, "max": 3, "min": 1}),
            common=p.common_values(layout="legacy", location_effect_type=1, max_generation=5,
                                   life={"center": 30, "max": 40, "min": 20}))],
        "common_legacy": [p.node("Node", common=p.common_values(
            layout="legacy", generation_time={"center": 2, "max": 2, "min": 2}, remove_when_parent_removed=True))],
        "distortion": [p.sprite_node("Node", sprite_block=p.sprite(), renderer_common=p.renderer_common(
            color_texture="Texture/t.png", alpha_blend=2, distortion=True, distortion_intensity=0.3,
            fade_in={"frame": 4, "start_speed": 10, "end_speed": 0}))],
        "uv_animation": [p.sprite_node("Node", sprite_block=p.sprite(), renderer_common=p.renderer_common(
            uv_animation={"size": {"x": 64, "y": 64}, "frame_length": 2, "frame_count_x": 4, "frame_count_y": 4}))],
        "group": [p.group_node("G", children=[p.sprite_node("Node", sprite_block=p.sprite())])],
    }


# Ribbon/Track smoothing is a *behaviour* the 1.70α1 migration pins for old
# files (TrailSmoothing/TrailTimeSource), not a toolkit field that gets lost.
_BEHAVIOUR_ONLY_TAGS = ("<TrailSmoothing>", "<TrailTimeSource>")


def stage_ground_truth(r: Reporter) -> None:
    r.section("stage 11: ground truth via the EDIT chunk, per Effekseer CUI (best-effort, machine-specific)")
    cuis = available_cuis()
    if not cuis:
        r.ok("skipped: no Effekseer CUI found (add them to effekseer.cui_paths)")
        return
    for version, cui, profile in cuis:
        check_cui_ground_truth(r, version, cui, profile, True)


def check_cui_ground_truth(r: Reporter, version: str, cui: Path, profile: versions.Profile, migrations: bool) -> None:
    """Compile presets-built trees with one CUI and decode the EDIT chunk:
    ``migrations`` = every migration that editor knows is caught by
    versions.MIGRATIONS (slow: one compile per tree x threshold); for 1.80,
    the v180 CommonValues layout; for all, ``upgrade`` round trips."""
    tag = f"[Effekseer {version}]"
    import argparse
    import contextlib
    import io
    import tempfile
    shared = dict(max_generation=7, life={"center": 30, "max": 40, "min": 20},
                  generation_time={"center": 2.5, "max": 3, "min": 2},
                  generation_time_offset={"center": 4, "max": 4, "min": 4},
                  remove_when_life_extinct=False, remove_when_parent_removed=True,
                  remove_when_all_children_removed=True)
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        for sub in ("Texture", "Model", "Sound"):
            (work / sub).mkdir()
        (work / "Texture" / "t.png").write_bytes(b"png")
        (work / "Model" / "rock.efkmodel").write_bytes(b"model")
        (work / "Sound" / "x.wav").write_bytes(b"wav")

        known = [m for m in versions.MIGRATIONS
                 if versions.parse_tool_version(m.skipped_from) <= versions.parse_tool_version(version)]
        try:
            if not migrations:
                raise _Skip()
            missed, flagged_same = [], []
            checked = 0
            for name, nodes in _migration_trees().items():
                def root_text(tool_version: str) -> str:
                    proj = p.new_project(root_children=[n.clone() for n in nodes], tool_version=tool_version)
                    edit = _compile_edit(cui, profile, proj, work, f"{name}_{abs(hash(tool_version))}")
                    return "\n".join(line for line in _canonical(edit.require("Root")).splitlines()
                                     if not line.strip().startswith(_BEHAVIOUR_ONLY_TAGS))
                baseline = root_text(versions.LEGACY_TOOL_VERSION)
                for m in known:
                    tool_version = m.skipped_from
                    proj = p.new_project(root_children=[n.clone() for n in nodes], tool_version=tool_version)
                    flagged = versions.project_migration_problems(proj)
                    lost = root_text(tool_version) != baseline
                    checked += 1
                    if lost and not flagged:
                        missed.append(f"{name} @ ToolVersion {tool_version}")
                    if flagged and not lost:
                        flagged_same.append(f"{name} @ ToolVersion {tool_version}: {flagged[0]}")
            if missed or flagged_same:
                raise AssertionError("values Effekseer drops that versions.MIGRATIONS doesn't catch:\n  "
                                     + "\n  ".join(missed) + "\nflagged although nothing changed:\n  "
                                     + "\n  ".join(flagged_same))
            r.ok(f"{tag} every presets value Effekseer drops under a newer ToolVersion is caught by "
                 f"versions.MIGRATIONS, nothing else is ({len(known)} threshold(s), {checked} compiles vs 0.7CTP1)")
        except _Skip:
            pass
        except Exception:  # noqa: BLE001
            r.fail(f"{tag} versions.MIGRATIONS completeness", traceback.format_exc())

        if profile is not versions.PROFILE_180:
            _check_upgrade(r, tag, version, cui, profile, work)
            return

        try:
            legacy_kwargs = dict(shared, trigger_to_start=257, trigger_to_stop=513, trigger_to_remove=769)
            proj = p.new_project(root_children=[p.sprite_node(
                "N", sprite_block=p.sprite(), common=p.common_values(layout="legacy", **legacy_kwargs))])
            edit = _compile_edit(cui, profile, proj, work, "legacy")
            got = xmlio.serialize(edit.get("Root.Children.Node.CommonValues"))
            want = xmlio.serialize(p.common_values(layout="v180", **legacy_kwargs))
            if got != want:
                raise AssertionError(f"1.80 migrated the legacy layout to\n{got}\nbut v180 common_values() "
                                     f"builds\n{want}")
            r.ok(f"{tag} migrates presets' legacy CommonValues into exactly what common_values(layout='v180') "
                 "builds from the same arguments")
        except Exception:  # noqa: BLE001
            r.fail(f"{tag} legacy -> v180 CommonValues migration", traceback.format_exc())

        try:
            v180_kwargs = dict(shared, generation_timing=1, trigger=3, trigger_count={"center": 5, "max": 7, "min": 3},
                               trigger_to_start=2, trigger_to_stop=769, trigger_to_remove=513)
            node = p.sprite_node("N", sprite_block=p.sprite(billboard=4),
                                 renderer_common=p.renderer_common(wrap=2),
                                 common=p.common_values(layout="v180", **v180_kwargs))
            node.set_path("RotationValues.Type", "7")
            node.set_path("RotationValues.Velocity.Axis", "3")
            proj = p.new_project(root_children=[node], tool_version="1.80")
            if enums.check_project(proj, profile) or versions.project_migration_problems(proj):
                raise AssertionError("the tree under test fails the toolkit's own checks")
            edit = _compile_edit(cui, profile, proj, work, "v180")
            got = xmlio.serialize(edit.get("Root.Children.Node.CommonValues"))
            want = xmlio.serialize(p.common_values(layout="v180", **v180_kwargs))
            if got != want:
                raise AssertionError(f"1.80 read the v180 layout back as\n{got}\nexpected\n{want}")
            kept = {path: (edit.get(f"Root.Children.Node.{path}").text
                           if edit.get(f"Root.Children.Node.{path}") is not None else None)
                    for path in ("DrawingValues.Sprite.Billboard", "RendererCommonValues.Wrap",
                                 "RotationValues.Type", "RotationValues.Velocity.Axis")}
            if kept != {"DrawingValues.Sprite.Billboard": "4", "RendererCommonValues.Wrap": "2",
                        "RotationValues.Type": "7", "RotationValues.Velocity.Axis": "3"}:
                raise AssertionError(f"1.80-only values after compile: {kept!r}")
            r.ok(f"{tag} reads ToolVersion 1.80 + v180 CommonValues (triggers, timing, counts) as written; "
                 "Billboard=4 / Wrap=2 / RotateToVelocity survive")
        except Exception:  # noqa: BLE001
            r.fail(f"{tag} v180 layout round trip", traceback.format_exc())

        _check_upgrade(r, tag, version, cui, profile, work)


class _Skip(Exception):
    pass


def _check_upgrade(r: Reporter, tag: str, version: str, cui: Path, profile: versions.Profile, work: Path) -> None:
    import argparse
    import contextlib
    import io
    try:
        nodes = [n for tree in _migration_trees().values() for n in tree]
        src = work / "upgrade_me.efkproj"
        xmlio.write(src, p.new_project(root_children=nodes))
        before = _compile_edit(cui, profile, xmlio.read(src), work, "upgrade_before")
        args = argparse.Namespace(file=str(src), out=None, cui_path=str(cui), effekseer_version=version)
        with contextlib.redirect_stdout(io.StringIO()):
            cli.cmd_upgrade(args)
        upgraded = xmlio.read(src)
        upgraded_tv = versions.tool_version_of(upgraded)
        if not versions.same_family(upgraded_tv, version) or                 versions.layout_of(upgraded) != ("v180" if profile is versions.PROFILE_180 else "legacy"):
            raise AssertionError(f"upgraded ToolVersion {upgraded_tv!r}")
        if versions.project_migration_problems(upgraded) or list(work.glob(".upgrade_me.upgrade.efkefc")):
            raise AssertionError("upgraded file has migration problems / scratch file left behind")
        after = _compile_edit(cui, profile, upgraded, work, "upgrade_after")
        if _canonical(after.require("Root")) != _canonical(before.require("Root")):
            raise AssertionError("the upgraded file compiles to a different project than the original")
        r.ok(f"{tag} `upgrade` rewrites a presets-built legacy file natively (ToolVersion {upgraded_tv}) and it "
             "compiles to the identical project")
    except Exception:  # noqa: BLE001
        r.fail(f"{tag} upgrade", traceback.format_exc())


def main() -> int:
    r = Reporter()
    stage_formatting(r)
    stage_presets_roundtrip(r)
    stage_meta_roundtrip(r)
    stage_content_path_convention(r)
    stage_cui_compile(r)
    stage_enum_domains(r)
    stage_corpus_sweep(r)
    stage_config_and_export(r)
    stage_asset_references(r)
    stage_versions(r)
    stage_ground_truth(r)
    return r.finish()


if __name__ == "__main__":
    raise SystemExit(main())
