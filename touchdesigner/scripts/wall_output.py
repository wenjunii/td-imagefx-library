"""Pixel-exact UHD 2x2 wall packer; embedded controller has no external deps.

Build after show_control so cue deck templates cannot contain output windows.
The coordinate contract is top-left based; TOP textures are bottom-left based.
"""
from __future__ import annotations

from pathlib import Path

WIDTH, HEIGHT = 3840, 2160
PANEL_WIDTH, PANEL_HEIGHT = 1920, 1080
QUADRANTS = ((0, 0), (1920, 0), (0, 1080), (1920, 1080))
SOURCE_MODES = ("show", "identical", "panoramic", "independent")


def quadrant_at(x, y):
    """Return 1..4 for integer pixels in the user's top-left-origin grid."""
    if not (0 <= x < WIDTH and 0 <= y < HEIGHT):
        raise ValueError("Pixel outside 3840x2160 canvas")
    return 1 + int(x >= PANEL_WIDTH) + 2 * int(y >= PANEL_HEIGHT)


PROJECTOR_SHADER = r'''
layout(location=0) out vec4 fragColor;
uniform vec4 uSource; // panorama, panel (0..2), fit (0 fit/1 fill/2 stretch), test
uniform vec4 uSafety; // enabled, blackout
void main(){
    vec2 uv=vUV.st;
    vec2 dim=vec2(textureSize(sTD2DInputs[0],0));
    if(uSource.x>.5) dim.x/=3.0;
    float ratio=(dim.x/max(dim.y,1.0))/(1920.0/1080.0);
    vec2 p=uv-.5;
    if(uSource.z<.5) { if(ratio>1.0) p.y*=ratio; else p.x/=ratio; }
    else if(uSource.z<1.5) { if(ratio>1.0) p.x/=ratio; else p.y*=ratio; }
    uv=p+.5;
    bool inside=all(greaterThanEqual(uv,vec2(0)))&&all(lessThanEqual(uv,vec2(1)));
    if(uSource.x>.5) uv.x=(uv.x+uSource.y)/3.0;
    vec3 col=inside?texture(sTD2DInputs[0],uv).rgb:vec3(0);
    if(uSource.w>.5){
        vec3 tint=uSource.y<.5?vec3(.65,.06,.05):(uSource.y<1.5?vec3(.05,.55,.1):vec3(.05,.16,.7));
        ivec2 px=ivec2(gl_FragCoord.xy);
        bool grid=(px.x%120<2)||(px.y%120<2);
        bool edge=px.x<4||px.x>=1916||px.y<4||px.y>=1076;
        col=grid?vec3(.7):tint;
        if(edge) col=vec3(1);
        // Asymmetric corner marks expose vertical/horizontal flips.
        if(px.x<70&&px.y>=1010) col=vec3(1,1,0);
        if(px.x>=1850&&px.y<70) col=vec3(0,1,1);
        vec4 label=texture(sTD2DInputs[1],vUV.st);
        col=mix(col,label.rgb,label.a);
    }
    if(uSafety.x<.5||uSafety.y>.5) col=vec3(0);
    fragColor=TDOutputSwizzle(vec4(col,1));
}
'''

MULTIVIEW_SHADER = r'''
layout(location=0) out vec4 fragColor;
void main(){
    vec2 uv=vUV.st;
    vec3 c;
    if(uv.x<1.0/3.0)c=texture(sTD2DInputs[0],vec2(uv.x*3.0,uv.y)).rgb;
    else if(uv.x<2.0/3.0)c=texture(sTD2DInputs[1],vec2(uv.x*3.0-1.0,uv.y)).rgb;
    else c=texture(sTD2DInputs[2],vec2(uv.x*3.0-2.0,uv.y)).rgb;
    fragColor=TDOutputSwizzle(vec4(c,1));
}
'''

MONITOR_SHADER = r'''
layout(location=0) out vec4 fragColor;
uniform vec4 uMonitor; // monitor enabled, stats enabled
void main(){
    ivec2 p=ivec2(gl_FragCoord.xy);
    vec3 c=vec3(0);
    if(uMonitor.x>.5){
        if(p.y>=720)c=texelFetch(sTD2DInputs[0],ivec2(p.x,p.y-720),0).rgb;
        else if(uMonitor.y>.5)c=texelFetch(sTD2DInputs[1],p,0).rgb;
    }
    fragColor=TDOutputSwizzle(vec4(c,1));
}
'''

