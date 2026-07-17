"""Install the compiled ImageFX core into a disposable TouchDesigner QA project.

Run this script inside a project that contains Embody/Envoy. It changes only the
live network, never saves the project, and refuses the canonical library .toe.
Executing it through Envoy makes the operation one TouchDesigner undo step.
"""

from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CANONICAL_PROJECT = PROJECT_ROOT / "TD_ImageFX_Library.toe"
LIBRARY_TOX = PROJECT_ROOT / "touchdesigner" / "core" / "TDImageFXLibrary.tox"
RACK_TOX = PROJECT_ROOT / "touchdesigner" / "core" / "FxRack.tox"
EXTENSION_ROOT = PROJECT_ROOT / "touchdesigner" / "extensions"
MANAGED_NAMES = ("td_imagefx", "imagefx_demo")


def _current_project_identity():
    return Path(str(project.folder)).resolve(), Path(str(project.name)).stem


def _refuse_canonical_project():
    folder, name = _current_project_identity()
    if folder == CANONICAL_PROJECT.parent.resolve() and name == CANONICAL_PROJECT.stem:
        raise RuntimeError(
            "Refusing to install the QA harness into TD_ImageFX_Library.toe"
        )


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

    _refuse_canonical_project()
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

        demo = project_comp.create(baseCOMP, "imagefx_demo")
        created.append(demo)
        demo.nodeX = 100
        demo.nodeY = 100
        demo.color = (0.32, 0.18, 0.36)
        demo.comment = "Disposable Embody/Envoy QA harness"

        source = demo.create(rampTOP, "source_image")
        source.nodeX = -300
        source.nodeY = 0
        if source.par["outputresolution"] is not None:
            source.par.outputresolution = "custom"
            source.par.resolutionw = 1280
            source.par.resolutionh = 720

        rack = _load_single_tox(demo, RACK_TOX)
        rack.name = "fx_rack"
        rack.nodeX = 0
        rack.nodeY = 0
        _set_library_root(rack, "demo rack")
        _sync_extension(rack, "FxRackExt")
        _repair_effect_shader_paths(rack)
        source.outputConnectors[0].connect(rack.inputConnectors[0])

        output = demo.create(outTOP, "out1_image")
        output.nodeX = 280
        output.nodeY = 0
        rack.outputConnectors[0].connect(output.inputConnectors[0])
        output.display = True
        output.render = True
        demo.par.opviewer = output.path

        health = library.HealthCheck()
        return {
            "ok": bool(health.get("ok")),
            "library": library.path,
            "demo": demo.path,
            "output": output.path,
            "package_count": health.get("package_count"),
            "package_version_count": health.get("package_version_count"),
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
