"""File-backed main workflow source; retain the test shader and stable TOP name."""
import inspect
import re


PARAMETERS = (
    dict(name="Sourcemode", label="Source", type="menu", default="auto",
         menu_names=["auto", "file", "demo"],
         menu_labels=["Auto (File / Test Pattern)", "Image / Video File", "Test Pattern"]),
    dict(name="Sourcefile", label="Image / Video File", type="file", default="", animatable=False),
    dict(name="Sourcefit", label="Image Fit", type="menu", default="contain",
         menu_names=["contain", "cover", "stretch"], menu_labels=["Fit / Letterbox", "Fill / Crop", "Stretch"]),
    dict(name="Sourceanchor", label="Fit / Crop Anchor X / Y", type="xy", default=[.5, .5], min=0., max=1.),
    dict(name="Sourcebackground", label="Letterbox Color / Alpha", type="rgba", default=[0., 0., 0., 1.]),
    dict(name="Sourceplay", label="Video Play / Pause", type="toggle", default=True),
    dict(name="Sourceloop", label="Loop Video", type="toggle", default=True),
    dict(name="Sourcespeed", label="Video Speed / Reverse", type="float", default=1., min=-4., max=4.),
    dict(name="Sourcein", label="Start / Seek (Seconds)", type="float", default=0., min=0., max=86400., norm_max=60.),
    dict(name="Sourcerestart", label="Restart at Start / Seek", type="pulse"),
    dict(name="Sourcereload", label="Reload Media File", type="pulse"),
    dict(name="Sourcepreview", label="Preview Source", type="pulse"),
    dict(name="Sourcestatus", label="Media Status", type="string", default="", read_only=True, animatable=False),
)


def source_index(mode, file_path, show_runtime=False):
    """0: test pattern, 1: empty/background, 2: file. No hidden cue override."""
    if show_runtime or mode == "demo":
        return 0
    if str(file_path).strip():
        return 2
    return 1 if mode == "file" else 0


def fit_extent(image_size, canvas_size, fit):
    """Portable reference for the shader's aspect-preserving extent."""
    ratio = (max(1., image_size[0]) / max(1., image_size[1])) / (max(1., canvas_size[0]) / max(1., canvas_size[1]))
    if fit == "contain": return min(1., ratio), min(1., 1. / ratio)
    if fit == "cover": return max(1., ratio), max(1., 1. / ratio)
    return 1., 1.


RUNTIME = r'''
def selected(c):
    return source_index(c.par.Sourcemode.eval(), c.par.Sourcefile.eval(), c.fetch('imagefx_show_runtime', False))

def rendered(c):
    index = selected(c)
    return 1 if index == 2 and c.op('source_media_file').isInvalid else index

def status(c):
    if c.fetch('imagefx_show_runtime', False):
        return 'Show cue: set media and transport in Cue Editor, not Source Media'
    index = selected(c)
    if index == 0: return 'Test pattern (choose an image/video file to replace it)'
    if index == 1: return 'No file selected: showing letterbox background'
    reader = c.op('source_media_file')
    if reader.isInvalid: return 'ERROR: missing or unsupported media; check path / codec'
    if not reader.isOpen or not reader.isFullyPreRead: return 'Loading media...'
    return 'Ready: {} x {} | visual only; audio uses Show Control'.format(reader.width, reader.height)

def onValueChange(par, prev):
    c = par.owner
    if c.fetch('imagefx_show_runtime', False): return
    reader = c.op('source_media_file')
    if par.name in ('Sourcefile', 'Sourcemode') and selected(c) == 2:
        reader.preload()
        reader.par.cuepulse.pulse()
    elif par.name == 'Sourcein' and selected(c) == 2:
        reader.par.cuepulse.pulse()

def onPulse(par):
    c = par.owner
    if c.fetch('imagefx_show_runtime', False): return
    reader = c.op('source_media_file')
    if par.name == 'Sourcepreview': c.op('source_image').openViewer()
    elif selected(c) == 2:
        if par.name == 'Sourcerestart': reader.par.cuepulse.pulse()
        elif par.name == 'Sourcereload':
            reader.par.reloadpulse.pulse()
            reader.preload()
'''


MEDIA_SHADER = r'''
uniform vec4 uSource, uSourceAnchor, uSourceBackground;
void main() {
    if (uSource.x < 0.5) { imagefxTestPattern(); return; }
    if (uSource.x < 1.5) { fragColor = TDOutputSwizzle(uSourceBackground); return; }
    vec2 size = uTD2DInfos[0].res.zw;
    vec2 canvas = uTDOutputInfo.res.zw;
    float ratio = (size.x / max(size.y, 1.)) / (canvas.x / max(canvas.y, 1.));
    vec2 extent = vec2(1.);
    if (uSource.y < .5) extent = vec2(min(1., ratio), min(1., 1. / ratio));
    else if (uSource.y < 1.5) extent = vec2(max(1., ratio), max(1., 1. / ratio));
    vec2 uv = (vUV.st - (1. - extent) * uSourceAnchor.xy) / extent;
    if (any(lessThan(uv, vec2(0.))) || any(greaterThan(uv, vec2(1.)))) {
        fragColor = TDOutputSwizzle(uSourceBackground); return;
    }
    fragColor = TDOutputSwizzle(texture(sTD2DInputs[0], clamp(uv, 0., 1.)));
}
'''


