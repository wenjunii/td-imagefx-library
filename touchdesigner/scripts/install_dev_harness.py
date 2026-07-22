"""Install the compiled ImageFX core into a disposable TouchDesigner QA project.

Run this script inside a project that contains Embody/Envoy. It changes only the
live network, never saves the project, and refuses the canonical library .toe.
Executing it through Envoy makes the operation one TouchDesigner undo step.
"""

from __future__ import annotations

from pathlib import Path
import re


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CANONICAL_PROJECT = PROJECT_ROOT / "TD_ImageFX_Library.toe"
EXPECTED_HARNESS_PROJECT = (
    PROJECT_ROOT
    / "integrations"
    / "embody"
    / "local"
    / "TD_ImageFX_DevHarness.toe"
)
NUMBERED_HARNESS_NAME = re.compile(
    r"^{}\.[1-9][0-9]*\.toe$".format(re.escape(EXPECTED_HARNESS_PROJECT.stem)),
    re.IGNORECASE,
)
LIBRARY_TOX = PROJECT_ROOT / "touchdesigner" / "core" / "TDImageFXLibrary.tox"
RACK_TOX = PROJECT_ROOT / "touchdesigner" / "core" / "FxRack.tox"
PARTICLE_TOX = PROJECT_ROOT / "touchdesigner" / "core" / "ParticleRandomMove.tox"
INK_FLOW_TOX = PROJECT_ROOT / "touchdesigner" / "core" / "InkFlowFusion.tox"
GLITCH_TOX = PROJECT_ROOT / "touchdesigner" / "core" / "GlitchFusion.tox"
COLOR_ADJUSTMENT_TOX = (
    PROJECT_ROOT / "touchdesigner" / "core" / "ColorAdjustment.tox"
)
MOTION_STUDIO_TOX = PROJECT_ROOT / "touchdesigner" / "core" / "MotionStudio.tox"
REFERENCE_PARTICLE_FIELD_TOX = (
    PROJECT_ROOT / "touchdesigner" / "core" / "ReferenceParticleField.tox"
)
CALLIGRAPHIC_SHADOW_TOX = (
    PROJECT_ROOT / "touchdesigner" / "core" / "CalligraphicShadow.tox"
)
INK_ORBIT_CANVAS_TOX = (
    PROJECT_ROOT / "touchdesigner" / "core" / "InkOrbitCanvas.tox"
)
EXTENSION_ROOT = PROJECT_ROOT / "touchdesigner" / "extensions"
MANAGED_NAMES = ("td_imagefx", "imagefx_demo")
OUTPUT_PRESETS = (
    ("hd", "HD 1920 x 1080"),
    ("uhd4k", "4K UHD 3840 x 2160"),
    ("custom", "Custom"),
)
DEMO_SOURCE_SHADER = r"""
layout(location = 0) out vec4 fragColor;
uniform float uTime;
void main() {
    vec2 uv = vUV.st;
    uv = fract(uv + vec2(
        0.030 * sin(uTime * 0.70),
        0.025 * sin(uTime * 0.53)
    ));
    vec3 phase = vec3(0.0, 2.1, 4.2);
    vec3 color = 0.5 + 0.5 * cos(
        6.28318530718 * (uv.x + 0.35 * uv.y) + phase + uTime * 0.45
    );
    float checker = mod(floor(uv.x * 12.0) + floor(uv.y * 8.0), 2.0);
    color = mix(color, color.bgr, checker * 0.32);
    float ring = 1.0 - smoothstep(0.012, 0.025, abs(length(uv - 0.5) - 0.27));
    color = mix(color, vec3(1.0, 0.92, 0.35), ring * 0.85);
    float disk = 1.0 - smoothstep(0.34, 0.37, length(uv - 0.5));
    float alphaGrid = mix(0.18, 0.72, checker);
    float alpha = max(disk, alphaGrid * (1.0 - ring));
    fragColor = TDOutputSwizzle(vec4(color, alpha));
}
""".strip()
DEMO_SECONDARY_IMAGE_SHADER = r"""
layout(location = 0) out vec4 fragColor;
void main() {
    vec2 uv = clamp(vUV.st + vec2(0.018, -0.012), 0.0, 1.0);
    vec4 source = texture(sTD2DInputs[0], uv);
    float changedRegion = smoothstep(0.42, 0.58, vUV.x);
    vec3 changed = mix(source.rgb, source.gbr, 0.48);
    vec3 color = mix(source.rgb, changed, changedRegion);
    fragColor = TDOutputSwizzle(vec4(color, source.a));
}
""".strip()


