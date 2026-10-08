"""Off-air look navigation, installable without restarting ShowControlExt."""
import inspect


def target_definitions(order, labels):
    """Keep navigation aligned with the workflow; rack slots are individually editable."""
    return ([("workflow", ".", "Workflow / Module Switches")]
            + [(name, name, label) for name, label in zip(order, labels)]
            + [("rack_slot_{}".format(i), "fx_rack/slot{}".format(i),
                "FX Rack / Slot {}".format(i)) for i in range(1, 9)])


def active_deck(show):
    extension = show.ext.ShowControlExt
    if extension.engine.state != "stopped":
        raise ValueError("Stop All before editing a look")
    draft = extension._look_edit
    if not draft:
        raise ValueError("Select a visual cue and Recall Look first")
    deck = draft["deck"]
    if deck is None or deck != show.op("look_editor") or deck.path != show.path + "/look_editor":
        raise ValueError("The recalled look is unavailable; no main-workflow fallback is used")
    return deck


def control_target(show, selection=None):
    deck = active_deck(show)
    selection = show.par.Lookmodule.eval() if selection is None else selection
    paths = {name: path for name, path, label in TARGETS}
    if selection not in paths:
        raise ValueError("Choose an Effect Module from the menu")
    path = paths[selection]
    target = deck if path == "." else deck.op(path)
    if target is None:
        raise ValueError("This module/slot is empty in the recalled look: " + selection)
    if target != deck and not target.path.startswith(deck.path + "/"):
        raise ValueError("Edit Controls only opens modules in the recalled look")
    return target


def open_controls(show):
    target = control_target(show)
    pages = target.customPages
    # Built-in Base/Layout pages can be empty on these components. Start on a
    # useful custom page, but retain an operator's previously selected tab.
    if pages and str(target.currentPage) not in [str(page) for page in pages]:
        target.currentPage = pages[0]
    target.openParameters()
    return target


def open_preview(show):
    preview = active_deck(show).op("out1_image")
    if preview is None:
        raise ValueError("The recalled look has no output preview")
    preview.openViewer()
    return preview


def on_pulse(show, action):
    actions = {"Editlookcontrols": open_controls, "Openlookpreview": open_preview}
    if action not in actions:
        return False
    try:
        target = actions[action](show)
        show.par.Lookcontrolstatus = "OFF-AIR: " + target.path
        return True
    except Exception as exc:
        show.par.Lookcontrolstatus = str(exc)
        return False


CALLBACKS = """def onPulse(par):
    parent().op('look_editor_controls').module.on_pulse(parent(), par.name)
    return
"""


def runtime_source(targets):
    functions = (active_deck, control_target, open_controls, open_preview, on_pulse)
    return "TARGETS = {!r}\n\n".format(targets) + "\n\n".join(
        inspect.getsource(function) for function in functions)


def install(show, order, labels):
    """Add navigation only; never initialize the extension or touch cue/deck state."""
    import td
    page = next((page for page in show.customPages if page.name == "Look Editor"), None)
    if page is None:
        raise ValueError("Show Control has no Look Editor page")
    actions = show.op("show_parameters")
    if actions is None or "def onPulse(par):\n" not in actions.text:
        raise ValueError("Show Control action callback is not compatible with the navigation installer")
    # The original callback listens to every pulse; don't send navigation
    # actions to its playback dispatcher as well (it reports Unknown action).
    guard = "    if par.name in ('Editlookcontrols', 'Openlookpreview'):\n        return\n"
    if guard not in actions.text:
        actions.text = actions.text.replace("def onPulse(par):\n", "def onPulse(par):\n" + guard, 1)
    targets = target_definitions(order, labels)
    menu = getattr(show.par, "Lookmodule", None)
    if menu is None:
        menu = page.appendMenu("Lookmodule", label="Effect Module")[0]
        menu.menuNames = [name for name, path, label in targets]
        menu.menuLabels = [label for name, path, label in targets]
        menu.default = "calligraphic_shadow"
        menu.val = "calligraphic_shadow"
    else:
        selected = menu.eval()
        menu.menuNames = [name for name, path, label in targets]
        menu.menuLabels = [label for name, path, label in targets]
        menu.val = selected if selected in menu.menuNames else "calligraphic_shadow"
    menu.enableExpr = "bool(me.par.Lookediting)"
    for name, label in (("Editlookcontrols", "Edit Controls"), ("Openlookpreview", "Open Preview")):
        parameter = getattr(show.par, name, None)
        if parameter is None:
            parameter = page.appendPulse(name, label=label)[0]
        parameter.enableExpr = "bool(me.par.Lookediting)"
    status = getattr(show.par, "Lookcontrolstatus", None)
    if status is None:
        status = page.appendStr("Lookcontrolstatus", label="Controls Status")[0]
        status.val = "Recall Look > choose Effect Module > Edit Controls"
        status.readOnly = True
    runtime = show.op("look_editor_controls")
    if runtime is None:
        runtime = show.create(td.textDAT, "look_editor_controls")
    runtime.text = runtime_source(targets)
    callback = show.op("look_editor_controls_callbacks")
    if callback is None:
        callback = show.create(td.parameterexecuteDAT, "look_editor_controls_callbacks")
    callback.par.active = False
    callback.par.op = ".."
    callback.par.custom = True
    callback.par.builtin = False
    callback.par.pars = "Editlookcontrols Openlookpreview"
    callback.par.valuechange = False
    callback.par.onpulse = True
    callback.text = CALLBACKS
    callback.par.active = True
    for index, text in enumerate(("Look Editor > Effect Module > Edit Controls",
                                  "Open Preview > Update / Save New / Cancel")):
        hint = show.op("look_help_{}".format(index))
        if hint is not None:
            hint.par.text = text
    inspector = show.op("cue_inspector")
    if inspector is not None:
        # Parameter COMPs cache the parameter list; adding custom parameters to
        # the target doesn't refresh an already-open panel until it is rebound.
        source = inspector.par.op.eval()
        inspector.par.op = ""
        inspector.cook(force=True)
        inspector.par.op = source
        inspector.cook(force=True)
    return runtime
