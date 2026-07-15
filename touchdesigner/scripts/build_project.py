"""Build the native TD ImageFX .toe and .tox assets inside TouchDesigner.

Run from TouchDesigner's Textport:

    script = r"C:/path/to/video-effects/touchdesigner/scripts/build_project.py"
    exec(compile(open(script, encoding="utf-8").read(), script, "exec"),
         {"__file__": script, "__name__": "__main__"})

The script only creates or updates operators inside ``/project1/td_imagefx`` and
``/project1/imagefx_demo``. Package source files remain text-first on disk.
"""

from __future__ import annotations

import json
import re
import traceback
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = PROJECT_ROOT / "packages"
CORE_ROOT = PROJECT_ROOT / "touchdesigner" / "core"
BUILD_ROOT = PROJECT_ROOT / "build"
PROJECT_PATH = PROJECT_ROOT / "TD_ImageFX_Library.toe"
LIBRARY_VERSION = "0.1.0"


def _read_text(path):
    return Path(path).read_text(encoding="utf-8")


def _manifest_sort_key(manifest):
    return (manifest.get("category", ""), manifest.get("name", ""), manifest.get("version", ""))


def load_manifests():
    manifests = []
    for manifest_path in sorted(PACKAGE_ROOT.glob("*/**/package.json")):
        manifest = json.loads(_read_text(manifest_path))
        manifest["_path"] = manifest_path
        manifests.append(manifest)
    return sorted(manifests, key=_manifest_sort_key)


def _safe_name(value):
    return re.sub(r"[^A-Za-z0-9_]", "_", str(value))


def _set_par_defaults(par, definition):
    if "default" in definition:
        try:
            par.default = definition["default"]
        except Exception:
            pass
        par.val = definition["default"]
    if "min" in definition:
        par.min = definition["min"]
        par.normMin = definition["min"]
        par.clampMin = True
    if "max" in definition:
        par.max = definition["max"]
        par.normMax = definition["max"]
        par.clampMax = True


def _append_parameter(comp, page, definition):
    name = definition["name"]
    label = definition.get("label", name)
    par_type = definition.get("type", "float")
    if par_type == "toggle":
        page.appendToggle(name, label=label)
        par = comp.par[name]
        _set_par_defaults(par, definition)
        return [par]
    if par_type == "pulse":
        page.appendPulse(name, label=label)
        return [comp.par[name]]
    if par_type == "string":
        page.appendStr(name, label=label)
        par = comp.par[name]
        _set_par_defaults(par, definition)
        return [par]
    if par_type == "menu":
        page.appendMenu(name, label=label)
        par = comp.par[name]
        par.menuNames = list(definition.get("menu_names", []))
        par.menuLabels = list(definition.get("menu_labels", par.menuNames))
        _set_par_defaults(par, definition)
        return [par]
    if par_type == "rgba":
        page.appendRGBA(name, label=label)
        pars = [comp.par[name + suffix] for suffix in "rgba"]
        defaults = list(definition.get("default", [0.0, 0.0, 0.0, 1.0]))
        for index, par in enumerate(pars):
            _set_par_defaults(par, {"default": defaults[index], "min": 0.0, "max": 1.0})
        return pars
    page.appendFloat(name, label=label)
    par = comp.par[name]
    _set_par_defaults(par, definition)
    return [par]


def _append_system_parameters(comp, manifest):
    page = comp.appendCustomPage("Package")
    definitions = []
    if any(definition.get("name") == "Time" for definition in manifest.get("parameters", [])):
        definitions.append(
            {"name": "Timescale", "label": "Time Scale", "type": "float", "default": 1.0, "min": -10.0, "max": 10.0}
        )
    definitions.extend((
        {"name": "Packageid", "label": "Package ID", "type": "string", "default": manifest["id"]},
        {"name": "Packageversion", "label": "Package Version", "type": "string", "default": manifest["version"]},
        {"name": "Fxapi", "label": "FX API", "type": "string", "default": manifest.get("fx_api", "1.0")},
        {"name": "Status", "type": "string", "default": "Ready"},
    ))
    for definition in definitions:
        _append_parameter(comp, page, definition)