def _output_resolution_expression(dimension):
    if dimension == "width":
        hd, uhd, custom = 1920, 3840, "Customwidth"
    elif dimension == "height":
        hd, uhd, custom = 1080, 2160, "Customheight"
    else:
        raise ValueError("Output dimension must be width or height")
    return (
        "{hd} if parent().par.Resolutionpreset.eval() == 'hd' else "
        "({uhd} if parent().par.Resolutionpreset.eval() == 'uhd4k' else "
        "int(parent().par.{custom}.eval()))"
    ).format(hd=hd, uhd=uhd, custom=custom)


def _project_path(folder, name):
    """Return TouchDesigner's current project as a normalized .toe path."""

    project_name = Path(str(name)).name
    if not project_name.lower().endswith(".toe"):
        project_name += ".toe"
    return (Path(str(folder)) / project_name).resolve()


def _current_project_path():
    return _project_path(project.folder, project.name)


def _validate_harness_project():
    """Require the exact ignored harness and reject numbered recovery identities."""

    current = _current_project_path()
    canonical = CANONICAL_PROJECT.resolve()
    expected = EXPECTED_HARNESS_PROJECT.resolve()
    if current == canonical:
        raise RuntimeError(
            "Refusing to install the QA harness into TD_ImageFX_Library.toe"
        )
    if current != expected:
        if current.parent == expected.parent and NUMBERED_HARNESS_NAME.fullmatch(
            current.name
        ):
            raise RuntimeError(
                "TouchDesigner is using a numbered harness identity: {}. "
                "Use File > Save Project As, replace only {}, close TouchDesigner, "
                "and reopen the unnumbered harness before installing.".format(
                    current.name,
                    expected.name,
                )
            )
        raise RuntimeError(
            "QA harness must be opened and saved as {}; current project is {}".format(
                expected,
                current,
            )
        )
    return current


def _load_single_tox(parent_comp, source):
    source = Path(source).resolve()
    if not source.is_file():
        raise FileNotFoundError(str(source))
    before = {child.id for child in parent_comp.children}
    parent_comp.loadTox(str(source))
    created = [child for child in parent_comp.children if child.id not in before]
    if len(created) != 1:
        for child in created:
            child.destroy()
        raise RuntimeError(
            "Expected one top-level component from {}".format(source)
        )
    return created[0]


def _repair_effect_shader_paths(root_comp):
    """Repair legacy absolute Pixel Shader paths after loading packaged effects."""

    repaired = 0
    pending = list(getattr(root_comp, "children", ()) or ())
    while pending:
        operator = pending.pop()
        pending.extend(list(getattr(operator, "children", ()) or ()))
        name = str(getattr(operator, "name", ""))
        if str(getattr(operator, "type", "")) != "glsl" or not name.startswith(
            "effect_glsl_"
        ):
            continue
        shader_name = "pixel_shader_" + name[len("effect_glsl_"):]
        shader_dat = operator.parent().op(shader_name)
        parameter = operator.par["pixeldat"]
        if shader_dat is None or parameter is None:
            raise RuntimeError(
                "{} is missing its portable Pixel Shader DAT".format(operator.path)
            )
        parameter.val = operator.relativePath(shader_dat)
        if parameter.eval() != shader_dat:
            raise RuntimeError(
                "{} Pixel Shader reference did not resolve".format(operator.path)
            )
        repaired += 1
    return repaired


