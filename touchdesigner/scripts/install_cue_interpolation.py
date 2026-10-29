"""Install cue transitions in a stopped show while retaining its document.

Run inside TouchDesigner. This installer never saves the TOE or show file.
"""
from __future__ import annotations

import copy
import importlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def install(show=None):
    import td
    show = show or td.op("/project1/imagefx_demo/show_control")
    if show is None:
        raise RuntimeError("Show Control is missing")
    previous = show.ext.ShowControlExt
    if previous.engine.state != "stopped" or previous._look_edit is not None:
        raise RuntimeError("Stop All and finish or cancel the look draft before installing cue transitions")
    if show.fetch("imagefx_export_job", None, search=False):
        raise RuntimeError("Finish video export before installing cue transitions")
    document = copy.deepcopy(previous.document)
    selected = int(show.par.Selectedcue.eval())
    values = {p.name: (p.eval(), p.mode, p.expr, p.bindExpr) for p in show.customPars
              if not p.isPulse and not p.readOnly and p.name not in {"Audioenabled", "Masterblackout"}}
    builder_path = ROOT / "touchdesigner/scripts/build_show_control.py"
    spec = importlib.util.spec_from_file_location("_cue_transition_builder", builder_path)
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    builder.install_transition_controls(show)
    importlib.reload(previous.model)
    show.op("ShowControlExt").text = (ROOT / "touchdesigner/extensions/ShowControlExt.py").read_text(encoding="utf-8")
    show.initializeExtensions()
    current = show.ext.ShowControlExt
    if current.document != current.model.validate_show(document):
        raise RuntimeError("Cue document changed unexpectedly during installation")
    current.SelectCue(selected)
    for name, (value, mode, expression, binding) in values.items():
        parameter = show.par[name]
        if parameter.eval() != value:
            parameter.val = value
        if (parameter.expr, parameter.bindExpr, parameter.mode) != (expression, binding, mode):
            parameter.expr, parameter.bindExpr, parameter.mode = expression, binding, mode
    current._save_document_dat()
    show.par.Masterblackout, show.par.Audioenabled = True, False
    current._status("Cue transitions installed: Cue Editor > Visual Transition")
    inspector = show.op("show_panel_layout")
    if inspector is not None:
        inspector.module.configure(show)
    return {"ok": True, "cue_count": len(document["cues"]),
            "legacy_default": "crossfade", "modes": list(show.par.Transition.menuNames),
            "document_preserved": True,
            "controls_preserved": all(show.par[n].eval() == v[0] and show.par[n].mode == v[1]
                                      and show.par[n].expr == v[2] and show.par[n].bindExpr == v[3]
                                      for n, v in values.items()), "toe_saved": False}


if __name__ == "__main__":
    print(json.dumps(install(), indent=2))
