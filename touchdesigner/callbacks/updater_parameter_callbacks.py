"""Parameter Execute DAT callbacks for the generated Update Manager COMP."""


def onValueChange(par, prev):
    updater = parent()
    if par.name == "Autocheck":
        if bool(par.eval()):
            updater.StartAutoCheck()
        else:
            updater.StopAutoCheck()
    elif par.name == "Intervalhours" and bool(updater.par.Autocheck):
        updater.StopAutoCheck()
        updater.StartAutoCheck()
    return


def onValuesChanged(changes):
    return


def onPulse(par):
    if par.name == "Checkupdates":
        parent().CheckUpdates()
    return


def onExpressionChange(par, val, prev):
    return


def onExportChange(par, val, prev):
    return


def onEnableChange(par, val, prev):
    return


def onModeChange(par, val, prev):
    return
