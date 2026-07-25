"""Parameter Execute DAT callbacks for the ImageFX Library COMP."""


def _set_error(library, message):
    try:
        library.par.Status = "Error: {}".format(message)
    except Exception:
        pass


def onPulse(par):
    library = parent()
    if str(par.name).replace("_", "").casefold() != "refreshcatalog":
        return
    try:
        library.RefreshCatalog()
    except Exception as exc:
        _set_error(library, exc)
    return


def onValueChange(par, prev):
    return


def onValuesChanged(changes):
    return


def onExpressionChange(par, val, prev):
    return


def onExportChange(par, val, prev):
    return


def onEnableChange(par, val, prev):
    return


def onModeChange(par, val, prev):
    return
