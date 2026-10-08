"""Read-only native navigation audit; requires an existing recalled look draft.

Does not edit effect values, create/delete a draft, play cues, or open outputs.
Use the two navigation buttons manually to complete the visible UI check.
"""
from datetime import datetime, timezone
from pathlib import Path
import copy
import json
from types import SimpleNamespace


def validate(write_report=True):
    show = op("/project1/imagefx_demo/show_control")
    ext = show.ext.ShowControlExt
    document = copy.deepcopy(ext.document)
    draft = ext._look_edit
    if not draft:
        raise ValueError("Recall a visual look before the navigation audit")
    main_look = ext._capture_look(show.parent())
    draft_look = ext._capture_look(draft["deck"])
    runtime = show.op("look_editor_controls").module
    checks = {}
    for name, path, label in runtime.TARGETS:
        target = runtime.control_target(show, name)
        expected = draft["deck"] if path == "." else draft["deck"].op(path)
        checks["target/" + name] = target == expected
        checks["custom_tabs/" + name] = bool(target.customPages)
    checks["menu_names"] = show.par.Lookmodule.menuNames == [row[0] for row in runtime.TARGETS]
    checks["menu_labels"] = show.par.Lookmodule.menuLabels == [row[2] for row in runtime.TARGETS]
    for name in ("Lookmodule", "Editlookcontrols", "Openlookpreview"):
        parameter = show.par[name]
        checks["draft_enable/" + name] = parameter.enable and parameter.enableExpr == "bool(me.par.Lookediting)"
    callback = show.op("look_editor_controls_callbacks")
    checks["pulse_callback"] = (bool(callback.par.active) and bool(callback.par.onpulse)
                                and callback.par.pars.eval() == "Editlookcontrols Openlookpreview")
    checks["dispatcher_exclusion"] = "if par.name in ('Editlookcontrols', 'Openlookpreview'):" in show.op("show_parameters").text
    checks["preview_is_off_air"] = show.op("look_preview").par.top.eval() == draft["deck"].op("out1_image")
    for state, active, label in (("stopped", None, "no_draft"), ("running", draft, "running"),
                                 ("paused", draft, "paused")):
        proxy = SimpleNamespace(ext=SimpleNamespace(ShowControlExt=SimpleNamespace(
            engine=SimpleNamespace(state=state), _look_edit=active)))
        try:
            runtime.active_deck(proxy)
            checks["guard/" + label] = False
        except ValueError:
            checks["guard/" + label] = True
    checks["document_preserved"] = document == ext.document
    checks["main_look_preserved"] = main_look == ext._capture_look(show.parent())
    checks["draft_preserved"] = draft is ext._look_edit and draft_look == ext._capture_look(draft["deck"])
    report = {"ok": all(checks.values()), "checks": checks,
              "generated_at": datetime.now(timezone.utc).isoformat(),
              "scope": "Look Editor navigation only; no playback or full release certification"}
    if write_report:
        path = Path(__file__).resolve().parents[2] / "build/envoy-validation/look-editor-controls.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    if not report["ok"]:
        raise AssertionError("Failed navigation checks: " + str([name for name, ok in checks.items() if not ok]))
    print("Look Editor navigation:", len(checks), "checks passed")
    return report


if __name__ == "__main__":
    validate()
