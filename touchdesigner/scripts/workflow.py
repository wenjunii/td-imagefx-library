"""Self-contained module ordering for the demo and captured show decks."""
import json

DEFAULT_ORDER = (
    "reference_particle_field", "calligraphic_shadow", "ink_orbit_canvas",
    "ink_dream_flow", "ink_brush_flow", "ink_radial_flow", "ink_flow",
    "particle_random_move", "glitch_fusion", "color_adjustment", "motion_studio",
    "fx_rack", "layer_composite", "final_crop",
)
LABELS = ("Chromatic Particle Field", "Calligraphic Shadow", "Ink Orbit Canvas",
          "Ink Dream Flow", "Ink Brush Flow", "Ink Radial Flow", "Ink Flow Fusion",
          "Random Particles", "Glitch Fusion", "Color Adjustment", "Motion Studio",
          "Eight-Slot FX Rack", "Layer Composite", "Final Crop")


def validate_order(order):
    if not isinstance(order, (list, tuple)) or any(not isinstance(n,str) for n in order):
        raise ValueError("Workflow order must be a list of module names")
    if len(order) != len(DEFAULT_ORDER) or set(order) != set(DEFAULT_ORDER):
        raise ValueError("Workflow must contain each of the 14 stages exactly once")
    return list(order)


def moved_order(order, selection, action):
    order = validate_order(order)
    if action == "Resetorder": return list(DEFAULT_ORDER)
    if selection not in order: raise ValueError("Unknown workflow stage")
    index = order.index(selection)
    target = {"Stageup": index-1, "Stagedown": index+1, "Stagefirst": 0,
              "Stagelast": len(order)-1}.get(action)
    if target is None: raise ValueError("Unknown workflow action")
    target = max(0,min(len(order)-1,target))
    order.insert(target,order.pop(index))
    return order


def current(demo):
    return validate_order(json.loads(demo.op("workflow_order").text))


def describe(demo):
    names = dict(zip(DEFAULT_ORDER,LABELS))
    return " -> ".join(names[n] for n in current(demo))


def apply_order(demo, order):
    order = validate_order(order)
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


def onPulse(par):
    demo = par.owner
    try:
        order = moved_order(current(demo),demo.par.Stageselection.eval(),par.name)
        apply_order(demo,order)
        demo.par.Orderstatus = "Order updated; effect settings retained. Capture Look to store in a cue."
    except Exception as exc:
        demo.par.Orderstatus = "Order unchanged: " + str(exc)
