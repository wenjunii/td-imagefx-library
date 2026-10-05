"""Embedded wall-output controller. Never opens a display on load/import."""
from __future__ import annotations


def _show(wall):
    return wall.parent().op("show_control")


def _source(wall, i):
    mode=wall.par.Sourcemode.eval()
    if mode == "show":
        show=_show(wall)
        return show.op("out{}_projector".format(i)) if show else None
    path=wall.par["Projector{}top".format(i) if mode=="independent" else "Mastertop"].eval().strip()
    source=wall.op(path) if path else None
    # Fail closed for missing/non-TOP/local feedback paths.
    if source is None or source.family != "TOP" or source.path.startswith(wall.path+"/"):
        return None
    return source


def source_path(wall, i):
    source=_source(wall,i)
    return source.path if source else "black"


def source_status(wall):
    sources=[_source(wall,i) for i in (1,2,3)]
    missing=[str(i+1) for i,s in enumerate(sources) if s is None]
    if missing: return "Missing/unsafe TOP for P"+", P".join(missing)+" (black fallback)"
    if wall.par.Sourcemode == "panoramic" and (sources[0].width,sources[0].height)!=(5760,1080):
        return "Panorama {}x{} scaled; prepare 5760x1080 for 1:1 pixels".format(sources[0].width,sources[0].height)
    if wall.par.Sourcemode == "show": return "Show Control: {} / three mapped feeds".format(_show(wall).par.Routingmode.eval())
    return "Sources OK / " + wall.par.Sourcemode.eval()


def blackout(wall):
    show=_show(wall)
    return bool(wall.par.Blackout or (wall.par.Sourcemode=="show" and show is not None and show.par.Masterblackout))


def _display_list():
    import td
    return [dict(index=m.index,width=m.width,height=m.height,primary=m.isPrimary,
                 name=m.displayName,refresh=getattr(m,"refreshRate",0)) for m in td.monitors]


def refresh_displays(wall):
    displays=_display_list()
    wall.par.Displays=" | ".join("{}: {}x{} {}{}".format(d["index"],d["width"],d["height"],d["name"]," PRIMARY" if d["primary"] else "") for d in displays)
    return displays


def display_problem(index, displays, allow_primary=False):
    selected=next((d for d in displays if d["index"]==index),None)
    if selected is None: return "Select a connected processor display index first."
    if (selected["width"],selected["height"])!=(3840,2160):
        return "Processor display must be 3840x2160 native pixels; currently {}x{}.".format(selected["width"],selected["height"])
    if selected["primary"] and not allow_primary:
        return "Primary/operator desktop is protected; choose the processor display."
    return ""


def check_display(wall):
    problem=display_problem(int(wall.par.Displayindex),refresh_displays(wall),bool(wall.par.Allowprimary))
    if problem: return problem
    out=wall.op("out1_wall_4k")
    out.cook(force=True)
    if (out.width,out.height)!=(3840,2160) or out.errors(recurse=True):
        return "4K TOP unavailable: check license, shaders and source errors."
    return ""


def display_changed(wall):
    # Never relocate a live fullscreen output while its display is being edited.
    wall.op("wall_window").par.winclose.pulse()
    wall.par.Status="Closed after display selection change; check before opening"


def safe_start(wall):
    wall.par.Blackout=True
    wall.par.Testpattern=False
    wall.op("wall_window").par.winclose.pulse()
    wall.par.Status="Wall window closed (safe startup)"
    refresh_displays(wall)


def action(wall,name):
    if name=="Closewall":
        wall.op("wall_window").par.winclose.pulse()
        wall.par.Status="Wall window closed"
    elif name in ("Checkdisplay","Openwall"):
        problem=check_display(wall)
        if problem:
            wall.par.Status="NOT OPENED: "+problem
        elif name=="Openwall":
            # Close only the legacy audience window from this demo, not other apps.
            show=_show(wall)
            if show: show.op("audience_window").par.winclose.pulse()
            wall.op("wall_window").par.performance.pulse()
            wall.par.Status="4K wall opened on display {}".format(int(wall.par.Displayindex))
        else: wall.par.Status="Display check passed: 3840x2160 native. Check processor 2x2 / no overscan."


def _channel(wall,name,format_spec):
    channel=wall.op("performance")[name]
    return format(float(channel[0]),format_spec) if channel is not None else "N/A"


def monitor_text(wall):
    show=_show(wall)
    lines=["PREVIEWS: 1 / LEFT | 2 / CENTER | 3 / RIGHT", "", "4 / CONFIDENCE MONITOR - NOT AN AUDIENCE OUTPUT", "",
           "FPS: {} | FRAME: {} ms | GPU: {} MB".format(_channel(wall,"fps",".1f"),_channel(wall,"msec",".2f"),_channel(wall,"gpu_mem_used",".0f")),
           "Dropped frames (last frame): {}".format(_channel(wall,"dropped_frames",".0f")),
           "PROJECTORS: {} | CALIBRATION: {}".format("BLACK" if blackout(wall) or not wall.par.Enabled else "LIVE","ON" if wall.par.Testpattern else "OFF"),
           source_status(wall)]
    if show:
        lines.extend(["SHOW: {} | TIME: {:.2f} s | SELECTED CUE: {}".format(show.par.Transport.eval(),float(show.par.Showtime),int(show.par.Selectedcue)),str(show.par.Status.eval())[:95]])
    lines.extend(["", "UHD 3840x2160 / TL=P1 TR=P2 BL=P3 BR=MONITOR", str(wall.par.Status.eval())[:95]])
    return "\n".join(lines)