def _repair_effect_state_paths(root_comp):
    """Repair legacy absolute Feedback TOP targets after loading components."""

    repaired = 0
    pending = list(getattr(root_comp, "children", ()) or ())
    while pending:
        operator = pending.pop()
        pending.extend(list(getattr(operator, "children", ()) or ()))
        if str(getattr(operator, "name", "")) != "history_feedback":
            continue
        target = operator.parent().op("state_target")
        parameter = operator.par["top"]
        if parameter is None or target is None:
            raise RuntimeError(
                "{} is missing its portable state target".format(operator.path)
            )
        parameter.val = operator.relativePath(target)
        if parameter.eval() != target:
            raise RuntimeError(
                "{} Feedback TOP target did not resolve".format(operator.path)
            )
        repaired += 1
    return repaired


def _sync_extension(component, class_name):
    """Load the tracked extension source into a compiled development component."""

    if component is None:
        raise RuntimeError("Cannot synchronize {} on a missing component".format(class_name))
    source = EXTENSION_ROOT / "{}.py".format(class_name)
    code_dat = component.op(class_name)
    if not source.is_file() or code_dat is None:
        raise RuntimeError("{} extension source or DAT is unavailable".format(class_name))
    code_dat.text = source.read_text(encoding="utf-8")
    parameter = component.par["reinitextensions"]
    if parameter is None:
        raise RuntimeError("{} cannot reinitialize extensions".format(component.path))
    parameter.pulse()


def _set_library_root(component, label):
    if component is None:
        raise RuntimeError("Loaded ImageFX library is missing {}".format(label))
    parameter = component.par["Rootfolder"]
    if parameter is None:
        raise RuntimeError("{} has no Rootfolder parameter".format(label))
    parameter.val = str(PROJECT_ROOT)


def _set_browser_target(browser, library):
    if browser is None:
        raise RuntimeError("Loaded ImageFX library is missing library browser")
    parameter = browser.par["Target"]
    effects = library.op("effects")
    if parameter is None or effects is None:
        raise RuntimeError("Library browser creation target is unavailable")
    # TouchDesigner can preserve the browser's former absolute relationship when
    # a nested palette component is exported and loaded again. Keep the dormant
    # constant empty and repair the active expression; a relative dormant value
    # can retain a stale warning even while the expression resolves correctly.
    parameter.val = ""
    parameter.expr = "me.op('../../effects')"
    if parameter.eval() != effects:
        raise RuntimeError("Library browser creation target did not resolve")
    browser.cook(force=True)