def wrap_shader(original):
    """Keep the existing test-pattern pixels, alpha and QA fixture marker intact."""
    if "imagefxTestPattern" in original:
        raise ValueError("Source shader already has a media input")
    renamed, count = re.subn(r"\bvoid\s+main\s*\(\s*\)", "void imagefxTestPattern()", original)
    if count != 1:
        raise ValueError("Expected exactly one source shader main function")
    return renamed + "\n" + MEDIA_SHADER


def install(demo, source, shader, context):
    """Attach Source Media controls without changing any downstream connections."""
    import td
    if demo.op("source_media_runtime") is not None:
        raise ValueError("Source Media is already installed")
    page = demo.appendCustomPage("Source Media")
    for definition in PARAMETERS:
        context["_append_parameter"](demo, page, definition)
    runtime = demo.create(td.textDAT, "source_media_runtime")
    runtime.text = inspect.getsource(source_index) + "\n" + RUNTIME
    empty = demo.create(td.constantTOP, "source_media_empty")
    empty.par.outputresolution = "custom"
    empty.par.resolutionw = empty.par.resolutionh = 16
    empty.par.alpha = 0
    reader = demo.create(td.moviefileinTOP, "source_media_file")
    reader.par.file.expr = "parent().par.Sourcefile if parent().op('source_media_runtime').module.selected(parent()) == 2 else ''"
    reader.par.playmode = "sequential"
    reader.par.play.expr = "parent().par.Sourceplay and parent().op('source_media_runtime').module.selected(parent()) == 2"
    reader.par.speed.expr = "parent().par.Sourcespeed"
    reader.par.cuepointunit = "seconds"
    reader.par.cuepoint.expr = "parent().par.Sourcein"
    for par in (reader.par.textendleft, reader.par.textendright):
        par.expr = "'cycle' if parent().par.Sourceloop else 'hold'"
    reader.par.premultrgbbyalpha = "off"
    reader.par.alwaysloadinitial = True
    select = demo.create(td.switchTOP, "source_media_select")
    for i, node in enumerate((empty, reader)):
        node.outputConnectors[0].connect(select.inputConnectors[i])
    select.par.index.expr = "int(parent().op('source_media_runtime').module.rendered(parent()) == 2)"
    select.outputConnectors[0].connect(source.inputConnectors[0])
    shader.text = wrap_shader(shader.text)
    source.seq.vec.numBlocks = 4
    source.par.vec1name = "uSource"
    source.par.vec1valuex.expr = "parent().op('source_media_runtime').module.rendered(parent())"
    source.par.vec1valuey.expr = "parent().par.Sourcefit.menuIndex"
    source.par.vec2name = "uSourceAnchor"
    source.par.vec2valuex.expr = "parent().par.Sourceanchorx"
    source.par.vec2valuey.expr = "parent().par.Sourceanchory"
    source.par.vec3name = "uSourceBackground"
    for axis, suffix in zip("xyzw", "rgba"):
        source.par["vec3value" + axis].expr = "parent().par.Sourcebackground" + suffix
    callback = demo.create(td.parameterexecuteDAT, "source_media_callbacks")
    callback.text = "def onValueChange(par, prev):\n    parent().op('source_media_runtime').module.onValueChange(par, prev)\ndef onPulse(par):\n    parent().op('source_media_runtime').module.onPulse(par)\n"
    callback.par.op = ".."
    callback.par.custom = True
    callback.par.builtin = False
    callback.par.valuechange = True
    callback.par.onpulse = True
    callback.par.pars = "Sourcefile Sourcemode Sourcein Sourcerestart Sourcereload Sourcepreview"
    demo.par.Sourcestatus.expr = "me.op('source_media_runtime').module.status(me)"
    for par in page.pars:
        if not par.readOnly:
            par.enableExpr = "not me.fetch('imagefx_show_runtime', False)"
    for name in ("Sourceplay", "Sourceloop", "Sourcespeed", "Sourcein", "Sourcerestart", "Sourcereload"):
        demo.par[name].enableExpr += " and me.op('source_media_runtime').module.selected(me) == 2"
    demo.par.Sourceanchorx.enableExpr += " and me.par.Sourcefit != 'stretch'"
    demo.par.Sourceanchory.enableExpr += " and me.par.Sourcefit != 'stretch'"
    for i, node in enumerate((runtime, empty, reader, select, callback)):
        node.nodeX, node.nodeY = -900 + i * 160, 400
    source.comment = "Source Media controls are on parent imagefx_demo. Output follows HD / 4K / Custom; do not replace this TOP."
    source.cook(force=True)
    if source.errors():
        raise RuntimeError("Source Media shader failed: " + str(source.errors()))
    return source