def _configure_glsl_uniform(glsl, definition, custom_pars, vector_index, color_index):
    uniform = definition.get("uniform")
    if not uniform:
        return vector_index, color_index
    if definition.get("type") == "rgba":
        glsl.par["color{}name".format(color_index)] = uniform
        suffixes = ("rgbr", "rgbg", "rgbb", "alpha")
        for shader_suffix, custom_par in zip(suffixes, custom_pars):
            target = glsl.par["color{}{}".format(color_index, shader_suffix)]
            target.expr = "parent().par.{}".format(custom_par.name)
        return vector_index, color_index + 1
    glsl.par["vec{}name".format(vector_index)] = uniform
    axes = ("x", "y", "z", "w")
    for axis, custom_par in zip(axes, custom_pars):
        target = glsl.par["vec{}value{}".format(vector_index, axis)]
        target.expr = "parent().par.{}".format(custom_par.name)
    return vector_index + 1, color_index


def configure_extension(comp, class_name, source_path):
    code_dat = comp.create(textDAT, class_name)
    code_dat.text = _read_text(source_path)
    code_dat.nodeX = -200
    code_dat.nodeY = -300
    comp.par.ext0object = "op('./{}').module.{}(me)".format(class_name, class_name)
    comp.par.ext0name = class_name
    comp.par.ext0promote = True
    comp.par.initextonstart = True
    comp.par.reinitextensions.pulse()
    return code_dat


def load_tox_component(parent_comp, tox_path, name):
    """Load a .tox as a direct child and return its top-level component."""
    before_ids = {child.id for child in parent_comp.children}
    parent_comp.loadTox(str(tox_path))
    created = [child for child in parent_comp.children if child.id not in before_ids]
    if len(created) != 1:
        raise RuntimeError(
            "Expected one top-level component from {}, found {}".format(tox_path, len(created))
        )
    instance = created[0]
    instance.name = name
    return instance