def install():
    """Load the library and demo into the current live project without saving."""

    harness_project = _validate_harness_project()
    project_comp = op("/project1")
    if project_comp is None:
        project_comp = root.create(baseCOMP, "project1")

    conflicts = [name for name in MANAGED_NAMES if project_comp.op(name) is not None]
    if conflicts:
        raise RuntimeError(
            "QA harness managed root already exists; use a fresh disposable project: "
            + ", ".join(conflicts)
        )

    created = []
    try:
        library = _load_single_tox(project_comp, LIBRARY_TOX)
        created.append(library)
        library.name = "td_imagefx"
        library.nodeX = -250
        library.nodeY = 100
        _set_library_root(library, "library")
        library_rack = library.op("core/fx_rack")
        _set_library_root(library_rack, "library rack")
        browser = library.op("core/fx_browser")
        _set_library_root(browser, "library browser")
        _set_browser_target(browser, library)
        updater = library.op("update_manager")
        _set_library_root(updater, "update manager")
        _sync_extension(library, "ImageFXLibraryExt")
        _sync_extension(library_rack, "FxRackExt")
        _sync_extension(browser, "ImageFXBrowserExt")
        _sync_extension(updater, "UpdaterExt")
        if browser.UpdateSelection() is None:
            raise RuntimeError("Library browser preview did not initialize")
        _repair_effect_shader_paths(library)
        _repair_effect_state_paths(library)

        demo = project_comp.create(baseCOMP, "imagefx_demo")
        created.append(demo)
        demo.nodeX = 100
        demo.nodeY = 100
        demo.color = (0.32, 0.18, 0.36)
        demo.comment = (
            "Disposable Embody/Envoy QA harness with three reference-video "
            "recreations, optional ink flow, random particles, Glitch Fusion, "
            "color adjustment, Motion Studio, and video effects"
        )
        demo_page = demo.appendCustomPage("Demo")
        demo_page.appendToggle(
            "Referenceparticlefieldenabled",
            label="Chromatic Particle Field Enabled",
        )
        demo.par.Referenceparticlefieldenabled.default = False
        demo.par.Referenceparticlefieldenabled = False
        demo_page.appendToggle(
            "Calligraphicshadowenabled",
            label="Calligraphic Shadow Enabled",
        )
        demo.par.Calligraphicshadowenabled.default = False
        demo.par.Calligraphicshadowenabled = False
        demo_page.appendToggle(
            "Inkorbitenabled",
            label="Ink Orbit Canvas Enabled",
        )
        demo.par.Inkorbitenabled.default = False
        demo.par.Inkorbitenabled = False
        demo_page.appendToggle("Inkflowenabled", label="Ink Flow Module Enabled")
        demo.par.Inkflowenabled.default = True
        demo.par.Inkflowenabled = True
        demo_page.appendToggle("Particlesenabled", label="Random Particles Enabled")
        demo.par.Particlesenabled.default = False
        demo.par.Particlesenabled = False
        demo_page.appendToggle("Glitchenabled", label="Glitch Module Enabled")
        demo.par.Glitchenabled.default = False
        demo.par.Glitchenabled = False
        demo_page.appendToggle(
            "Coloradjustmentenabled",
            label="Color Adjustment Enabled",
        )
        demo.par.Coloradjustmentenabled.default = False
        demo.par.Coloradjustmentenabled = False
        demo_page.appendToggle(
            "Motionenabled",
            label="Motion Module Enabled",
        )
        demo.par.Motionenabled.default = False
        demo.par.Motionenabled = False
        demo_page.appendToggle("Applyvideofx", label="Apply Video Effects")
        demo.par.Applyvideofx.default = True
        demo.par.Applyvideofx = True
        output_page = demo.appendCustomPage("Output")
        output_page.appendMenu("Resolutionpreset", label="Resolution Preset")
        demo.par.Resolutionpreset.menuNames = [item[0] for item in OUTPUT_PRESETS]
        demo.par.Resolutionpreset.menuLabels = [item[1] for item in OUTPUT_PRESETS]
        demo.par.Resolutionpreset.default = "hd"
        demo.par.Resolutionpreset = "hd"
        output_page.appendInt("Customwidth", label="Custom Width")
        demo.par.Customwidth.default = 1920
        demo.par.Customwidth = 1920
        demo.par.Customwidth.min = 16
        demo.par.Customwidth.max = 8192
        demo.par.Customwidth.clampMin = True
        demo.par.Customwidth.clampMax = True
        demo.par.Customwidth.enableExpr = (
            "me.par.Resolutionpreset.eval() == 'custom'"
        )
        output_page.appendInt("Customheight", label="Custom Height")
        demo.par.Customheight.default = 1080
        demo.par.Customheight = 1080
        demo.par.Customheight.min = 16
        demo.par.Customheight.max = 8192
        demo.par.Customheight.clampMin = True
        demo.par.Customheight.clampMax = True
        demo.par.Customheight.enableExpr = (
            "me.par.Resolutionpreset.eval() == 'custom'"
        )

        source_shader = demo.create(textDAT, "source_image_shader")
        source_shader.text = DEMO_SOURCE_SHADER
        source_shader.nodeX = -520
        source_shader.nodeY = 100

        source = demo.create(glslTOP, "source_image")
        source.nodeX = -300
        source.nodeY = 0
        source.par.pixeldat = source.relativePath(source_shader)
        if source.par["glslversion"] is not None:
            source.par.glslversion = "glsl460"
        if source.par["compilebehavior"] is not None:
            source.par.compilebehavior = "stalluntildone"
        if source.par["errorbehavior"] is not None:
            source.par.errorbehavior = "showerror"
        source.seq.vec.numBlocks = 1
        source.par.vec0name = "uTime"
        source.par.vec0valuex.expr = "absTime.seconds"
        if source.par["outputresolution"] is not None:
            source.par.outputresolution = "custom"
            source.par.resolutionw.expr = _output_resolution_expression("width")
            source.par.resolutionh.expr = _output_resolution_expression("height")
        source.cook(force=True)
        source_errors = list(source.errors())
        if source_errors:
            raise RuntimeError(
                "QA demo source shader failed: {}".format("; ".join(source_errors))
            )

        reference_particle_field = _load_single_tox(
            demo,
            REFERENCE_PARTICLE_FIELD_TOX,
        )
        reference_particle_field.name = "reference_particle_field"
        reference_particle_field.nodeX = -40
        reference_particle_field.nodeY = 0
        reference_particle_field.par.Enabled.expr = (
            "parent().par.Referenceparticlefieldenabled"
        )
        _repair_effect_shader_paths(reference_particle_field)
        source.outputConnectors[0].connect(
            reference_particle_field.inputConnectors[0]
        )

        calligraphic_shadow = _load_single_tox(
            demo,
            CALLIGRAPHIC_SHADOW_TOX,
        )
        calligraphic_shadow.name = "calligraphic_shadow"
        calligraphic_shadow.nodeX = 220
        calligraphic_shadow.nodeY = 0
        calligraphic_shadow.par.Enabled.expr = (
            "parent().par.Calligraphicshadowenabled"
        )
        _repair_effect_shader_paths(calligraphic_shadow)
        reference_particle_field.outputConnectors[0].connect(
            calligraphic_shadow.inputConnectors[0]
        )

        ink_orbit_canvas = _load_single_tox(demo, INK_ORBIT_CANVAS_TOX)
        ink_orbit_canvas.name = "ink_orbit_canvas"
        ink_orbit_canvas.nodeX = 480
        ink_orbit_canvas.nodeY = 0
        ink_orbit_canvas.par.Enabled.expr = "parent().par.Inkorbitenabled"
        _repair_effect_shader_paths(ink_orbit_canvas)
        calligraphic_shadow.outputConnectors[0].connect(
            ink_orbit_canvas.inputConnectors[0]
        )

        ink_flow = _load_single_tox(demo, INK_FLOW_TOX)
        ink_flow.name = "ink_flow"
        ink_flow.nodeX = 740
        ink_flow.nodeY = 0
        ink_flow.par.Enabled.expr = "parent().par.Inkflowenabled"
        _repair_effect_shader_paths(ink_flow)
        ink_orbit_canvas.outputConnectors[0].connect(ink_flow.inputConnectors[0])

        particles = _load_single_tox(demo, PARTICLE_TOX)
        particles.name = "particle_random_move"
        particles.nodeX = 1000
        particles.nodeY = 0
        particles.par.Enabled.expr = "parent().par.Particlesenabled"
        _repair_effect_shader_paths(particles)
        ink_flow.outputConnectors[0].connect(particles.inputConnectors[0])

        glitch = _load_single_tox(demo, GLITCH_TOX)
        glitch.name = "glitch_fusion"
        glitch.nodeX = 1260
        glitch.nodeY = 0
        glitch.par.Enabled.expr = "parent().par.Glitchenabled"
        _repair_effect_shader_paths(glitch)
        particles.outputConnectors[0].connect(glitch.inputConnectors[0])

        color_adjustment = _load_single_tox(demo, COLOR_ADJUSTMENT_TOX)
        color_adjustment.name = "color_adjustment"
        color_adjustment.nodeX = 1520
        color_adjustment.nodeY = 0
        color_adjustment.par.Enabled.expr = (
            "parent().par.Coloradjustmentenabled"
        )
        _repair_effect_shader_paths(color_adjustment)
        glitch.outputConnectors[0].connect(
            color_adjustment.inputConnectors[0]
        )

        motion = _load_single_tox(demo, MOTION_STUDIO_TOX)
        motion.name = "motion_studio"
        motion.nodeX = 1780
        motion.nodeY = 0
        motion.par.Enabled.expr = "parent().par.Motionenabled"
        _repair_effect_shader_paths(motion)
        color_adjustment.outputConnectors[0].connect(
            motion.inputConnectors[0]
        )

        rack = _load_single_tox(demo, RACK_TOX)
        rack.name = "fx_rack"
        rack.nodeX = 2040
        rack.nodeY = 0
        _set_library_root(rack, "demo rack")
        _sync_extension(rack, "FxRackExt")
        _repair_effect_shader_paths(rack)
        _repair_effect_state_paths(rack)
        motion.outputConnectors[0].connect(rack.inputConnectors[0])
        fixture_values = {
            "displacement": (0.72, 0.28, 0.50, 1.0),
            "depth": (0.68, 0.68, 0.68, 1.0),
            "normal": (0.64, 0.36, 1.00, 1.0),
            "flow": (0.58, 0.42, 0.85, 1.0),
            "mask": (0.72, 0.72, 0.72, 1.0),
        }
        secondary_shader = demo.create(textDAT, "fixture_image_b_shader")
        secondary_shader.text = DEMO_SECONDARY_IMAGE_SHADER
        secondary_shader.nodeX = -520
        secondary_shader.nodeY = -110
        secondary = demo.create(glslTOP, "fixture_image_b")
        secondary.nodeX = -300
        secondary.nodeY = -110
        source.outputConnectors[0].connect(secondary.inputConnectors[0])
        secondary.par.pixeldat = secondary.relativePath(secondary_shader)
        if secondary.par["glslversion"] is not None:
            secondary.par.glslversion = "glsl460"
        if secondary.par["compilebehavior"] is not None:
            secondary.par.compilebehavior = "stalluntildone"
        if secondary.par["errorbehavior"] is not None:
            secondary.par.errorbehavior = "showerror"
        if secondary.par["outputresolution"] is not None:
            secondary.par.outputresolution = "useinput"
        secondary.outputConnectors[0].connect(rack.inputConnectors[1])

        for input_index, (role, color) in enumerate(fixture_values.items(), start=2):
            fixture = demo.create(constantTOP, "fixture_{}".format(role))
            fixture.nodeX = -300
            fixture.nodeY = -input_index * 110
            for suffix, value in zip("rgba", color):
                parameter = fixture.par["color{}".format(suffix)]
                if parameter is not None:
                    parameter.val = value
            if fixture.par["outputresolution"] is not None:
                fixture.par.outputresolution = "custom"
                fixture.par.resolutionw = 1
                fixture.par.resolutionh = 1
            fixture.outputConnectors[0].connect(rack.inputConnectors[input_index])

        video_fx_router = demo.create(switchTOP, "video_fx_router")
        motion.outputConnectors[0].connect(
            video_fx_router.inputConnectors[0]
        )
        rack.outputConnectors[0].connect(video_fx_router.inputConnectors[1])
        video_fx_router.par.index.expr = (
            "1 if parent().par.Applyvideofx else 0"
        )
        video_fx_router.nodeX = 2290
        video_fx_router.nodeY = 0

        output = demo.create(outTOP, "out1_image")
        output.nodeX = 2500
        output.nodeY = 0
        video_fx_router.outputConnectors[0].connect(output.inputConnectors[0])
        if output.par["outputresolution"] is not None:
            output.par.outputresolution = "custom"
            output.par.resolutionw.expr = _output_resolution_expression("width")
            output.par.resolutionh.expr = _output_resolution_expression("height")
        output.display = True
        output.render = True
        demo.par.opviewer = output.path

        health = library.HealthCheck()
        return {
            "ok": bool(health.get("ok")),
            "library": library.path,
            "demo": demo.path,
            "reference_particle_field": reference_particle_field.path,
            "calligraphic_shadow": calligraphic_shadow.path,
            "ink_orbit_canvas": ink_orbit_canvas.path,
            "ink_flow": ink_flow.path,
            "particles": particles.path,
            "glitch": glitch.path,
            "color_adjustment": color_adjustment.path,
            "motion": motion.path,
            "output": output.path,
            "resolution_preset": str(demo.par.Resolutionpreset.eval()),
            "output_width": int(output.width),
            "output_height": int(output.height),
            "package_count": health.get("package_count"),
            "package_version_count": health.get("package_version_count"),
            "harness_project": str(harness_project),
            "saved": False,
        }
    except Exception:
        for child in reversed(created):
            try:
                child.destroy()
            except Exception:
                pass
        raise


if __name__ == "__main__":
    print("TD ImageFX QA harness:", install())
