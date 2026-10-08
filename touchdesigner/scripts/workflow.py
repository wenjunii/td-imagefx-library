"""Self-contained module ordering for the demo and captured show decks."""
import json

DEFAULT_ORDER = (
    "reference_particle_field", "calligraphic_shadow", "ink_orbit_canvas",
    "ink_dream_flow", "ink_brush_flow", "ink_radial_flow", "ink_flow",
    "particle_random_move", "glitch_fusion", "color_adjustment", "color_switch", "motion_studio",
    "fx_rack", "image_composition", "layer_composite", "final_crop",
)
LABELS = ("Chromatic Particle Field", "Calligraphic Shadow", "Ink Orbit Canvas",
          "Ink Dream Flow", "Ink Brush Flow", "Ink Radial Flow", "Ink Flow Fusion",
          "Random Particles", "Glitch Fusion", "Color Adjustment", "Color Switch", "Motion Studio",
          "Eight-Slot FX Rack", "Two-Image Composition", "Layer Composite", "Final Crop")
BRANCH_ORDER = tuple(name for name in DEFAULT_ORDER if name != "image_composition")
LEGACY_ORDER = tuple(name for name in DEFAULT_ORDER if name not in {"color_switch", "image_composition"})
MODULE_TOGGLES = {
    "reference_particle_field": "Referenceparticlefieldenabled",
    "calligraphic_shadow": "Calligraphicshadowenabled", "ink_orbit_canvas": "Inkorbitenabled",
    "ink_flow": "Inkflowenabled", "particle_random_move": "Particlesenabled",
    "glitch_fusion": "Glitchenabled", "color_adjustment": "Coloradjustmentenabled",
    "motion_studio": "Motionenabled", "ink_dream_flow": "Inkdreamenabled",
    "ink_brush_flow": "Inkbrushenabled", "ink_radial_flow": "Inkradialenabled",
    "layer_composite": "Layercompositeenabled", "final_crop": "Finalcropenabled",
    "color_switch": "Colorswitchenabled", "image_composition": "Imagecompositionenabled",
    "fx_rack": "Applyvideofx",
}


def validate_order(order, branch=False):
    if not isinstance(order, (list, tuple)) or any(not isinstance(n,str) for n in order):
        raise ValueError("Workflow order must be a list of module names")
    expected = BRANCH_ORDER if branch else DEFAULT_ORDER
    if len(order) == len(LEGACY_ORDER) and set(order) == set(LEGACY_ORDER):
        # Migrate approved older cue orders without moving any existing stage.
        order = list(order)
        order.insert(order.index("color_adjustment")+1, "color_switch")
        if not branch: order.insert(order.index("layer_composite"), "image_composition")
    if len(order) != len(expected) or set(order) != set(expected):
        raise ValueError("Workflow must contain each of the {} stages exactly once".format(len(expected)))
    return list(order)


def moved_order(order, selection, action, branch=False):
    order = validate_order(order,branch)
    if action == "Resetorder": return list(BRANCH_ORDER if branch else DEFAULT_ORDER)
    if selection not in order: raise ValueError("Unknown workflow stage")
    index = order.index(selection)
    target = {"Stageup": index-1, "Stagedown": index+1, "Stagefirst": 0,
              "Stagelast": len(order)-1}.get(action)
    if target is None: raise ValueError("Unknown workflow action")
    target = max(0,min(len(order)-1,target))
    order.insert(target,order.pop(index))
    return order


def current(demo):
    return validate_order(json.loads(demo.op("workflow_order").text),demo.fetch("imagefx_branch",False))


def describe(demo):
    names = dict(zip(DEFAULT_ORDER,LABELS))
    return " -> ".join(names[n] for n in current(demo))


def bind_shadow_enabled(demo, preserve_child=False):
    """Compatibility entry point for the original shadow-only migration."""
    return bind_module_enabled(demo, "calligraphic_shadow", preserve_child)


def bind_module_enabled(demo, name, preserve_child=False):
    """Link both UI switches; relative binding also follows copied cue decks.

    Only the in-place migration preserves the child's effective state. Normal
    builds and look recalls use the parent routing value as the authority.
    """
    toggle = MODULE_TOGGLES[name]
    module = demo.op(name)
    master = getattr(demo.par, toggle, None)
    if module is None or master is None:
        return False
    enabled = module.par.Enabled
    if preserve_child:
        master.val = bool(enabled.eval())
    enabled.readOnly = False
    enabled.bindExpr = "parent().par." + toggle
    # The enum is exposed by TD's DAT globals, not the importable td module.
    # Taking it from the parameter also works in the builder's exec namespace.
    enabled.mode = type(enabled.mode).BIND
    return True


