"""Native two-way toggle regression tests, isolated from the operator's show.

Audit the installed bindings before creating fixtures; never repair a missing
binding to make the initial audit pass. Temporary cue copies exercise recall,
reordering, rack reloads, and the master bypass without editing the real cue.
"""
from datetime import datetime, timezone
from pathlib import Path
import copy
import json
import traceback
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
REPORT_PATH = ROOT / "build/envoy-validation/module-toggle-bindings.json"


def validate(write_report=True):
    original = op("/project1/imagefx_demo/show_control")
    original_ext = original.ext.ShowControlExt
    document = copy.deepcopy(original_ext.document)
    draft = original_ext._look_edit
    main_look = original_ext._capture_look(original.parent())
    checks = {}
    report = {"ok": False, "generated_at": datetime.now(timezone.utc).isoformat()}
    qa = None

    def linked(child, master, value=None):
        return (child.mode == ParMode.BIND and child.bindMaster == master
                and not child.readOnly and bool(child) == bool(master)
                and (value is None or bool(child) == value))

    def module_pairs(owner, mapping):
        return [(name, owner.op(name).par.Enabled, owner.par[toggle])
                for name, toggle in mapping.items()
                if owner.op(name) is not None and owner.par[toggle] is not None]

    def audit_rack(rack, prefix):
        for index in range(1, 9):
            slot = rack.op("slot" + str(index))
            checks[prefix + "/slot{}_binding".format(index)] = (
                slot is not None and linked(slot.par.Enable, rack.par["Slot{}enable".format(index)]))
        checks[prefix + "/master_gate_present"] = (
            rack.op("rack_chain_out") is not None and rack.op("rack_enable_switch") is not None
            and rack.op("out1_image").inputs[0] == rack.op("rack_enable_switch"))

    def exercise(owner, mapping, prefix):
        pairs = module_pairs(owner, mapping)
        for name, child, master in pairs:
            others = {p.name: bool(p) for n, c, p in pairs if n != name}
            for value in (True, False):
                master.val = value
                checks[prefix + "/" + name + "/parent_" + str(value)] = linked(child, master, value)
                child.val = not value
                checks[prefix + "/" + name + "/child_" + str(not value)] = linked(child, master, not value)
            checks[prefix + "/" + name + "/independent"] = all(
                bool(owner.par[key]) == value for key, value in others.items())
            child.val = False
        rack = owner.op("fx_rack")
        audit_rack(rack, prefix + "/rack")
        for index in range(1, 9):
            child, master = rack.op("slot" + str(index)).par.Enable, rack.par["Slot{}enable".format(index)]
            for value in (True, False):
                master.val = value
                checks[prefix + "/slot{}_parent_{}".format(index, value)] = linked(child, master, value)
                child.val = not value
                checks[prefix + "/slot{}_child_{}".format(index, not value)] = linked(child, master, not value)
            child.val = False

    def pixels(top):
        top.cook(force=True)
        data = top.numpyArray(delayed=False)
        if data is None:
            data = top.numpyArray(delayed=False)
        if data is None or not np.isfinite(data).all():
            raise AssertionError("Missing/non-finite pixels: " + top.path)
        return np.array(data, copy=True)

    try:
        mapping = original.parent().op("workflow").module.MODULE_TOGGLES
        for dat in op("/project1").findChildren(type=textDAT, name="workflow"):
            owner = dat.parent()
            if owner.op("calligraphic_shadow") is None:
                continue
            for name, child, master in module_pairs(owner, mapping):
                checks["installed" + owner.path + "/" + name] = linked(child, master)
        for dat in op("/project1").findChildren(type=textDAT, name="FxRackExt"):
            audit_rack(dat.parent(), "installed" + dat.parent().path)

        qa = original.parent().copy(original, name="module_binding_qa")
        qa.initializeExtensions()
        qa.op("show_tick").par.active = False
        qa.par.Renderwidth, qa.par.Renderheight = 320, 180
        ext = qa.ext.ShowControlExt
        deck = ext._new_deck("binding_test")
        deck.allowCooking = True
        ext._set_deck_resolution(deck)
        flow = deck.op("workflow").module
        owners = [deck, deck.op("image_composition/a_effects"), deck.op("image_composition/b_effects")]
        for owner in owners:
            exercise(owner, mapping, "roundtrip/" + owner.name)

        looks = {}
        for value in (True, False):
            for owner in owners:
                for name, child, master in module_pairs(owner, mapping):
                    child.val = value
            # This test captures controls, not private media validity.
            looks[value] = ext._capture_look(deck, active=False)
            checks["capture_all_" + str(value)] = all(
                toggle == value for toggle in looks[value]["toggles"].values())
        for value in (True, False):
            ext._apply_look(deck, looks[value], active=False)
            for owner in owners:
                for name, child, master in module_pairs(owner, mapping):
                    key = "recall/{}/{}/{}".format(value, owner.name, name)
                    checks[key] = linked(child, master, value)
                    child.val = not value
                    checks[key + "/editable"] = linked(child, master, not value)
                    child.val = value
                audit_rack(owner.op("fx_rack"), "recall/{}/{}".format(value, owner.name))

        flow.apply_order(deck, list(reversed(flow.current(deck))))
        for name, child, master in module_pairs(deck, mapping):
            checks["reorder/" + name] = linked(child, master, False)
        flow.apply_order(deck, list(flow.DEFAULT_ORDER))

        rack = deck.op("fx_rack")
        rack.par.Autotime = False
        rack.par.Manualtime = 0
        preset = json.loads(rack.ExportPreset())
        package = preset["slots"][-1]["package"]
        rack.LoadSlot(8, package["id"], package["version"])
        checks["slot_reload_gate_retained"] = rack.op("out1_image").inputs[0] == rack.op("rack_enable_switch")
        checks["slot_reload_binding_retained"] = linked(rack.op("slot8").par.Enable, rack.par.Slot8enable)
        rack.ImportPreset(preset)
        audit_rack(rack, "preset_roundtrip")

        # Deterministic two-texture fixture verifies actual gate pixels, not
        # just parameter values. It is connected only inside the QA copy.
        source = deck.create(constantTOP, "binding_gate_input")
        processed = rack.create(constantTOP, "binding_gate_processed")
        for top in (source, processed):
            top.par.outputresolution = "custom"
            top.par.resolutionw, top.par.resolutionh = 320, 180
        source.par.colorr, source.par.colorg, source.par.colorb = 1, 0, 0
        processed.par.colorr, processed.par.colorg, processed.par.colorb = 0, 0, 1
        source.outputConnectors[0].connect(rack.inputConnectors[0])
        processed.outputConnectors[0].connect(rack.op("rack_chain_out").inputConnectors[0])
        rack.par.Enabled = False
        checks["master_off_pixel_bypass"] = np.array_equal(pixels(rack.op("out1_image")), pixels(source))
        rack.par.Enabled = True
        checks["master_on_processed_pixels"] = np.array_equal(pixels(rack.op("out1_image")), pixels(processed))
        checks["master_switch_parent_updated"] = bool(deck.par.Applyvideofx)
        checks["rack_output_no_errors"] = not rack.op("out1_image").errors(recurse=True)
    except Exception:
        report["error"] = traceback.format_exc()
    finally:
        if qa is not None:
            qa.destroy()
        checks["user_cue_document_unchanged"] = original_ext.document == document
        checks["user_look_draft_unchanged"] = original_ext._look_edit is draft
        checks["user_designer_look_unchanged"] = original_ext._capture_look(original.parent()) == main_look
    report["checks"] = {name: bool(value) for name, value in checks.items()}
    report["ok"] = "error" not in report and all(report["checks"].values())
    if write_report:
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    result = validate()
    print("MODULE SWITCH VALIDATION:", result["ok"], "checks:", len(result["checks"]))
    if "error" in result:
        print(result["error"])
    print("Failed:", [name for name, passed in result["checks"].items() if not passed])
