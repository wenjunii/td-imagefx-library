"""Check both shadow switches and cue look round trips on disposable copies.

Run inside TouchDesigner; never edits the user's cue document or look draft.
"""
from datetime import datetime, timezone
from pathlib import Path
import copy
import json
import traceback

ROOT = Path(__file__).resolve().parents[2]
REPORT_PATH = ROOT / "build/envoy-validation/shadow-toggle-binding.json"


def validate(write_report=True):
    original = op("/project1/imagefx_demo/show_control")
    original_ext = original.ext.ShowControlExt
    document = copy.deepcopy(original_ext.document)
    draft = original_ext._look_edit
    checks = {}
    report = {"ok": False, "generated_at": datetime.now(timezone.utc).isoformat()}
    qa = None
    try:
        qa = original.parent().copy(original, name="shadow_binding_qa")
        qa.initializeExtensions()
        qa.op("show_tick").par.active = False
        ext = qa.ext.ShowControlExt
        qa.par.Renderwidth, qa.par.Renderheight = 320, 180
        deck = ext._new_deck("binding_test")
        deck.allowCooking = True
        ext._set_deck_resolution(deck)
        flow = deck.op("workflow").module
        child = deck.op("calligraphic_shadow").par.Enabled
        master = deck.par.Calligraphicshadowenabled
        flow.bind_shadow_enabled(deck)

        def linked(value):
            return (bool(master.eval()) == value and bool(child.eval()) == value
                    and child.mode == ParMode.BIND and child.bindMaster == master)

        for value in (True, False, True):
            master.val = value
            checks["parent_to_child_" + str(value)] = linked(value)
            child.val = not value
            checks["child_to_parent_" + str(not value)] = linked(not value)
        child.val = True
        enabled_look = ext._capture_look(deck)
        checks["capture_child_on"] = enabled_look["toggles"]["Calligraphicshadowenabled"]
        child.val = False
        disabled_look = ext._capture_look(deck)
        checks["capture_child_off"] = not disabled_look["toggles"]["Calligraphicshadowenabled"]
        for value, look in ((True, enabled_look), (False, disabled_look)):
            ext._apply_look(deck, look)
            checks["recall_preserves_binding_" + str(value)] = linked(value)
            child.val = not value
            checks["editable_after_recall_" + str(value)] = linked(not value)
        master.val = False
        child.mode = ParMode.CONSTANT
        child.val = True
        flow.bind_shadow_enabled(deck, preserve_child=True)
        checks["migration_keeps_visible_effect"] = linked(True)
        flow.apply_order(deck, list(reversed(flow.current(deck))))
        checks["reorder_keeps_binding"] = linked(True)
        for name in ("a_effects", "b_effects"):
            branch = deck.op("image_composition/" + name)
            branch.op("calligraphic_shadow").par.Enabled.val = True
            checks[name + "_bidirectional"] = bool(branch.par.Calligraphicshadowenabled)
        checks["no_shadow_operator_errors"] = not deck.op("calligraphic_shadow").errors(recurse=True)
    except Exception:
        report["error"] = traceback.format_exc()
    finally:
        if qa is not None:
            qa.destroy()
        checks["user_cue_document_unchanged"] = original_ext.document == document
        checks["user_look_draft_unchanged"] = original_ext._look_edit is draft
    report["checks"] = {name: bool(value) for name, value in checks.items()}
    report["ok"] = "error" not in report and all(report["checks"].values())
    if write_report:
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    print(json.dumps(validate(), indent=2))