PACK_SHADER = r'''
layout(location=0) out vec4 fragColor;
void main(){
    ivec2 p=ivec2(gl_FragCoord.xy);
    vec3 c;
    if(p.y>=1080){
        if(p.x<1920)c=texelFetch(sTD2DInputs[0],ivec2(p.x,p.y-1080),0).rgb;
        else c=texelFetch(sTD2DInputs[1],p-ivec2(1920,1080),0).rgb;
    }else{
        if(p.x<1920)c=texelFetch(sTD2DInputs[2],p,0).rgb;
        else c=texelFetch(sTD2DInputs[3],p-ivec2(1920,0),0).rgb;
    }
    fragColor=TDOutputSwizzle(vec4(c,1));
}
'''


def build_wall_output(demo, context):
    import td
    if demo.op("wall_output") is not None:
        raise RuntimeError("wall_output already exists; do not overwrite a configured output")
    wall = demo.create(td.baseCOMP, "wall_output")
    wall.nodeX, wall.nodeY = 800, -1000
    wall.color = (.12, .35, .5)
    wall.comment = "4K 2x2 wall: P1 TL / P2 TR / P3 BL / Confidence BR. Select parameters. Window starts CLOSED."
    append = context["_append_parameter"]

    def parameter(page, name, kind="float", default=0, **extra):
        pages = {p.name:p for p in wall.customPages}
        append(wall, pages.get(page) or wall.appendCustomPage(page), dict(name=name, type=kind, default=default, **extra))

    parameter("Sources", "Sourcemode", "menu", "show", menu_names=list(SOURCE_MODES), menu_labels=["Show Control (mapped outputs)","Identical (Master TOP)","Panoramic (Master TOP)","Independent (three TOPs)"])
    parameter("Sources", "Mastertop", "string", "../out1_image", label="Master / Panorama TOP Path")
    for i in (1,2,3):
        parameter("Sources", "Projector{}top".format(i), "string", "../out1_image", label="Projector {} TOP Path".format(i))
    parameter("Sources", "Fit", "menu", "fit", menu_names=["fit","fill","stretch"], menu_labels=["Fit (letterbox)","Fill (crop)","Stretch"])
    parameter("Wall Output", "Enabled", "toggle", True, label="Enable Projector Feeds")
    parameter("Wall Output", "Blackout", "toggle", True, label="Projector Blackout (keeps Q4)")
    parameter("Wall Output", "Testpattern", "toggle", False, label="Numbered Calibration Pattern")
    parameter("Wall Output", "Monitorenabled", "toggle", True, label="Enable Confidence Quadrant")
    parameter("Wall Output", "Showstats", "toggle", True, label="Show Diagnostics / Cue Status")
    parameter("Wall Output", "Displayindex", "int", -1, min=-1, max=31, label="4K Processor Display Index (-1 = unassigned)")
    parameter("Wall Output", "Allowprimary", "toggle", False, label="Allow Primary Display (use with care)")
    for name,label in (("Checkdisplay","Check Display / Refresh List"),("Openwall","OPEN 4K WALL (Perform Mode)"),("Closewall","CLOSE 4K WALL")):
        parameter("Wall Output",name,"pulse",label=label)
    parameter("Wall Output", "Status", "string", "Wall window closed; display not yet checked", read_only=True)
    parameter("Wall Output", "Displays", "string", "", read_only=True, label="Connected Displays")
    parameter("Wall Output", "Sourcesstatus", "string", "", read_only=True, label="Source Validation")

    controller = wall.create(td.textDAT, "controller")
    controller.text = (Path(context["PROJECT_ROOT"]) / "touchdesigner/scripts/wall_output_controller.py").read_text(encoding="utf-8")
    wall.par.Sourcesstatus.expr = "me.op('controller').module.source_status(me)"

    def shader(name, source, inputs, width, height):
        code = wall.create(td.textDAT,name+"_shader")
        code.text = source
        node = wall.create(td.glslTOP,name)
        node.par.pixeldat = node.relativePath(code)
        node.par.glslversion = "glsl460"
        node.par.outputresolution = "custom"
        node.par.resolutionw, node.par.resolutionh = width,height
        node.par.format = "rgba8fixed"
        # Upscaling must clamp at texel edges, not mix the picture with zero
        # outside the input. Letterboxing is handled explicitly in the shader.
        node.par.inputextenduv = "hold"
        if len(inputs)>3:
            # GLSL TOP's TOPs parameter supports >3 sources without the
            # three-connector limit, preserving the specified source order.
            node.par.tops=" ".join(node.relativePath(source) for source in inputs)
        else:
            for i, upstream in enumerate(inputs): upstream.outputConnectors[0].connect(node.inputConnectors[i])
        return node

    def text_top(name, value, width, height, fontsize=32):
        node = wall.create(td.textTOP,name)
        node.par.outputresolution = "custom"
        node.par.resolutionw, node.par.resolutionh = width,height
        node.par.text = value
        node.par.font = "Consolas"
        node.par.fontsizexunit = "pixels"
        node.par.fontsizex = fontsize
        return node

    black = wall.create(td.constantTOP,"black")
    black.par.colorr,black.par.colorg,black.par.colorb = 0,0,0
    black.par.resolutionw,black.par.resolutionh = 16,16
    black.par.outputresolution = "custom"
    feeds=[]
    for i,name in enumerate(("LEFT","CENTER","RIGHT"),1):
        source = wall.create(td.selectTOP,"source{}".format(i))
        source.par.top.expr = "op('controller').module.source_path(parent(),{})".format(i)
        label=text_top("test_label{}".format(i),"{} / PROJECTOR {} / {}\n1920 x 1080\nYELLOW = TOP LEFT   |   CYAN = BOTTOM RIGHT".format(i,i,name),1920,1080,48)
        feed=shader("projector{}".format(i),PROJECTOR_SHADER,[source,label],1920,1080)
        feed.seq.vec.numBlocks=2
        feed.par.vec0name="uSource"
        feed.par.vec0valuex.expr="int(parent().par.Sourcemode == 'panoramic')"
        feed.par.vec0valuey=i-1
        feed.par.vec0valuez.expr="parent().par.Fit.menuIndex"
        feed.par.vec0valuew.expr="parent().par.Testpattern"
        feed.par.vec1name="uSafety"
        feed.par.vec1valuex.expr="parent().par.Enabled"
        feed.par.vec1valuey.expr="op('controller').module.blackout(parent())"
        out=wall.create(td.nullTOP,"p{}_out".format(i))
        feed.outputConnectors[0].connect(out.inputConnectors[0])
        feeds.append(out)
    multi=shader("layout_multiview",MULTIVIEW_SHADER,feeds,1920,360)
    perf=wall.create(td.performCHOP,"performance")
    for name in ("fps","msec","gpumemused","droppedframes"):
        if perf.par[name] is not None: perf.par[name]=True
    stats=text_top("monitor_text","",1920,720,34)
    stats.par.text.expr="op('controller').module.monitor_text(parent())"
    stats.par.bgcolorr,stats.par.bgcolorg,stats.par.bgcolorb=0,0,0
    stats.par.bgalpha=1
    stats.par.alignx="left"
    stats.par.aligny="top"
    stats.par.positionx=24
    stats.par.positiony=-16
    monitor=shader("comp_monitor_out",MONITOR_SHADER,[multi,stats],1920,1080)
    monitor.seq.vec.numBlocks=1
    monitor.par.vec0name="uMonitor"
    monitor.par.vec0valuex.expr="parent().par.Monitorenabled"
    monitor.par.vec0valuey.expr="parent().par.Showstats"
    packed=shader("layout_master_4k",PACK_SHADER,feeds+[monitor],3840,2160)
    output=wall.create(td.outTOP,"out1_wall_4k")
    packed.outputConnectors[0].connect(output.inputConnectors[0])
    wall.par.opviewer="out1_wall_4k"
    window=wall.create(td.windowCOMP,"wall_window")
    window.par.winop="out1_wall_4k"
    window.par.justifyoffsetto="specifydisplay"
    window.par.display.expr="max(0,int(parent().par.Displayindex))"
    window.par.size="fill"
    window.par.dpiscaling="native"
    window.par.borders=False
    window.par.cursorvisible="nocursor"
    callbacks=wall.create(td.parameterexecuteDAT,"wall_parameters")
    callbacks.par.op=".."
    callbacks.par.pars="*"
    callbacks.par.onpulse=True
    callbacks.par.valuechange=True
    callbacks.text="def onPulse(par):\n    parent().op('controller').module.action(parent(),par.name)\n    return\ndef onValueChange(par,prev):\n    if par.name in ('Displayindex','Allowprimary'): parent().op('controller').module.display_changed(parent())\n    return\n"
    startup=wall.create(td.executeDAT,"safe_start")
    startup.par.start=True
    startup.text="def onStart():\n    parent().op('controller').module.safe_start(parent())\n    return\n"
    controller.module.refresh_displays(wall)
    for index,node in enumerate(wall.children):
        node.nodeX=(index%6)*180; node.nodeY=-(index//6)*130
    return wall
