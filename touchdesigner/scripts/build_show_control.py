"""Build the local cue workstation inside the existing demo (called by builder)."""

from __future__ import annotations

import json


MAPPING_SHADER = r'''
layout(location=0) out vec4 fragColor;
uniform vec4 uRow0, uRow1, uRow2, uCrop, uGrade, uEdges, uTransform;
void main() {
    vec3 q = vec3(vUV.st, 1.0);
    float divisor = dot(uRow2.xyz, q);
    vec2 uv = vec2(dot(uRow0.xyz,q), dot(uRow1.xyz,q)) / max(divisor, 0.000001);
    float inside = float(divisor > 0.0 && all(greaterThanEqual(uv,vec2(0))) && all(lessThanEqual(uv,vec2(1))));
    vec2 local = uv;
    float angle = radians(uTransform.x);
    uv = mat2(cos(angle),sin(angle),-sin(angle),cos(angle)) * (uv - 0.5) + 0.5;
    if (uTransform.y > 0.5) uv.x = 1.0 - uv.x;
    if (uTransform.z > 0.5) uv.y = 1.0 - uv.y;
    inside *= float(all(greaterThanEqual(uv,vec2(0))) && all(lessThanEqual(uv,vec2(1))));
    vec2 sourceUV = mix(uCrop.xy, uCrop.zw, uv);
    vec3 color = texture(sTD2DInputs[0], sourceUV).rgb;
    if (uGrade.w > 0.5) {
        vec2 grid = abs(fract(uv * vec2(16,9)) - 0.5);
        float line = float(max(grid.x,grid.y)>0.475);
        vec3 tint = uTransform.w < 1.5 ? vec3(0.65,0.12,0.12) : uTransform.w < 2.5 ? vec3(0.12,0.65,0.12) : vec3(0.12,0.24,0.8);
        color = mix(tint,vec3(1),line);
    }
    float edge = 1.0;
    if (uEdges.x>0) edge *= smoothstep(0.0,uEdges.x,local.x);
    if (uEdges.y>0) edge *= smoothstep(0.0,uEdges.y,1.0-local.x);
    if (uEdges.z>0) edge *= smoothstep(0.0,uEdges.z,local.y);
    if (uEdges.w>0) edge *= smoothstep(0.0,uEdges.w,1.0-local.y);
    color = pow(max(color*uGrade.x,vec3(0)),vec3(1.0/max(uGrade.y,0.1)));
    fragColor = TDOutputSwizzle(vec4(color*inside*edge*(1.0-uGrade.z),1));
}
'''

BLEND_SHADER = r'''
layout(location=0) out vec4 fragColor;
uniform vec4 uBlend;
void main(){fragColor=TDOutputSwizzle(mix(texture(sTD2DInputs[0],vUV.st),texture(sTD2DInputs[1],vUV.st),uBlend.x)*uBlend.y);}
'''

ATLAS_SHADER = r'''
layout(location=0) out vec4 fragColor;
uniform vec4 uWidths, uHeights;
void main(){
    float total=uWidths.x+uWidths.y+uWidths.z;
    float x=vUV.x*total;
    float y=vUV.y*max(uHeights.x,max(uHeights.y,uHeights.z));
    vec4 c;
    if(x<uWidths.x)c=y<uHeights.x?texture(sTD2DInputs[0],vec2(x/uWidths.x,y/uHeights.x)):vec4(0);
    else if(x<uWidths.x+uWidths.y)c=y<uHeights.y?texture(sTD2DInputs[1],vec2((x-uWidths.x)/uWidths.y,y/uHeights.y)):vec4(0);
    else c=y<uHeights.z?texture(sTD2DInputs[2],vec2((x-uWidths.x-uWidths.y)/uWidths.z,y/uHeights.z)):vec4(0);
    fragColor=TDOutputSwizzle(c);
}
'''


