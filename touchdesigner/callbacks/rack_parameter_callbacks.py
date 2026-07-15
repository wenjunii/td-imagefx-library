"""Parameter Execute DAT callbacks for the eight-slot ImageFX rack."""

import re


_SLOT_VALUE_RE = re.compile(r"^Slot([1-8])(effect|moddepth|modrate|modstate|bypass)$")
_SLOT_PULSE_RE = re.compile(r"^Slot([1-8])(up|down|reset|bypass)$")


def _rack():
    return parent()


def _callbacks_suspended(rack):
    try:
        return bool(rack.CallbacksSuspended)
    except Exception:
        return False


def _parameter_value(rack, name, default=""):
    try:
        parameter = rack.par[name]
    except Exception:
        return default
    if parameter is None:
        return default
    try:
        return parameter.eval()
    except Exception:
        return default


def _set_parameter(rack, name, value):
    try:
        parameter = rack.par[name]
    except Exception:
        return False
    if parameter is None:
        return False
    try:
        parameter.val = value
    except Exception:
        return False
    return True


def onValueChange(par, prev):
    rack = _rack()
    if _callbacks_suspended(rack):
        return
    match = _SLOT_VALUE_RE.fullmatch(par.name)
    if match is None:
        return

    index = int(match.group(1))
    field = match.group(2)
    value = par.eval()
    if field == "effect":
        rack.LoadSlot(index, value)
    elif field == "moddepth":
        rack.SetModulation(index, depth=value, update_parameters=False)
    elif field == "modrate":
        rack.SetModulation(index, rate=value, update_parameters=False)
    elif field == "modstate":
        rack.SetModulation(index, state=value, update_parameters=False)
    elif field == "bypass":
        rack.BypassSlot(index, value)
    return


def onValuesChanged(changes):
    for change in changes:
        if isinstance(change, (list, tuple)) and change:
            onValueChange(change[0], change[1] if len(change) > 1 else None)
        else:
            changed_parameter = getattr(change, "par", None)
            if changed_parameter is not None:
                onValueChange(changed_parameter, getattr(change, "prev", None))
    return


def onPulse(par):
    rack = _rack()
    if _callbacks_suspended(rack):
        return

    match = _SLOT_PULSE_RE.fullmatch(par.name)
    if match is not None:
        index = int(match.group(1))
        action = match.group(2)
        if action == "up":
            rack.MoveSlotUp(index)
        elif action == "down":
            rack.MoveSlotDown(index)
        elif action == "reset":
            rack.ResetSlot(index)
        else:
            rack.ToggleBypass(index)
        return

    if par.name == "Reset":
        rack.Reset()
    elif par.name == "Reloadall":
        rack.ReloadAll()
    elif par.name == "Bypassall":
        rack.BypassAll(True)
    elif par.name == "Enableall":
        rack.BypassAll(False)
    elif par.name == "Exportpreset":
        text = rack.ExportPreset(_parameter_value(rack, "Presetname", ""))
        _set_parameter(rack, "Presetjson", text)
    elif par.name == "Importpreset":
        rack.ImportPreset(_parameter_value(rack, "Presetjson", ""))
    elif par.name == "Savepreset":
        rack.SavePreset(
            _parameter_value(rack, "Presetpath", ""),
            _parameter_value(rack, "Presetname", ""),
        )
    elif par.name == "Loadpreset":
        rack.LoadPreset(_parameter_value(rack, "Presetpath", ""))
    return


def onExpressionChange(par, val, prev):
    return


def onExportChange(par, val, prev):
    return


def onEnableChange(par, val, prev):
    return


def onModeChange(par, val, prev):
    return
