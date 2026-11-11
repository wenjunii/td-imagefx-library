"""Build an isolated, adjustable backdrop audition in a blank TD session.

Existing ImageFX / harness / puppet sessions and existing destinations are
refused. Native files containing private media paths stay in ignored build/.
"""
from pathlib import Path
import json
import re

WARP_SHADER = r'''
layout(location=0) out vec4 fragColor;
uniform vec4 uMotion; // enabled*strength, radius, max displacement, diagnostic
uniform vec4 uImage;  // source aspect, output aspect, reserved, reserved
uniform vec4 uDancer;
uniform vec4 uPoint0; uniform vec4 uPoint1; uniform vec4 uPoint2;
uniform vec4 uPoint3; uniform vec4 uPoint4; uniform vec4 uPoint5;
uniform vec4 uPoint6; uniform vec4 uPoint7; uniform vec4 uPoint8;
uniform vec4 uPoint9; uniform vec4 uPoint10; uniform vec4 uPoint11;
vec4 sampleImage(vec2 uv) {
    vec2 fit=vec2(max(1.,uImage.y/uImage.x),max(1.,uImage.x/uImage.y));
    vec2 q=(uv-.5)*fit+.5;
    if(any(lessThan(q,vec2(0)))||any(greaterThan(q,vec2(1)))) return vec4(0,0,0,1);
    return texture(sTD2DInputs[0],clamp(q,0.,1.));
}
void main() {
    vec2 uv=vUV.st;
    vec4 points[12]=vec4[12](uPoint0,uPoint1,uPoint2,uPoint3,uPoint4,uPoint5,
        uPoint6,uPoint7,uPoint8,uPoint9,uPoint10,uPoint11);
    vec2 flow=vec2(0.); float normalization=0.; vec3 debug=vec3(0.);
    for(int i=0;i<12;i++) {
        vec2 delta=(uv-points[i].xy)*vec2(uImage.y,1.);
        float r=max(.01,uMotion.y);
        float weight=exp(-dot(delta,delta)/(2.*r*r));
        // Inactive joints must not attenuate another dancer's field.
        float enabledPoint=step(.0000001,length(points[i].zw));
        flow+=points[i].zw*weight;
        normalization+=weight*enabledPoint;
        float mark=1.-smoothstep(.007,.012,length(delta));
        debug+=mark*(i<6?vec3(.05,.9,1.):vec3(1.,.65,.05));
    }
    flow=flow/max(1.,normalization)*uMotion.x;
    flow*=min(1.,max(0.,uMotion.z)/max(.000001,length(flow)));
    // Bounded edge falloff keeps the original frame border anchored.
    vec2 edge=smoothstep(vec2(0.),vec2(.07),uv)*smoothstep(vec2(0.),vec2(.07),1.-uv);
    flow*=edge.x*edge.y;
    vec4 col=sampleImage(clamp(uv-flow,0.,1.));
    col.rgb=mix(col.rgb,clamp(debug,0.,1.),clamp(max(debug.r,max(debug.g,debug.b))*uMotion.w,0.,1.));
    fragColor=TDOutputSwizzle(col);
}
'''

COMPARE_SHADER = r'''
layout(location=0) out vec4 fragColor;
void main() {
    vec2 uv=vUV.st;
    vec3 rgb=uv.x<.5?texture(sTD2DInputs[0],vec2(uv.x*2.,uv.y)).rgb:
                         texture(sTD2DInputs[1],vec2((uv.x-.5)*2.,uv.y)).rgb;
    if(abs(uv.x-.5)<.001)rgb=vec3(.85);
    fragColor=TDOutputSwizzle(vec4(rgb,1.));
}
'''