def build_show_control(demo, context):
    import td
    from tdimagefx.show import new_cue, SHOW_KIND
    context = dict(context)
    for name in ("containerCOMP", "textDAT", "glslTOP", "constantTOP", "selectTOP", "outTOP", "windowCOMP", "constantCHOP", "mathCHOP", "audiodeviceoutCHOP", "tableDAT", "textCOMP", "buttonCOMP", "panelexecuteDAT", "parameterCOMP", "parameterexecuteDAT", "executeDAT"):
        context[name] = getattr(td, name)
    # Snapshot before adding show_control, preventing recursive nested copies.
    template = demo.parent().copy(demo, name="_show_template_transaction")
    template.allowCooking = False
    show = demo.create(context["containerCOMP"], "show_control")
    show.nodeX, show.nodeY = 400, -1000
    show.par.w, show.par.h = 1440, 900
    show.color = (0.08, 0.35, 0.42)
    show.comment = "ImageFX Show Control: select a cue, edit its parameters, Apply Cue, Preload, GO. Outputs/audio are off on startup."
    try:
        copied = show.copy(template, name="deck_template")
        copied.allowCooking = False
    finally:
        template.destroy()
    append = context["_append_parameter"]

    def parameter(page, name, kind="float", default=0, minimum=0, maximum=1, **extra):
        pages = {p.name: p for p in show.customPages}
        page_obj = pages.get(page) or show.appendCustomPage(page)
        definition = dict(name=name, type=kind, default=default, min=minimum, max=maximum, **extra)
        append(show, page_obj, definition)

    def menu(page, name, values, default, **extra):
        parameter(page, name, "menu", default, menu_names=values, menu_labels=[v.replace("_", " ").title() for v in values], **extra)

    parameter("Transport", "Libraryroot", "folder", str(context["PROJECT_ROOT"]), read_only=True)
    parameter("Transport", "Showfile", "file", str(context["PROJECT_ROOT"] / ".imagefx" / "shows" / "current.json"), label="Show File (local JSON)")
    parameter("Transport", "Selectedcue", "int", 1, 1, 1000, label="Selected Cue Number")
    parameter("Transport", "Cuepage", "int", 1, 1, 84, label="Cue List Page (12 per page)")
    for name, label in (
        ("Gocue", "GO"), ("Pause", "Pause All"), ("Resume", "Resume All"), ("Stopcue", "Stop Selected Cue"),
        ("Stopall", "STOP ALL"), ("Preload", "Preload Selected"), ("Preflight", "Check Media Files"),
        ("Saveshow", "Save Show"), ("Loadshow", "Load Show"), ("Selectcue", "Load Selected Cue Details"),
        ("Openoutputs", "Open Audience Canvas"), ("Closeoutputs", "Close Audience Canvas"),
    ):
        parameter("Transport", name, "pulse", label=label)
    parameter("Transport", "Masterblackout", "toggle", True, label="Master Blackout")
    parameter("Transport", "Audioenabled", "toggle", False, label="Enable Stereo Audio Output")
    parameter("Transport", "Audiomute", "toggle", False, label="Master Audio Mute")
    parameter("Transport", "Mastervolume", default=0.7, label="Master Stereo Level")
    parameter("Transport", "Status", "string", "Ready; audience blackout on and audio off", read_only=True)
    parameter("Transport", "Transport", "string", "stopped", read_only=True)
    parameter("Transport", "Showtime", default=0, maximum=86400, read_only=True, label="Show Time (seconds)")

    parameter("Cue Editor", "Cuename", "string", "New cue", label="Cue Name")
    menu("Cue Editor", "Cuekind", ["visual", "audio", "parameters", "stop", "wait"], "visual", label="Cue Type")
    parameter("Cue Editor", "Cueenabled", "toggle", True, label="Cue Enabled")
    parameter("Cue Editor", "Mediafile", "file", "", label="Image / Video / Audio File")
    parameter("Cue Editor", "Track", "int", 1, 1, 3, label="Visual / Audio Track")
    parameter("Cue Editor", "Timestamp", "string", "", label="Show Timestamp (blank = manual GO)")
    for name, default, label in (("Prewait",0,"Pre-wait Seconds"),("Duration",10,"Duration (0 = indefinite)"),("Fade",1,"Fade Seconds"),("Postwait",0,"Post-wait Seconds"),("Mediain",0,"Media In Point (seconds)")):
        parameter("Cue Editor", name, default=default, maximum=86400,
                  norm_max=300 if name in {"Duration", "Mediain"} else 10, label=label)
    menu("Cue Editor", "Follow", ["manual", "continue", "follow"], "manual", label="Next Cue Behavior")
    parameter("Cue Editor", "Loop", "toggle", False, label="Loop Media")
    parameter("Cue Editor", "Movieaudio", "toggle", False, label="Use Video's Embedded Audio")
    parameter("Cue Editor", "Hold", "toggle", True, label="Hold Visual At End")
    parameter("Cue Editor", "Speed", default=1, minimum=0.1, maximum=4, label="Video Playback Speed")
    parameter("Cue Editor", "Gain", default=0.7, label="Audio Cue Level")
    parameter("Cue Editor", "Target", "string", "calligraphic_shadow/Particleamount", label="Automation Target (module/Parameter)")
    parameter("Cue Editor", "Targetvalue", "string", "1.0", label="Target Value (number, true/false, or menu name)")
    menu("Cue Editor", "Easing", ["linear", "smooth"], "smooth")
    parameter("Cue Editor", "Notes", "string", "")
    for name, label in (("Applycue","Apply Cue Edits"),("Capturelook","Capture Demo Effects Into Cue"),("Addcue","Add Cue"),("Duplicatecue","Duplicate Cue"),("Removecue","Remove Cue"),("Cueup","Move Cue Up"),("Cuedown","Move Cue Down")):
        parameter("Cue Editor", name, "pulse", label=label)

    for name, label in (("Recalllook", "Recall Look (Off-Air)"), ("Updatelook", "Update Cue Look"),
                        ("Savelookasnew", "Save as New Cue"), ("Cancellook", "Cancel Changes")):
        parameter("Look Editor", name, "pulse", label=label)
    parameter("Look Editor", "Lookediting", "toggle", False, read_only=True, label="Look Draft Active")
    parameter("Look Editor", "Lookstatus", "string", "No look draft", read_only=True, label="Look Editor Status")

    menu("Routing", "Routingmode", ["identical", "panoramic", "independent"], "identical", label="Three-Output Content Mapping")
    parameter("Routing", "Renderwidth", "int", 1920, 320, 3840, label="Render Width Per Panel")
    parameter("Routing", "Renderheight", "int", 1080, 180, 2160, label="Render Height")
    parameter("Routing", "Panoramaoverlap", default=0, maximum=0.5, label="Panorama Shared Edge Overlap")
    parameter("Routing", "Testpattern", "toggle", False, label="Output Calibration Grid")
    parameter("Routing", "Windowx", "int", 1920, -32768, 32768, label="Audience Canvas Desktop X")
    parameter("Routing", "Windowy", "int", 0, -32768, 32768, label="Audience Canvas Desktop Y")
    parameter("Routing", "Mappingstatus", "string", "Mapping valid", read_only=True)
    for output in (1, 2, 3):
        page, prefix = "Output {}".format(output), "Output{}".format(output)
        parameter(page, prefix + "width", "int", 1920, 320, 3840, label="Output Width")
        parameter(page, prefix + "height", "int", 1080, 180, 2160, label="Output Height")
        parameter(page, prefix + "track", "int", output, 1, 3, label="Independent Mode Track")
        parameter(page, prefix + "blackout", "toggle", False, label="Output Blackout")
        parameter(page, prefix + "brightness", default=1, maximum=2, label="Brightness")
        parameter(page, prefix + "gamma", default=1, minimum=0.1, maximum=4, label="Gamma")
        for corner, default in (("bl",[0,0]),("br",[1,0]),("tr",[1,1]),("tl",[0,1])):
            parameter(page, prefix + corner, "xy", default, -1, 2, label={"bl":"Bottom Left","br":"Bottom Right","tr":"Top Right","tl":"Top Left"}[corner])
        for edge, default in (("left",0),("bottom",0),("right",1),("top",1)):
            parameter(page, prefix + "crop" + edge, default=default, label="Source Crop " + edge.title())
            parameter(page, prefix + "edge" + edge, default=0, maximum=0.45, label="Edge Fade " + edge.title())
        parameter(page, prefix + "rotate", default=0, minimum=-180, maximum=180, label="Rotation Degrees")
        parameter(page, prefix + "flipx", "toggle", False, label="Flip Horizontal")
        parameter(page, prefix + "flipy", "toggle", False, label="Flip Vertical")
    for track in (1, 2, 3):
        parameter("Runtime", "Track{}blend".format(track), default=0, read_only=True)
        parameter("Runtime", "Track{}visible".format(track), "toggle", False, read_only=True)

    def node(kind, name):
        return show.create(context[kind], name)

    def shader(name, text, inputs, width="1920", height="1080"):
        code = node("textDAT", name + "_shader")
        code.text = text
        result = node("glslTOP", name)
        result.par.pixeldat = result.relativePath(code)
        result.par.glslversion = "glsl460"
        result.par.outputresolution = "custom"
        result.par.resolutionw.expr = width
        result.par.resolutionh.expr = height
        for i, source in enumerate(inputs):
            source.outputConnectors[0].connect(result.inputConnectors[i])
        return result

    black = node("constantTOP", "black")
    black.par.colorr, black.par.colorg, black.par.colorb = 0, 0, 0
    black.par.outputresolution = "custom"
    black.par.resolutionw, black.par.resolutionh = 16, 16
    for track in (1, 2, 3):
        sources = []
        for side in (0, 1):
            source = node("selectTOP", "track{}_source{}".format(track, side))
            source.par.top = "black"
            sources.append(source)
        blend = shader("track{}".format(track), BLEND_SHADER, sources, "int(parent().par.Renderwidth * ((3-2*parent().par.Panoramaoverlap) if parent().par.Routingmode == 'panoramic' else 1))", "parent().par.Renderheight")
        blend.seq.vec.numBlocks = 1
        blend.par.vec0name = "uBlend"
        blend.par.vec0valuex.expr = "parent().par.Track{}blend".format(track)
        blend.par.vec0valuey.expr = "parent().par.Track{}visible".format(track)

    for output in (1, 2, 3):
        prefix = "Output{}".format(output)
        source = node("selectTOP", "output_source{}".format(output))
        source.par.top.expr = "'track' + str(int(parent().par.{}track)) if parent().par.Routingmode == 'independent' else 'track1'".format(prefix)
        mapped = shader("mapped{}".format(output), MAPPING_SHADER, [source], "parent().par.{}width".format(prefix), "parent().par.{}height".format(prefix))
        mapped.seq.vec.numBlocks = 7
        for index, name in enumerate(("uRow0", "uRow1", "uRow2", "uCrop", "uGrade", "uEdges", "uTransform")):
            mapped.par["vec{}name".format(index)] = name
        for i in range(3):
            mapped.par["vec{}value{}".format(i, "xyz"[i])] = 1
        # Committed together with the corner transform by UpdateMapping, so
        # invalid crops retain the last valid mapping instead of flipping it.
        mapped.par.vec3valuez = 1
        mapped.par.vec3valuew = 1
        expressions = (
            "parent().par.{}brightness".format(prefix), "parent().par.{}gamma".format(prefix),
            "max(parent().par.Masterblackout, parent().par.{}blackout)".format(prefix), "parent().par.Testpattern",
        )
        for axis, expression in zip("xyzw", expressions):
            mapped.par["vec4value" + axis].expr = expression
        for axis, edge in zip("xyzw", ("left", "right", "bottom", "top")):
            mapped.par["vec5value" + axis].expr = "parent().par.{}edge{}".format(prefix, edge)
        for axis, suffix in zip("xyz", ("rotate", "flipx", "flipy")):
            mapped.par["vec6value" + axis].expr = "parent().par.{}{}".format(prefix, suffix)
        mapped.par.vec6valuew = output
        out = node("outTOP", "out{}_projector".format(output))
        mapped.outputConnectors[0].connect(out.inputConnectors[0])
    atlas = shader("audience_atlas", ATLAS_SHADER, [show.op("mapped{}".format(i)) for i in (1,2,3)], "sum(int(parent().par['Output' + str(i) + 'width']) for i in (1,2,3))", "max(int(parent().par['Output' + str(i) + 'height']) for i in (1,2,3))")
    atlas.seq.vec.numBlocks = 2
    atlas.par.vec0name = "uWidths"
    atlas.par.vec1name = "uHeights"
    for axis, i in zip("xyz", (1,2,3)):
        atlas.par["vec0value" + axis].expr = "parent().par.Output{}width".format(i)
        atlas.par["vec1value" + axis].expr = "parent().par.Output{}height".format(i)
    window = node("windowCOMP", "audience_window")
    window.par.winop = "audience_atlas"
    window.par.size = "custom"
    window.par.justifyoffsetto = "primarydisplay"
    window.par.justifyv = "top"
    window.par.dpiscaling = "native"
    window.par.cursorvisible = "nocursor"
    window.par.winw.expr = "op('audience_atlas').width"
    window.par.winh.expr = "op('audience_atlas').height"
    window.par.winoffsetx.expr = "parent().par.Windowx"
    window.par.winoffsety.expr = "parent().par.Windowy"
    window.par.borders = False

    silence = node("constantCHOP", "silence")
    silence.par.name0 = "left"
    silence.par.value0 = 0
    silence.par.name1 = "right"
    silence.par.value1 = 0
    mixer = node("mathCHOP", "audio_mix")
    silence.outputConnectors[0].connect(mixer.inputConnectors[0])
    mixer.par.chopop = "add"
    master = node("mathCHOP", "audio_master")
    mixer.outputConnectors[0].connect(master.inputConnectors[0])
    master.par.gain.expr = "parent().par.Mastervolume * (0 if parent().par.Audiomute else 1)"
    audio_out = node("audiodeviceoutCHOP", "stereo_output")
    master.outputConnectors[0].connect(audio_out.inputConnectors[0])
    audio_out.par.active.expr = "parent().par.Audioenabled"
    audio_out.par.clampoutput = True
    parameter("Transport", "Audiodevice", "menu", "default", menu_names=["default"], menu_labels=["System Default"], label="Stereo Output Device")
    show.par.Audiodevice.menuSource = "me.op('stereo_output').par.device"
    audio_out.par.device.expr = "parent().par.Audiodevice"

    sample = new_cue()
    sample.update(name="Test pattern — Track 1", duration=0.0, fade=0.0)
    data = node("textDAT", "show_data")
    data.text = json.dumps({"kind": SHOW_KIND, "schema_version": 1, "cues": [sample], "mapping": {}}, indent=2)
    node("tableDAT", "cue_list")
    node("textDAT", "cue_text")
    node("selectTOP", "look_preview").par.top = "black"

    def ui_node(kind, name, x, y, w, h):
        item = node(kind, name)
        item.par.x, item.par.y, item.par.w, item.par.h = x, y, w, h
        return item

    title = ui_node("textCOMP", "header", 20, 840, 1380, 45)
    title.par.text = "IMAGEFX / SHOW CONTROL"
    status = ui_node("textCOMP", "status_display", 20, 794, 1380, 36)
    status.par.text.expr = "parent().par.Transport.eval().upper() + '   ' + format(parent().par.Showtime.eval(), '.2f') + ' s     ' + parent().par.Status.eval()"
    button_actions = (("Gocue","GO"),("Pause","Pause"),("Resume","Resume"),("Stopall","STOP ALL"),("Preload","Preload"),("Addcue","Add cue"),("Applycue","Apply edits"),("Capturelook","Capture look"))
    look_actions = (("Recalllook", "Recall Look"), ("Updatelook", "Update Cue"),
                    ("Savelookasnew", "Save as New Cue"), ("Cancellook", "Cancel Changes"))
    for index, (action, label) in enumerate(button_actions + look_actions):
        x, y, width = (20 + index * 112, 730, 106) if index < 8 else (20 + (index - 8) * 224, 178, 216)
        button = ui_node("buttonCOMP", "button_" + action.lower(), x, y, width, 44)
        button.par.label = label
        button.par.fontsize = 16
        button.store("show_action", action)
        callback = button.create(context["panelexecuteDAT"], "clicked")
        callback.par.panels = ".."
        callback.par.panelvalue = "lselect"
        callback.par.offtoon = True
        callback.text = "def onOffToOn(panelValue):\n    parent().parent().Action(parent().fetch('show_action'))\n    return\n"
    for row in range(12):
        cue_button = ui_node("buttonCOMP", "cue_row_{}".format(row), 20, 675-row*40, 880, 36)
        cue_button.par.label.expr = "parent().CueLabel({})".format(row)
        cue_button.par.fontsize = 16
        cue_button.store("cue_row", row)
        callback = cue_button.create(context["panelexecuteDAT"], "clicked")
        callback.par.panels = ".."
        callback.par.panelvalue = "lselect"
        callback.par.offtoon = True
        callback.text = "def onOffToOn(panelValue):\n    parent().parent().SelectRow(parent().fetch('cue_row'))\n    return\n"
    inspector = ui_node("parameterCOMP", "cue_inspector", 920, 20, 500, 750)
    inspector.par.op = ".."
    inspector.par.pagescope = "Transport 'Cue Editor' 'Look Editor' Routing 'Output 1' 'Output 2' 'Output 3'"
    inspector.par.pagenames = True
    preview = ui_node("containerCOMP", "look_preview_panel", 644, 20, 256, 144)
    preview.par.top = "look_preview"
    help_text = ui_node("textCOMP", "help", 20, 132, 604, 32)
    help_text.par.fontsize = 16
    help_text.par.wordwrap = True
    help_text.par.alignx = "left"
    help_text.par.aligny = "top"
    help_text.par.text.expr = "'OFF-AIR LOOK PREVIEW (silent) | ' + ('DRAFT ACTIVE' if parent().par.Lookediting else 'No draft')"
    for index, line in enumerate(("Recall Look > enter show_control/look_editor",
                                  "Edit its modules > Update / Save New / Cancel",
                                  "Save Show writes committed cues to disk.",
                                  "Guide: docs/show-control.md")):
        hint = ui_node("textCOMP", "look_help_{}".format(index), 20, 104 - index * 28, 604, 28)
        hint.par.fontsize = 16
        hint.par.alignx = "left"
        hint.par.text = line

    context["configure_extension"](show, "ShowControlExt", context["PROJECT_ROOT"] / "touchdesigner" / "extensions" / "ShowControlExt.py")
    callbacks = node("parameterexecuteDAT", "show_parameters")
    callbacks.par.op = ".."
    callbacks.par.pars = "*"
    callbacks.par.valuechange = True
    callbacks.par.onpulse = True
    callbacks.text = "def onPulse(par):\n    parent().Action(par.name)\n    return\ndef onValueChange(par, prev):\n    return\n"
    tick = node("executeDAT", "show_tick")
    tick.par.frameend = True
    tick.text = "def onFrameEnd(frame):\n    parent().Tick()\n    return\n"
    show.op("deck_template").allowCooking = False
    show.UpdateMapping()
    # Build AFTER the snapshot so cue decks never include physical output windows.
    wall_path = context["PROJECT_ROOT"] / "touchdesigner/scripts/wall_output.py"
    wall_scope = dict(context, __file__=str(wall_path), __name__="_imagefx_wall_builder")
    exec(compile(wall_path.read_text(encoding="utf-8"), str(wall_path), "exec"), wall_scope)
    wall_scope["build_wall_output"](demo, context)
    return show
