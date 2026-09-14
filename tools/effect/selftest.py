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
  5. best-effort CUI compile: only runs if the Effekseer CUI configured in
     effect_config.json (or $EFFEKSEER_CUI) is present on this machine;
     compiles a fixture and a presets-built tree, checks exit 0 + EFKE/INFO
     header. Skipped elsewhere.
  6. Effekseer enum domains (enums.py): out-of-range easing speeds are
     rejected at build time and by `validate`, pva() per-axis blocks come out
     with the capitalised <Center>/<Max>/<Min> Effekseer actually reads, and
     `install` keeps an existing asset's GUID.
  7. best-effort corpus sweep: every real .efkproj under $EFFEKSEER_CORPUS
     (default: selftest.corpus_dir in effect_config.json) must produce zero
     enum-domain violations - the false-positive guard for enums.py's table.
  8. effect_config.json loading (defaults, relative paths, JSON errors,
     meta.enabled=false install) and `export` (manifest complete, no
     user-profile paths, distributed config has no CUI path).
  9. texture/model references: validate/compile refuse missing files and
     --out in another folder; install copies referenced files next to --dest,
     rebases the --project copy, refuses missing / conflicting / ../ refs; every
     real _Source/ .efkproj resolves.

Stages 3/4 and parts of 6 read real assets under project.effect_dir and skip
when they are absent (e.g. outside NanamiEngine).
"""

from __future__ import annotations

import argparse
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

from tools.effect import assets, cli, config, enums, export, meta, presets as p, xmlio  # noqa: E402
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
# EFKE header + an INFO chunk with only a version and no asset lists.
_EMPTY_EFKEFC = b"EFKE\x00\x00\x00\x00INFO\x04\x00\x00\x00\xae\x06\x00\x00"


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
            common=p.common_values(max_generation=50,
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
                    common=p.common_values(location_effect_type=1, rotation_effect_type=1,
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


def _compile_check(cui: Path, in_path: Path, out_path: Path) -> None:
    import subprocess
    result = subprocess.run(
        [str(cui), "-cui", "-in", str(in_path), "-o", str(out_path)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise AssertionError(f"CUI exited {result.returncode}: {result.stderr[:300]}")
    if not out_path.exists():
        raise AssertionError("CUI exited 0 but produced no output file")
    header = out_path.read_bytes()[:16]
    if not header.startswith(b"EFKE") or b"INFO" not in header:
        raise AssertionError(f"output does not look like a valid .efkefc (header {header!r})")


def stage_cui_compile(r: Reporter) -> None:
    r.section("stage 5: CUI compile (best-effort, machine-specific)")
    cui = cli.find_cui(None)
    if cui is None:
        r.ok(f"skipped: no Effekseer CUI found (checked $EFFEKSEER_CUI and effekseer.cui_path in "
             f"{CONFIG.config_path.name})")
        return

    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        try:
            fixture = TESTDATA / "actionLines_shockwave.efkproj"
            out = tmp_path / "fixture.efkefc"
            _compile_check(cui, fixture, out)
            r.ok(f"compiled fixture {fixture.name}")
        except Exception:  # noqa: BLE001
            r.fail("compile real fixture", traceback.format_exc())

        try:
            proj = p.new_project(root_children=[
                p.ring_node("Node", ring_block=p.ring(vertex_count=36, center_ratio=0.8)),
            ])
            in_path = tmp_path / "presets_demo.efkproj"
            xmlio.write(in_path, proj)
            out = tmp_path / "presets_demo.efkefc"
            _compile_check(cui, in_path, out)
            r.ok("compiled presets-built tree")
        except Exception:  # noqa: BLE001
            r.fail("compile presets-built tree", traceback.format_exc())

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
            _compile_check(cui, in_path, out)
            r.ok("compiled Model+Track presets-built tree")
        except Exception:  # noqa: BLE001
            r.fail("compile Model+Track presets-built tree", traceback.format_exc())

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
            _compile_check(cui, in_path, out)
            r.ok("compiled ColorAll_Easing/Ring-color-mode presets-built tree")
        except Exception:  # noqa: BLE001
            r.fail("compile ColorAll_Easing/Ring-color-mode presets-built tree", traceback.format_exc())

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
                                  common=p.common_values(life={"center": 60, "max": 60, "min": 60}),
                                  renderer_common=renderer)
            proj = p.new_project(root_children=[node])
            in_path = tmp_path / "sprite_texture_demo.efkproj"
            xmlio.write(in_path, proj)
            out = tmp_path / "sprite_texture_demo.efkefc"
            _compile_check(cui, in_path, out)
            compiled_text = out.read_bytes().decode("utf-16-le", errors="ignore")
            if "selftestRegressionTex" not in compiled_text:
                raise AssertionError(
                    "Sprite node's ColorTexture did not survive CUI compile - "
                    "DRAWING_TYPE['sprite'] regressed back to node-type 0 (\"none\")?"
                )
            got = cli.efkefc_asset_paths(out)
            if got != ["Texture/selftestRegressionTex.png"]:
                raise AssertionError(f"efkefc_asset_paths() = {got!r}, expected the one ColorTexture")
            r.ok("Sprite node's ColorTexture survives CUI compile (and efkefc_asset_paths() reads it back)")
        except Exception:  # noqa: BLE001
            r.fail("sprite texture reaches compiled INFO chunk", traceback.format_exc())


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
            problems = enums.check_project(xmlio.read(TESTDATA / f"{name}.efkproj"))
            if problems:
                raise AssertionError(f"false positive(s) in real fixture {name}: {problems[:3]}")
        node = p.sprite_node("Node", sprite_block=p.sprite(),
                             renderer_common=p.renderer_common(fade_out={"frame": 4}))
        node.set_path("RendererCommonValues.FadeOut.EndSpeed", "-90")
        node.set_path("DrawingValues.Sprite.Billboard", "7")
        node.set_path("CommonValues.MaxGeneration.Value", "-90")  # plain int, not an enum: must not be flagged
        problems = enums.check_node(node)
        if len(problems) != 2 or "EndSpeed=-90" not in problems[0] or "Billboard=7" not in problems[1]:
            raise AssertionError(f"check_node() = {problems!r}, expected exactly the EndSpeed and Billboard hits")
        proj = p.new_project(root_children=[p.group_node("G", children=[node])])
        got = enums.check_project(proj)
        if len(got) != 2 or not got[0].startswith("[0.0] Node:"):
            raise AssertionError(f"check_project() = {got!r}")
        r.ok("enums.check_node()/check_project(): 0 hits on 7 real fixtures, 2 on a doctored node")
    except Exception:  # noqa: BLE001
        r.fail("enums.check_node()/check_project()", traceback.format_exc())

    try:
        # CLI paths refuse to *write* a violating node (apply stays atomic).
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            proj_path = Path(tmp) / "t.efkproj"
            xmlio.write(proj_path, p.new_project())
            before = proj_path.read_bytes()
            ns = argparse.Namespace(file=str(proj_path), parent="", kind="sprite", name="N",
                                    life=None, max_generation=None, infinite=None,
                                    color_texture=None, fade_in=None, fade_out=None, uv_scroll=None,
                                    generation_shape=None, radius=None, division=None,
                                    angle_start=None, angle_end=None, billboard=None, color=None,
                                    color_random=None, model=None, lighting=None, track_color=None,
                                    set=["RendererCommonValues.FadeOut.EndSpeed=-90"])
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
                cli.cmd_apply(argparse.Namespace(file=str(proj_path), ops=str(ops)))
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
                config.override(dataclasses.replace(CONFIG, meta_enabled=True)):
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


def stage_corpus_sweep(r: Reporter) -> None:
    r.section("stage 7: enum-domain sweep over the real sample corpus (best-effort, machine-specific)")
    corpus_spec = os.environ.get("EFFEKSEER_CORPUS") or DEFAULT_CORPUS_DIR
    corpus = Path(corpus_spec) if corpus_spec else None
    files = sorted(corpus.rglob("*.efkproj")) if corpus and corpus.is_dir() else []
    if not files:
        r.ok(f"skipped: no corpus at {corpus or '(not set)'} "
             "(set selftest.corpus_dir in effect_config.json or $EFFEKSEER_CORPUS)")
        return
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
        for msg in enums.check_project(proj):
            hits.append(f"{path.relative_to(corpus).as_posix()}: {msg}")
    if hits:
        r.fail("enum-domain false positives in real corpus",
               "\n".join(hits[:20]) + (f"\n... {len(hits)} total" if len(hits) > 20 else ""))
    else:
        r.ok(f"0 enum-domain hits across {swept} real .efkproj file(s)"
             + (f" ({len(unreadable)} unreadable, skipped)" if unreadable else ""))


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
                "verified_version": "1.7.3.0",
            }
            got = {k: getattr(cfg, k) for k in want}
            if got != want:
                raise AssertionError(f"config.load() = {got!r}, expected {want!r}")

            abs_cui = tmp_path / "abs" / "Effekseer.exe"
            cfg_path.write_text(json.dumps({"effekseer": {"cui_path": abs_cui.as_posix()}}), encoding="utf-8")
            if config.load(cfg_path).cui_path != abs_cui:
                raise AssertionError("absolute cui_path was not kept as-is")
        r.ok("config.load(): defaults for missing keys, relative paths resolve against project.root")
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
        r.ok("config.load(): single-backslash JSON, wrong type and missing file raise ConfigError")
    except Exception:  # noqa: BLE001
        r.fail("config.load() errors", traceback.format_exc())

    try:
        with tempfile.TemporaryDirectory() as tmp, \
                config.override(dataclasses.replace(CONFIG, meta_enabled=False)):
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
            if dist_cfg.cui_path is not None or dist_cfg.meta_enabled or dist_cfg.corpus_dir is not None:
                raise AssertionError(f"distributed effect_config.json is not neutral: {dist_cfg!r}")
            if dist_cfg.project_root != out.resolve():
                raise AssertionError(f"distributed project root = {dist_cfg.project_root}, expected {out}")
        r.ok(f"export writes all {len(export.MANIFEST)} manifest files, no personal paths, neutral config")
    except Exception:  # noqa: BLE001
        r.fail("export", traceback.format_exc())


def _efkefc_with_assets(paths: list[str]) -> bytes:
    """A minimal .efkefc whose INFO chunk lists ``paths`` (one string list)."""
    import struct
    chunk = struct.pack("<ii", 1, len(paths))
    for s in paths:
        chunk += struct.pack("<i", len(s) + 1) + (s + "\x00").encode("utf-16-le")
    return b"EFKE\x00\x00\x00\x00INFO" + struct.pack("<i", len(chunk)) + chunk


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
                if cli.cmd_validate(argparse.Namespace(file=str(proj_path))) != 1:
                    raise AssertionError("validate accepted a missing texture")
            _assert_cli_error(lambda: cli.cmd_compile(argparse.Namespace(
                file=str(proj_path), out=None, cui_path=None)), "missing.png", "compile with a missing texture")
            (work / "Texture").mkdir()
            (work / "Texture" / "missing.png").write_bytes(b"png")
            _assert_cli_error(lambda: cli.cmd_compile(argparse.Namespace(
                file=str(proj_path), out=str(Path(tmp) / "elsewhere" / "Fx.efkefc"), cui_path=None)),
                "same folder", "compile --out into another folder")
        r.ok("validate reports and compile refuses missing textures; compile refuses --out in another folder")
    except Exception:  # noqa: BLE001
        r.fail("validate/compile asset guards", traceback.format_exc())

    try:
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            tmp_path = Path(tmp)
            effect_dir = tmp_path / "Effects"
            cfg = dataclasses.replace(CONFIG, project_root=tmp_path, effect_dir=effect_dir,
                                      effect_dir_rel="Effects", source_subdir="_Source", meta_enabled=False)
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
    return r.finish()


if __name__ == "__main__":
    raise SystemExit(main())