def build(root, motion_file, backdrop, video, *, name='dance_driven_backdrop'):
    root = Path(root).resolve()
    host = op('/project1')
    if host is None or host.op(name) is not None:
        raise RuntimeError('A /project1 host without an existing backdrop audition is required')
    if host.op('td_imagefx') is not None or host.op('imagefx_demo') is not None:
        raise RuntimeError('Use a separate blank session; the production/harness project is preserved')
    if any(n.name.startswith('dance_puppet') for n in host.children):
        raise RuntimeError('Do not modify the rejected puppet prototype')
    for path in (motion_file, backdrop, video):
        if not Path(path).is_file():
            raise ValueError('Missing local input: '+str(path))
    builder_path = root/'touchdesigner/scripts/build_project.py'
    scope = dict(globals(), __file__=str(builder_path), __name__='imagefx_builder_import')
    exec(compile(builder_path.read_text(encoding='utf-8'), str(builder_path), 'exec'), scope)
    module = host.create(baseCOMP, name)
    module.nodeX, module.nodeY = 0, -480
    module.color = (.42, .10, .04)
    pages = {}

    def parameter(page, name, kind, value=None, low=None, high=None, label=None, readonly=False):
        definition = dict(name=name, type=kind, label=label or name, page=page, read_only=readonly)
        if value is not None:
            definition['default'] = value
        if low is not None:
            definition['min'] = low
        if high is not None:
            definition['max'] = high
        if page not in pages:
            pages[page] = module.appendCustomPage(page)
        return scope['_append_parameter'](module, pages[page], definition)

    parameter('Backdrop Motion', 'Enabled', 'toggle', True, label='Complete Module Enabled')
    parameter('Backdrop Motion', 'Motionenabled', 'toggle', True, label='Dancer Motion Enabled')
    parameter('Backdrop Motion', 'Shadowenabled', 'toggle', True, label='Calligraphic Shadow Enabled')
    parameter('Backdrop Motion', 'Strength', 'float', 1.2, 0., 3., 'Motion Strength')
    parameter('Backdrop Motion', 'Radius', 'float', .32, .02, 1., 'Influence Radius (Frame Height)')
    parameter('Backdrop Motion', 'Maxdisplacement', 'float', .18, 0., .5, 'Maximum Warp Distance')
    parameter('Backdrop Motion', 'Shadowresponse', 'float', .6, 0., 2., 'Movement Energy to Ink Flow')
    parameter('Backdrop Motion', 'Debug', 'toggle', False, label='Show Tracking Points (Preview Only)')
    for field, label in [('Preview','Open Backdrop'),('Compare','Open Side-by-Side Comparison'),('Resetmotion','Reset Motion Controls')]:
        parameter('Backdrop Motion', field, 'pulse', label=label)
    parameter('Media', 'Backdropfile', 'file', str(Path(backdrop).resolve()), label='Backdrop Image')
    parameter('Media', 'Useinput', 'toggle', False, label='Use Connected TOP Instead')
    parameter('Media', 'Referencevideo', 'file', str(Path(video).resolve()), label='Dance Video (Preview Only, Silent)')
    parameter('Media', 'Motionfile', 'file', '', label='Replacement Motion JSON')
    parameter('Media', 'Reloadmotion', 'pulse', label='Load Replacement Motion')
    parameter('Media', 'Reloadmedia', 'pulse', label='Reload Image / Preview Video')
    parameter('Playback', 'Playing', 'toggle', False)
    for field, label in [('Go','GO / Restart'),('Pause','Pause / Resume'),('Stop','Stop / Rewind')]:
        parameter('Playback',field,'pulse',label=label)
    parameter('Playback','Position','float',0.,0.,3600.,'Seek (Seconds)')
    parameter('Playback','Playbackspeed','float',1.,-2.,2.,'Playback Speed')
    parameter('Playback','Loop','toggle',False,label='Loop (Not Seamless)')
    parameter('Playback','Motionoffset','float',0.,-60.,60.,'Motion Sync Offset (Seconds)')
    parameter('Playback','Duration','float',0.,label='Clip Duration',readonly=True)
    parameter('Playback','Framerate','float',30.,label='Motion FPS',readonly=True)
    parameter('Playback','Status','string','Initializing',readonly=True)
    for field,label,value,low,high in (
        ('Posefollow','Pose / Position Follow',.7,0.,3.),
        ('Velocityresponse','Movement Velocity Response',.25,0.,1.),
        ('Smoothing','Motion Smoothing (Seconds)',.08,0.,.5),
        ('Confidence','Minimum Joint Confidence',.25,0.,1.),
        ('Bodyweight','Body Influence',1.,0.,3.),('Handweight','Hand Influence',1.2,0.,3.),
        ('Footweight','Foot Influence',.5,0.,3.),('Dancer1','Dancer 1 Influence',1.,0.,2.),
        ('Dancer2','Dancer 2 Influence',1.,0.,2.),('Referencepose','Neutral Pose Time',0.,0.,3600.)):
        parameter('Tracking',field,'float',value,low,high,label)
    parameter('Tracking','Setreference','pulse',label='Use Current Time as Neutral Pose')
    for field,label,value,low,high in (
        ('Stagezoom','Stage Mapping Zoom',1.7,.25,4.),
        ('Stagepanx','Stage Pan X',0.,-1.,1.),('Stagepany','Stage Pan Y',.08,-1.,1.)):
        parameter('Stage Mapping',field,'float',value,low,high,label)
    parameter('Stage Mapping','Mirror','toggle',False,label='Mirror Dancer Mapping')
    parameter('Stage Mapping','Energy1','float',0.,label='Dancer 1 Energy',readonly=True)
    parameter('Stage Mapping','Energy2','float',0.,label='Dancer 2 Energy',readonly=True)
    # Promote the entire original surface, except its redundant master toggle.
    for definition in scope['CALLIGRAPHIC_SHADOW_PARAMETER_DEFINITIONS']:
        if definition['name'] == 'Enabled':
            continue
        page = definition['page']
        if page not in pages:
            pages[page] = module.appendCustomPage(page)
        scope['_append_parameter'](module, pages[page], definition)
    module.par.Time.expr = 'me.par.Position * me.par.Timescale if me.par.Autotime else me.par.Manualtime'
    for filename, datname in [('dance_backdrop_motion.py','motion_math'),('dance_backdrop_runtime.py','runtime')]:
        dat = module.create(textDAT, datname)
        dat.text = (root/'touchdesigner/scripts'/filename).read_text(encoding='utf-8')
    data = module.create(textDAT,'motion_data')
    data.text = Path(motion_file).read_text(encoding='utf-8')
    module.op('motion_math').module.MotionClip(json.loads(data.text))
    source = module.create(inTOP,'in1_image')
    backdrop_top = module.create(moviefileinTOP,'backdrop_file')
    backdrop_top.par.file.expr = 'parent().par.Backdropfile'
    backdrop_top.par.play = False
    backdrop_top.par.alwaysloadinitial = True
    select = module.create(switchTOP,'source_select')
    backdrop_top.outputConnectors[0].connect(select.inputConnectors[0])
    source.outputConnectors[0].connect(select.inputConnectors[1])
    select.par.index.expr = 'int(parent().par.Useinput)'
    shader = module.create(textDAT,'warp_shader')
    shader.text = WARP_SHADER
    warp = module.create(glslTOP,'motion_warp')
    select.outputConnectors[0].connect(warp.inputConnectors[0])
    warp.par.pixeldat = 'warp_shader'
    warp.par.glslversion = 'glsl460'
    warp.par.compilebehavior = 'stalluntildone'
    warp.par.errorbehavior = 'showerror'
    warp.par.outputresolution = 'custom'
    warp.par.resolutionw = 1920
    warp.par.resolutionh = 1080
    warp.seq.vec.numBlocks = 15
    bindings = [
        ('uMotion', ['parent().par.Strength * parent().par.Motionenabled * parent().par.Enabled',
                     'parent().par.Radius','parent().par.Maxdisplacement','int(parent().par.Debug and parent().par.Enabled)']),
        ('uImage', ["op('source_select').width / max(1,op('source_select').height)",'1920/1080']),
        ('uDancer', ['parent().par.Dancer1','parent().par.Dancer2']),
    ]
    for i,(uniform,expressions) in enumerate(bindings):
        warp.par[f'vec{i}name'] = uniform
        for axis,expression in zip('xyzw',expressions):
            warp.par[f'vec{i}value{axis}'].expr = expression
    for i in range(12):
        warp.par[f'vec{i+3}name'] = f'uPoint{i}'
    calligraphy = module.loadTox(str(root/'touchdesigner/core/CalligraphicShadow.tox'))
    calligraphy.name = 'calligraphic_shadow'
    for par in calligraphy.customPars:
        if par.name == 'Enabled':
            par.expr = 'parent().par.Enabled and parent().par.Shadowenabled'
        elif par.name == 'Time':
            par.expr = 'parent().par.Time'
        elif module.par[par.name] is not None:
            par.expr = 'parent().par.'+par.name
    calligraphy.par.Stretch.expr = 'min(4.,parent().par.Stretch + parent().par.Shadowresponse * (parent().par.Energy1+parent().par.Energy2)/2 * parent().par.Motionenabled)'
    calligraphy.par.Turbulence.expr = 'min(.5,parent().par.Turbulence + .12 * parent().par.Shadowresponse * (parent().par.Energy1+parent().par.Energy2)/2 * parent().par.Motionenabled)'
    warp.outputConnectors[0].connect(calligraphy.inputConnectors[0])
    out = module.create(outTOP,'out1_image')
    calligraphy.outputConnectors[0].connect(out.inputConnectors[0])
    out.display = True
    out.render = True
    reference = module.create(moviefileinTOP,'reference_video')
    reference.par.file.expr = 'parent().par.Referencevideo'
    reference.par.playmode = 'specify'
    reference.par.indexunit = 'seconds'
    reference.par.index.expr = "parent().par.Position + parent().op('runtime').module.model(parent()).start"
    reference.par.play = True
    reference.par.alwaysloadinitial = True
    reference.par.textendleft = 'hold'
    reference.par.textendright = 'hold'
    comp_shader = module.create(textDAT,'compare_shader')
    comp_shader.text = COMPARE_SHADER
    comparison = module.create(glslTOP,'comparison')
    reference.outputConnectors[0].connect(comparison.inputConnectors[0])
    out.outputConnectors[0].connect(comparison.inputConnectors[1])
    comparison.par.pixeldat = 'compare_shader'
    comparison.par.outputresolution = 'custom'
    comparison.par.resolutionw = 1920
    comparison.par.resolutionh = 540
    module.par.opviewer = 'out1_image'
    module.viewer = True
    module.op('runtime').module.refresh(module)
    values = dict(Mix=.62, Maskmode='light', Threshold=.23, Softness=.10,
                  Paperamount=0., Sourceopacity=1., Shadowopacity=.65,
                  Offsetx=.055, Offsety=.025, Stretch=.85, Curl=.025,
                  Turbulence=.035, Noisescale=3.8, Traillength=.6, Speed=.24,
                  Diffusion=.2, Drybrush=.22, Splatter=.04, Glitteramount=.08,
                  Inkcolorr=.20, Inkcolorg=.004, Inkcolorb=.002,
                  Particlecolorr=1., Particlecolorg=.18, Particlecolorb=.025,
                  Glittercolorr=1., Glittercolorg=.65, Glittercolorb=.27)
    for key,value in values.items():
        module.par[key] = value
    buttons = module.create(parameterexecuteDAT,'buttons')
    buttons.par.op = '..'
    buttons.par.custom = True
    buttons.par.builtin = False
    buttons.par.pars = 'Go Pause Stop Preview Compare Setreference Resetmotion Reloadmotion Reloadmedia'
    buttons.par.valuechange = False
    buttons.par.onpulse = True
    buttons.text = "def onPulse(par):\n    parent().op('runtime').module.action(parent(),par.name)\n"
    changes = module.create(parameterexecuteDAT,'changes')
    changes.par.op = '..'
    changes.par.custom = True
    changes.par.builtin = False
    changes.par.pars = 'Position Playing Playbackspeed Loop Motionoffset Referencepose Smoothing Confidence Stagezoom Stagepanx Stagepany Mirror Posefollow Velocityresponse Bodyweight Handweight Footweight Dancer1 Dancer2'
    changes.par.valuechange = True
    changes.text = "def onValueChange(par,prev):\n    parent().op('runtime').module.changed(parent(),par.name)\n"
    timer = module.create(executeDAT,'tick')
    timer.par.framestart = True
    timer.par.start = True
    timer.text = "def onFrameStart(frame):\n    parent().op('runtime').module.tick(parent(),absTime.seconds)\ndef onStart():\n    parent().op('runtime').module.startup(parent())\n"
    readme = module.create(textDAT,'README')
    readme.text = ('DANCE-DRIVEN BACKDROP — audition, not yet routed into the live show.\n'
        'GO / Pause / Stop on Playback. Open Side-by-Side Comparison: dance left, backdrop right.\n'
        'All original Calligraphic Shadow parameters are on this outer component.\n'
        'Local 2D recorded joints drive the backdrop; no figures, no puppet rig, no live inference.\n'
        'The native files embed private motion data and refer to local private media. Do not publish them.\n'
        'Start paused. No audio, no audience windows, no canonical project changes.\n')
    for i,node in enumerate(module.children):
        node.nodeX,node.nodeY = (i%5)*240,-(i//5)*160
    for pane in ui.panes:
        if pane.type == 'NETWORKEDITOR':
            pane.owner = host
    module.currentPage = 'Backdrop Motion'
    module.current = True
    print('Built',module.path,'— paused, silent, separate from production')
    return module


def save_new(root, name='DanceDrivenBackdrop'):
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]*', name):
        raise ValueError('Choose a simple filename without directory components')
    root = Path(root).resolve()
    folder = root/'build/dance-backdrop'
    folder.mkdir(parents=True, exist_ok=True)
    toe,tox = folder/(name+'.toe'),folder/(name+'.tox')
    if toe.exists() or tox.exists() or any(folder.glob(name+'.[0-9]*.toe')):
        raise RuntimeError('Destination exists; choose a new name, never overwrite')
    if op('/project1/imagefx_demo') is not None or op('/project1/td_imagefx') is not None:
        raise RuntimeError('Refusing production/harness save')
    module = op('/project1/dance_driven_backdrop')
    if module is None:
        raise RuntimeError('Build and validate the module first')
    module.op('runtime').module.action(module,'Stop')
    module.par.Debug = False
    module.current = True
    module.currentPage = 'Playback'
    for pane in ui.panes:
        if pane.type == 'NETWORKEDITOR':
            pane.owner = module.parent()
    module.save(str(tox))
    if project.save(str(toe),saveExternalToxs=False) is not True:
        raise RuntimeError('Native project save not confirmed')
    if not toe.is_file() or not tox.is_file() or not toe.stat().st_size or not tox.stat().st_size:
        raise RuntimeError('Native save reported success but requested files are absent / empty')
    print('Saved new local files:',toe,tox)
    return str(toe)