def build_effect(parent_comp, manifest, report):
    component_name = _safe_name(manifest["id"])
    effect = parent_comp.create(baseCOMP, component_name)
    effect.nodeWidth = 180
    effect.nodeHeight = 120
    effect.color = (0.18, 0.32, 0.46)
    effect.comment = "{}\n{}\n{}".format(manifest["name"], manifest["id"], manifest["version"])

    effect_page = effect.appendCustomPage("ImageFX")
    vector_index = 0
    color_index = 0
    parameter_bindings = []
    for definition in manifest.get("parameters", []):
        custom_pars = _append_parameter(effect, effect_page, definition)
        parameter_bindings.append((definition, custom_pars))
    _append_system_parameters(effect, manifest)

    for input_index, input_definition in enumerate(manifest.get("inputs", []), start=1):
        input_node = effect.create(inTOP, "in{}_{}".format(input_index, _safe_name(input_definition["id"])))
        input_node.par.label = input_definition["id"]
        input_node.nodeX = -350
        input_node.nodeY = 180 - input_index * 120

    shader_path = manifest["_path"].parent / manifest["entrypoints"]["shader"]
    shader_dat = effect.create(textDAT, "pixel_shader")
    shader_dat.text = _read_text(shader_path)
    shader_dat.nodeX = -120
    shader_dat.nodeY = -220

    glsl = effect.create(glslTOP, "effect_glsl")
    glsl.nodeX = 0
    glsl.nodeY = 0
    for input_index, input_node in enumerate(sorted(effect.findChildren(type=inTOP), key=lambda node: node.name)):
        input_node.outputConnectors[0].connect(glsl.inputConnectors[input_index])
    glsl.par.pixeldat = shader_dat.path
    if glsl.par["glslversion"] is not None:
        glsl.par.glslversion = "glsl460"
    if glsl.par["compilebehavior"] is not None:
        glsl.par.compilebehavior = "stalluntildone"
    if glsl.par["errorbehavior"] is not None:
        glsl.par.errorbehavior = "showprevious"
    if glsl.par["outputresolution"] is not None:
        glsl.par.outputresolution = "useinput"
    # Color and vector uniforms are sequential parameter blocks.  A newly
    # created GLSL TOP exposes one block of each, so size both sequences before
    # addressing vec1/color1 and beyond.
    uniform_definitions = [
        definition
        for definition, _custom_pars in parameter_bindings
        if definition.get("uniform")
    ]
    glsl.seq.vec.numBlocks = max(
        1, sum(1 for definition in uniform_definitions if definition.get("type") != "rgba")
    )
    glsl.seq.color.numBlocks = max(
        1, sum(1 for definition in uniform_definitions if definition.get("type") == "rgba")
    )
    for definition, custom_pars in parameter_bindings:
        vector_index, color_index = _configure_glsl_uniform(
            glsl, definition, custom_pars, vector_index, color_index
        )

    time_par = effect.par["Time"]
    if time_par is not None:
        time_par.expr = "absTime.seconds * me.par.Timescale"

    # TOP bypass is an operator property in current TouchDesigner builds rather
    # than an expression-capable parameter.  A Switch TOP keeps the component's
    # Enable control exportable and makes bypass deterministic for every effect.
    bypass_switch = effect.create(switchTOP, "enable_switch")
    first_input = sorted(effect.findChildren(type=inTOP), key=lambda node: node.name)[0]
    first_input.outputConnectors[0].connect(bypass_switch.inputConnectors[0])
    glsl.outputConnectors[0].connect(bypass_switch.inputConnectors[1])
    bypass_switch.par.index.expr = "1 if parent().par.Enable else 0"
    bypass_switch.nodeX = 190
    bypass_switch.nodeY = 0

    output = effect.create(outTOP, "out1_image")
    bypass_switch.outputConnectors[0].connect(output.inputConnectors[0])
    output.nodeX = 280
    output.nodeY = 0
    output.display = True
    output.render = True

    info = effect.create(infoDAT, "shader_info")
    info.par.op = glsl.path
    info.nodeX = 120
    info.nodeY = -220

    glsl.cook(force=True)
    shader_errors = []
    try:
        shader_errors = list(glsl.errors())
    except Exception:
        pass
    if shader_errors:
        report["shader_errors"][manifest["id"]] = shader_errors

    tox_path = manifest["_path"].parent / manifest["entrypoints"]["touchdesigner_component"]
    tox_path.parent.mkdir(parents=True, exist_ok=True)
    effect.save(str(tox_path), createFolders=True)
    effect.par.externaltox = tox_path.relative_to(PROJECT_ROOT).as_posix()
    effect.par.enableexternaltox = True
    effect.par.savebackup = True
    if effect.par["relpath"] is not None:
        effect.par.relpath = "project"
    report["effects"].append({"id": manifest["id"], "version": manifest["version"], "tox": str(tox_path)})
    return effect


