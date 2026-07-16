"""Parameter Execute DAT callbacks for the ImageFX Browser COMP."""


def _set_error(browser, message):
    setter = getattr(browser, "_set_status", None)
    if callable(setter):
        setter(str(message), error=True)
        return
    try:
        browser.par.Status = "Error: {}".format(message)
    except Exception:
        pass


def _safe_action(browser, method_name, *args):
    """Invoke a promoted browser method without leaking UI callback errors."""
    try:
        method = getattr(browser, method_name)
        return method(*args)
    except Exception as exc:
        _set_error(browser, exc)
        return None


def onValueChange(par, prev):
    browser = parent()
    name = str(par.name).casefold()
    if name in {
        "search", "category", "tags", "favorites", "favoritesonly", "channel", "model",
        "capability", "inputreadiness", "availableinputs", "sortby",
    }:
        _safe_action(browser, "ApplyFilters")
    elif name in {"selectedid", "selectedeffect", "selected"}:
        _safe_action(browser, "UpdateSelection")
    return


def onValuesChanged(changes):
    return


def onPulse(par):
    browser = parent()
    name = str(par.name).replace("_", "").casefold()
    if name == "refresh":
        _safe_action(browser, "Refresh")
    elif name == "create":
        _safe_action(browser, "CreateSelected")
    elif name == "togglefavorite":
        _safe_action(browser, "ToggleFavorite")
    return


def onExpressionChange(par, val, prev):
    return


def onExportChange(par, val, prev):
    return


def onEnableChange(par, val, prev):
    return


def onModeChange(par, val, prev):
    return
