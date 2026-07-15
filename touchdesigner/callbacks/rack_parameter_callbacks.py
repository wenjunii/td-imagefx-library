"""Parameter Execute DAT callbacks for swapping ImageFX Rack slots."""


def onValueChange(par, prev):
    if par.name.startswith("Slot") and par.name.endswith("effect"):
        slot_text = par.name[4:-6]
        if slot_text.isdigit():
            parent().LoadSlot(int(slot_text), par.eval())
    return


def onValuesChanged(changes):
    return


def onPulse(par):
    if par.name == "Reset":
        parent().Reset()
    return


def onExpressionChange(par, val, prev):
    return


def onExportChange(par, val, prev):
    return


def onEnableChange(par, val, prev):
    return


def onModeChange(par, val, prev):
    return
