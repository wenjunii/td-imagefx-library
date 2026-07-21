"""Execute DAT callbacks that restore the ImageFX browser preview on startup."""


def _schedule_preview_reload():
    browser = parent()
    run(
        "op({!r}).UpdateSelection()".format(browser.path),
        delayFrames=1,
    )


def onStart():
    _schedule_preview_reload()
    return


def onCreate():
    _schedule_preview_reload()
    return


def onExit():
    return


def onFrameStart(frame):
    return


def onFrameEnd(frame):
    return


def onPlayStateChange(state):
    return


def onDeviceChange():
    return