def build_update_manager(parent_comp):
    updater = parent_comp.create(baseCOMP, "update_manager")
    updater.color = (0.42, 0.28, 0.12)
    updater.comment = "Safe update discovery. Installs are never activated automatically."
    page = updater.appendCustomPage("Updates")
    definitions = (
        {"name": "Rootfolder", "label": "Library Root (Blank = Project Folder)", "type": "string", "default": ""},
        {"name": "Autocheck", "label": "Auto Check", "type": "toggle", "default": True},
        {"name": "Intervalhours", "label": "Interval (Hours)", "type": "float", "default": 24.0, "min": 1.0 / 60.0, "max": 720.0},
        {"name": "Channel", "type": "menu", "default": "stable", "menu_names": ["stable", "beta", "experimental"], "menu_labels": ["Stable", "Beta", "Experimental"]},
        {"name": "Timeout", "label": "Timeout (Seconds)", "type": "float", "default": 10.0, "min": 1.0, "max": 120.0},
        {"name": "Checkupdates", "label": "Check for Updates", "type": "pulse"},
        {"name": "Lastcheck", "label": "Last Check", "type": "string", "default": ""},
        {"name": "Status", "type": "string", "default": "Not checked"},
    )
    for definition in definitions:
        _append_parameter(updater, page, definition)

    results = updater.create(tableDAT, "update_results")
    results.setSize(0, 0)
    results.appendRow(("id", "installed", "available", "channel", "restart", "permissions_changed", "source", "changelog"))
    results.nodeX = 0
    results.nodeY = 0

    configure_extension(updater, "UpdaterExt", PROJECT_ROOT / "touchdesigner" / "extensions" / "UpdaterExt.py")

    parexec = updater.create(parameterexecuteDAT, "parameter_callbacks")
    parexec.text = _read_text(PROJECT_ROOT / "touchdesigner" / "callbacks" / "updater_parameter_callbacks.py")
    parexec.par.op = updater.path
    parexec.par.pars = "Checkupdates Autocheck Intervalhours"
    parexec.par.valuechange = True
    parexec.par.onpulse = True
    parexec.par.custom = True
    parexec.par.builtin = False
    parexec.nodeX = 220
    parexec.nodeY = -120

    starter = updater.create(executeDAT, "startup_callbacks")
    starter.text = _read_text(PROJECT_ROOT / "touchdesigner" / "callbacks" / "updater_start_callbacks.py")
    starter.par.start = True
    starter.nodeX = 220
    starter.nodeY = -240

    updater.save(str(CORE_ROOT / "FxUpdater.tox"), createFolders=True)
    return updater


def build_rack(parent_comp, manifests, effect_components):
    rack = parent_comp.create(baseCOMP, "fx_rack")
    rack.color = (0.28, 0.20, 0.48)
    rack.comment = "Four-slot reusable ImageFX rack"
    page = rack.appendCustomPage("Rack")
    package_ids = [manifest["id"] for manifest in manifests]
    package_labels = [manifest["name"] for manifest in manifests]
    defaults = [
        "tdimagefx.distort.wave-warp",
        "tdimagefx.glitch.rgb-split",
        "tdimagefx.stylize.scanlines",
        "tdimagefx.stylize.vignette",
    ]
    _append_parameter(rack, page, {"name": "Rootfolder", "label": "Library Root (Blank = Project Folder)", "type": "string", "default": ""})
    _append_parameter(rack, page, {"name": "Autotime", "label": "Auto Time", "type": "toggle", "default": True})
    _append_parameter(rack, page, {"name": "Timescale", "label": "Time Scale", "type": "float", "default": 1.0, "min": -10.0, "max": 10.0})
    _append_parameter(rack, page, {"name": "Time", "type": "float", "default": 0.0, "min": -100000.0, "max": 100000.0})
    rack.par.Time.expr = "absTime.seconds * me.par.Timescale if me.par.Autotime else 0.0"
    for index in range(1, 5):
        _append_parameter(rack, page, {
            "name": "Slot{}effect".format(index), "label": "Slot {} Effect".format(index), "type": "menu",
            "default": defaults[index - 1], "menu_names": package_ids, "menu_labels": package_labels,
        })
        _append_parameter(rack, page, {"name": "Slot{}enable".format(index), "label": "Slot {} Enable".format(index), "type": "toggle", "default": True})
        _append_parameter(rack, page, {"name": "Slot{}mix".format(index), "label": "Slot {} Mix".format(index), "type": "float", "default": 1.0, "min": 0.0, "max": 1.0})

    rack_input = rack.create(inTOP, "in1_image")
    rack_input.par.label = "image"
    rack_input.nodeX = -520
    rack_input.nodeY = 0

    source_connector = rack_input.outputConnectors[0]
    for index, package_id in enumerate(defaults, start=1):
        manifest = next(item for item in manifests if item["id"] == package_id)
        tox_path = manifest["_path"].parent / manifest["entrypoints"]["touchdesigner_component"]
        slot = load_tox_component(rack, tox_path, "slot{}".format(index))
        slot.nodeX = -300 + (index - 1) * 210
        slot.nodeY = 0
        source_connector.connect(slot.inputConnectors[0])
        if len(slot.inputConnectors) > 1:
            rack_input.outputConnectors[0].connect(slot.inputConnectors[1])
        if slot.par["Enable"] is not None:
            slot.par.Enable.expr = "parent().par.Slot{}enable".format(index)
        if slot.par["Mix"] is not None:
            slot.par.Mix.expr = "parent().par.Slot{}mix".format(index)
        if slot.par["Time"] is not None:
            slot.par.Time.expr = "parent().par.Time"
        rack.store("slot{}_package".format(index), {"id": package_id, "version": manifest["version"]})
        source_connector = slot.outputConnectors[0]

    rack_output = rack.create(outTOP, "out1_image")
    source_connector.connect(rack_output.inputConnectors[0])
    rack_output.nodeX = 600
    rack_output.nodeY = 0
    rack_output.display = True
    rack_output.render = True

    configure_extension(rack, "FxRackExt", PROJECT_ROOT / "touchdesigner" / "extensions" / "FxRackExt.py")
    parexec = rack.create(parameterexecuteDAT, "parameter_callbacks")
    parexec.text = _read_text(PROJECT_ROOT / "touchdesigner" / "callbacks" / "rack_parameter_callbacks.py")
    parexec.par.op = rack.path
    parexec.par.pars = "Slot?effect"
    parexec.par.valuechange = True
    parexec.par.onpulse = True
    parexec.par.custom = True
    parexec.par.builtin = False
    parexec.nodeX = 400
    parexec.nodeY = -250

    rack_path = CORE_ROOT / "FxRack.tox"
    rack.save(str(rack_path), createFolders=True)
    return rack, rack_path