def install_rack_gate(rack, enabled=True):
    """Add a real master bypass without changing the eight slot selections.

    FxRackExt targets rack_chain_out when replacing/removing the last slot, so
    the gate survives preset imports and slot swaps. Standalone racks default
    on; workflow racks subsequently bind Enabled to Applyvideofx.
    """
    import td
    if getattr(rack.par, "Enabled", None) is None:
        page = next((p for p in rack.customPages if p.name == "Master"), None)
        if page is None:
            page = rack.appendCustomPage("Master")
        parameter = page.appendToggle("Enabled", label="Rack Enabled")[0]
        parameter.default = True
        parameter.val = bool(enabled)
    chain = rack.op("rack_chain_out")
    gate = rack.op("rack_enable_switch")
    if chain is not None and gate is not None:
        return
    if chain is not None or gate is not None:
        raise RuntimeError("Incomplete rack master gate")
    output = rack.op("out1_image")
    source = output.inputs[0] if output.inputs else rack.op("in1_image")
    while source.parent() != rack:
        source = source.parent()
    chain = rack.create(td.nullTOP, "rack_chain_out")
    gate = rack.create(td.switchTOP, "rack_enable_switch")
    source.outputConnectors[0].connect(chain.inputConnectors[0])
    rack.op("in1_image").outputConnectors[0].connect(gate.inputConnectors[0])
    chain.outputConnectors[0].connect(gate.inputConnectors[1])
    gate.par.index.expr = "int(parent().par.Enabled)"
    output.inputConnectors[0].disconnect()
    gate.outputConnectors[0].connect(output.inputConnectors[0])
    chain.nodeX, gate.nodeX, output.nodeX = 1300, 1500, 1700


def bind_module_enables(demo, preserve_children=False):
    """Bind every available module independently, including composition branches."""
    rack = demo.op("fx_rack")
    if rack is not None and getattr(demo.par, "Applyvideofx", None) is not None:
        install_rack_gate(rack, bool(demo.par.Applyvideofx))
    return [name for name in MODULE_TOGGLES
            if bind_module_enabled(demo, name, preserve_children)]


def apply_order(demo, order):
    order = validate_order(order,demo.fetch("imagefx_branch",False))
    required = [*order, "source_image", "video_fx_router", "out1_image", "workflow_order"]
    missing = [name for name in required if demo.op(name) is None]
    if missing: raise ValueError("Missing workflow nodes: " + ", ".join(missing))
    # Disconnect all chain edges first: swapping neighbors must not create a
    # transient cook-feedback loop. Auxiliary rack inputs are left untouched.
    for name in (*order,"video_fx_router","out1_image"):
        demo.op(name).inputConnectors[0].disconnect()
    previous = demo.op("source_image")
    for index,name in enumerate(order):
        node = demo.op(name)
        previous.outputConnectors[0].connect(node.inputConnectors[0])
        node.nodeX, node.nodeY = index*250,0
        if name == "fx_rack":
            router = demo.op("video_fx_router")
            previous.outputConnectors[0].connect(router.inputConnectors[0])
            node.outputConnectors[0].connect(router.inputConnectors[1])
            router.nodeX, router.nodeY = node.nodeX, -160
            previous = router
        else:
            previous = node
    previous.outputConnectors[0].connect(demo.op("out1_image").inputConnectors[0])
    demo.op("out1_image").nodeX = len(order)*250
    demo.op("workflow_order").text = json.dumps(order,indent=2)
    # Cue recall repairs routing expressions before reaching this function.
    # Restore the two-way links here without changing the recalled on/off values.
    bind_module_enables(demo)


def onPulse(par):
    demo = par.owner
    try:
        order = moved_order(current(demo),demo.par.Stageselection.eval(),par.name,demo.fetch("imagefx_branch",False))
        apply_order(demo,order)
        demo.par.Orderstatus = "Order updated; effect settings retained. Capture Look to store in a cue."
    except Exception as exc:
        demo.par.Orderstatus = "Order unchanged: " + str(exc)