def build_library(project_comp, manifests, report):
    library = project_comp.create(baseCOMP, "td_imagefx")
    library.nodeX = -250
    library.nodeY = 100
    library.color = (0.10, 0.34, 0.42)
    library.comment = "TD ImageFX Library {}".format(LIBRARY_VERSION)
    page = library.appendCustomPage("Library")
    definitions = (
        {"name": "Version", "type": "string", "default": LIBRARY_VERSION},
        {"name": "Rootfolder", "label": "Library Root (Blank = Project Folder)", "type": "string", "default": ""},
        {"name": "Status", "type": "string", "default": "Building"},
        {"name": "Refreshcatalog", "label": "Refresh Catalog", "type": "pulse"},
    )
    for definition in definitions:
        _append_parameter(library, page, definition)

    catalog = library.create(tableDAT, "catalog")
    catalog.setSize(0, 0)
    catalog.appendRow(("id", "name", "version", "kind", "category", "channel", "stateful", "tags", "component"))
    for manifest in manifests:
        catalog.appendRow((
            manifest["id"], manifest["name"], manifest["version"], manifest["kind"], manifest["category"],
            manifest["channel"], str(manifest["stateful"]), ", ".join(manifest["tags"]),
            manifest["entrypoints"]["touchdesigner_component"],
        ))
    catalog.nodeX = -400
    catalog.nodeY = -250

    readme = library.create(textDAT, "README")
    readme.text = (
        "TD ImageFX Library {}\n\n"
        "Use core/fx_rack for a ready four-effect chain.\n"
        "Use the promoted Find(), CreateEffect(), CheckUpdates(), and HealthCheck() methods.\n"
        "All effect versions are immutable and stored under packages/<id>/<version>.\n"
        "Updates are notify-only by default; review and activation are separate actions.\n"
    ).format(LIBRARY_VERSION)
    readme.nodeX = -150
    readme.nodeY = -250

    effects_parent = library.create(baseCOMP, "effects")
    effects_parent.nodeX = 0
    effects_parent.nodeY = 100
    effect_components = {}
    for index, manifest in enumerate(manifests):
        effect = build_effect(effects_parent, manifest, report)
        effect.nodeX = (index % 4) * 230
        effect.nodeY = -(index // 4) * 180
        effect_components[manifest["id"]] = effect

    core_parent = library.create(baseCOMP, "core")
    core_parent.nodeX = 260
    core_parent.nodeY = 100
    updater = build_update_manager(library)
    updater.nodeX = 520
    updater.nodeY = 100
    rack, rack_path = build_rack(core_parent, manifests, effect_components)
    rack.nodeX = 0
    rack.nodeY = 0

    configure_extension(library, "ImageFXLibraryExt", PROJECT_ROOT / "touchdesigner" / "extensions" / "ImageFXLibraryExt.py")
    library.par.Status = "Ready: {} packages".format(len(manifests))
    library_path = CORE_ROOT / "TDImageFXLibrary.tox"
    library.save(str(library_path), createFolders=True)
    report["core"] = {
        "library": str(library_path),
        "rack": str(rack_path),
        "updater": str(CORE_ROOT / "FxUpdater.tox"),
    }
    return library, rack_path


def build_demo(project_comp, rack_path):
    demo = project_comp.create(baseCOMP, "imagefx_demo")
    demo.nodeX = 100
    demo.nodeY = 100
    demo.color = (0.32, 0.18, 0.36)
    demo.comment = "Animated starter chain. Replace source_image with any TOP."

    source = demo.create(rampTOP, "source_image")
    source.nodeX = -300
    source.nodeY = 0
    if source.par["outputresolution"] is not None:
        source.par.outputresolution = "custom"
        source.par.resolutionw = 1280
        source.par.resolutionh = 720

    rack = load_tox_component(demo, rack_path, "fx_rack")
    rack.nodeX = 0
    rack.nodeY = 0
    source.outputConnectors[0].connect(rack.inputConnectors[0])

    output = demo.create(outTOP, "out1_image")
    rack.outputConnectors[0].connect(output.inputConnectors[0])
    output.nodeX = 280
    output.nodeY = 0
    output.display = True
    output.render = True
    demo.par.opviewer = output.path
    return demo


def _existing_owned_nodes(project_comp):
    return [node for node in (project_comp.op("td_imagefx"), project_comp.op("imagefx_demo")) if node is not None]


def build():
    BUILD_ROOT.mkdir(parents=True, exist_ok=True)
    CORE_ROOT.mkdir(parents=True, exist_ok=True)
    report = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "library_version": LIBRARY_VERSION,
        "touchdesigner_version": str(app.version),
        "touchdesigner_build": str(app.build),
        "touchdesigner_os": str(app.osName),
        "touchdesigner_architecture": str(app.architecture),
        "project": str(PROJECT_PATH),
        "effects": [],
        "core": {},
        "shader_errors": {},
        "errors": [],
    }
    report_path = BUILD_ROOT / "touchdesigner-build-report.json"
    try:
        manifests = load_manifests()
        if not manifests:
            raise RuntimeError("No package manifests found")
        project_comp = op("/project1")
        if project_comp is None:
            project_comp = root.create(baseCOMP, "project1")
        existing = _existing_owned_nodes(project_comp)
        if existing:
            names = ", ".join(node.path for node in existing)
            raise RuntimeError("Refusing to overwrite existing generated nodes: {}".format(names))
        library, rack_path = build_library(project_comp, manifests, report)
        build_demo(project_comp, rack_path)
        project.save(str(PROJECT_PATH), saveExternalToxs=False)
    except Exception as exc:
        report["errors"].append({"error": str(exc), "traceback": traceback.format_exc()})
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        raise
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    debug("TD ImageFX build complete", str(PROJECT_PATH), "effects", len(report["effects"]))
    return report


if __name__ == "__main__":
    build()
