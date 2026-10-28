"""Two-media, straight-alpha compositor with video transport and flicker."""


def control(name, label, page, default, minimum, maximum, **extra):
    return dict(name=name, label=label, page=page, type="float", default=default,
                min=minimum, max=maximum, **extra)


SOURCE_NAMES = ["auto", "effects", "second", "file", "transparent", "effects_a", "effects_b"]
SOURCE_LABELS = ["Auto (File / Input)", "Effects Result (Input 1)", "Second TOP Input", "Image / Video File", "Transparent", "Independent Effects A", "Independent Effects B"]

PARAMETERS = (
    dict(name="Enabled", label="Module Enabled", page="Images", type="toggle", default=True),
    dict(name="Backdropsource", label="Backdrop Source", page="Images", type="menu", default="auto", menu_names=SOURCE_NAMES, menu_labels=SOURCE_LABELS),
    dict(name="Backdropfile", label="Backdrop Image / Video File", page="Images", type="file", default="", animatable=False),
    dict(name="Topsource", label="Top Source", page="Images", type="menu", default="auto", menu_names=SOURCE_NAMES, menu_labels=SOURCE_LABELS),
    dict(name="Topfile", label="Top Image / Video File", page="Images", type="file", default="", animatable=False),
    dict(name="Routingstatus", label="Output Status", page="Images", type="string", default="", read_only=True, animatable=False),
    dict(name="Backdropstatus", label="Backdrop Status", page="Images", type="string", default="", read_only=True, animatable=False),
    dict(name="Topstatus", label="Top Status", page="Images", type="string", default="", read_only=True, animatable=False),
    dict(name="Preview", label="Preview This Layer", page="Images", type="pulse"),
    dict(name="Setupab", label="Use A as Backdrop + B as Top", page="Images", type="pulse"),
    dict(name="Edita", label="Edit Independent Effects A", page="Images", type="pulse"),
    dict(name="Editb", label="Edit Independent Effects B", page="Images", type="pulse"),
    dict(name="Abmedia", label="Choose A / B Images or Videos", page="Images", type="pulse"),
    dict(name="Backdropfit", label="Backdrop Fit", page="Images", type="menu", default="cover",
         menu_names=["stretch", "contain", "cover"], menu_labels=["Stretch", "Fit / Contain", "Fill / Crop"], uniform="uBackdropFit"),
    dict(name="Topfit", label="Top Image Fit", page="Images", type="menu", default="contain",
         menu_names=["stretch", "contain", "cover"], menu_labels=["Stretch", "Fit / Contain", "Fill / Crop"], uniform="uTopFit"),
    dict(name="Topcanvas", label="Top Canvas / Panoramic Placement", page="Top Placement", type="menu", default="full",
         menu_names=["full","left","center","right"], menu_labels=["Full Output Canvas","1080p — Left","1080p — Center","1080p — Right"], uniform="uTopCanvas"),
    control("Opacity", "Top Opacity (0 = Transparent)", "Top Color", 1., 0., 1., uniform="uOpacity"),
    dict(name="Tint", label="Top Color Tint", page="Top Color", type="rgb", default=[1.,1.,1.], uniform="uTint"),
    control("Hue", "Top Hue Rotation", "Top Color", 0., -180., 180., uniform="uHue"),
    control("Saturation", "Top Saturation", "Top Color", 1., 0., 3., uniform="uSaturation"),
    control("Contrast", "Top Contrast", "Top Color", 1., 0., 3., uniform="uContrast"),
    control("Brightness", "Top Brightness", "Top Color", 0., -1., 1., uniform="uBrightness"),
    control("Exposure", "Top Exposure (Stops)", "Top Color", 0., -4., 4., uniform="uExposure"),
    dict(name="Invert", label="Invert Top Colors", page="Top Color", type="toggle", default=False, uniform="uInvert"),
    dict(name="Position", label="Top Position X / Y", page="Top Placement", type="xy", default=[0.,0.], min=-1., max=1., uniform="uPosition"),
    control("Scale", "Top Scale", "Top Placement", 1., .05, 4., uniform="uScale"),
    control("Rotation", "Top Rotation", "Top Placement", 0., -180., 180., uniform="uRotation"),
    dict(name="Flickerenabled", label="Top Flicker Enabled", page="Flicker", type="toggle", default=False, uniform="uFlickerEnabled"),
    dict(name="Flickermode", label="Flicker Style", page="Flicker", type="menu", default="regular",
         menu_names=["regular", "soft", "random"], menu_labels=["Regular On / Off", "Soft Pulse", "Random On / Off"], uniform="uFlickerMode"),
    control("Flickerrate", "Flicker Rate (Hz)", "Flicker", 1., 0., 20., uniform="uFlickerRate",
            description="Zero freezes the pattern at Phase. Fast flashing can affect photosensitive viewers; rehearse before public use."),
    control("Flickerduty", "Visible Fraction / Random Probability", "Flicker", .5, 0., 1., uniform="uFlickerDuty"),
    control("Flickermin", "Minimum Visibility", "Flicker", 0., 0., 1., uniform="uFlickerMin"),
    control("Flickersoftness", "Soft Pulse Edge", "Flicker", .5, .01, 1., uniform="uFlickerSoftness"),
    control("Phase", "Flicker Phase (Cycles)", "Flicker", 0., 0., 1., uniform="uPhase"),
    dict(name="Seed", label="Random Flicker Seed", page="Flicker", type="int", default=7, min=0, max=100000, uniform="uSeed"),
    dict(name="Autotime", label="Auto Time", page="Timing", type="toggle", default=True),
    control("Timescale", "Time Scale / Reverse", "Timing", 1., -5., 5.),
    control("Manualtime", "Manual Time", "Timing", 0., -100000., 100000., norm_min=0., norm_max=60.),
    control("Time", "Effective Time", "Timing", 0., -500000., 500000., read_only=True, animatable=False, uniform="uTime"),
)

for _prefix, _label in (("Backdrop", "Backdrop"), ("Top", "Top")):
    PARAMETERS += (
        dict(name=_prefix+"play", label=_label+" Play / Pause", page=_label+" Playback", type="toggle", default=True),
        dict(name=_prefix+"loop", label=_label+" Loop", page=_label+" Playback", type="toggle", default=True),
        control(_prefix+"speed", _label+" Speed / Reverse", _label+" Playback", 1., -4., 4.),
        control(_prefix+"in", _label+" Start / Seek (Seconds)", _label+" Playback", 0., 0., 86400., norm_max=60.),
        dict(name=_prefix+"restart", label="Restart "+_label, page=_label+" Playback", type="pulse"),
        dict(name=_prefix+"reload", label="Reload "+_label+" File", page=_label+" Playback", type="pulse"),
    )

for _prefix in ('A', 'B'):
    PARAMETERS += (
        dict(name=_prefix+'module', label='Effect Module / Slot '+_prefix, page='Effects '+_prefix,
             type='menu', default='workflow', menu_names=['workflow'],
             menu_labels=['Workflow / Module Switches'], animatable=False),
        dict(name=_prefix+'edit', label='Edit Selected '+_prefix+' Controls', page='Effects '+_prefix, type='pulse'),
        dict(name=_prefix+'workflow', label='Open '+_prefix+' Module Switches / Order', page='Effects '+_prefix, type='pulse'),
        dict(name=_prefix+'preview', label='Preview '+_prefix+' Result', page='Effects '+_prefix, type='pulse'),
    )
PARAMETERS += (dict(name='Editstatus', label='Editing Target / Status', page='Images',
                   type='string', default='Choose Effects A or Effects B > Effect Module > Edit Controls',
                   read_only=True, animatable=False),)


STATUS = r'''
import json

def edit_targets(component):
    workflow=component.parent().op('workflow')
    if workflow is None: return [('workflow','.','Workflow / Module Switches')]
    module=workflow.module
    return [('workflow','.','Workflow / Module Switches')] + [
        (name,name,label) for name,label in zip(module.DEFAULT_ORDER,module.LABELS)
        if name!='image_composition'] + [
        ('rack_slot_'+str(i),'fx_rack/slot'+str(i),'FX Rack / Slot '+str(i)) for i in range(1,9)]

def edit_target(component, prefix, selection=None):
    if prefix not in ('A','B'): raise ValueError('Choose branch A or B')
    composition=component.parent().op('image_composition')
    if composition is None: raise ValueError('Independent A/B editing is unavailable inside a branch')
    branch=composition.op(prefix.lower()+'_effects')
    if branch is None: raise ValueError('Independent branch '+prefix+' is missing')
    choice=component.par[prefix+'module'].eval() if selection is None else selection
    paths={name:path for name,path,label in edit_targets(component)}
    if choice not in paths: raise ValueError('Choose an effect module or slot from the menu')
    target=branch if paths[choice]=='.' else branch.op(paths[choice])
    if target is None: raise ValueError('This effect / rack slot is empty: '+choice)
    if target!=branch and not target.path.startswith(branch.path+'/'):
        raise ValueError('Editing must stay inside this independent branch')
    return target

def edit_action(component, prefix, action):
    try:
        target=edit_target(component,prefix,'workflow' if action in ('workflow','preview') else None)
        if action=='preview':
            target=target.op('out1_image')
            target.openViewer()
        else:
            pages=target.customPages
            if pages and str(target.currentPage) not in [str(p) for p in pages]: target.currentPage=pages[0]
            target.openParameters()
        component.par.Editstatus='Effects '+prefix+': '+target.path
        return target
    except Exception as exc:
        component.par.Editstatus=str(exc)
        return None

def branch_error(component):
    demo=component.parent()
    composition=demo.op('image_composition')
    if composition is None: return 'Independent A/B effects are available on the main workflow, not inside A/B branches'
    order=json.loads(demo.op('workflow_order').text)
    if order.index('image_composition')>order.index('layer_composite'):
        return 'Move Two-Image Composition before Layer Composite, or press Use A as Backdrop + B as Top'
    return ''

def branch_path(component, name):
    if branch_error(component): return 'transparent'
    return '../image_composition/'+name+'_effects/out1_image'

def source_index(selection, has_file, input_count, port):
    if selection == 'auto':
        return 2 if has_file else (1 if input_count > port else 0)
    if selection == 'file': return 2 if has_file else 0
    if selection == 'effects': return 3 if input_count > 0 else 0
    if selection == 'second': return 4 if input_count > 1 else 0
    if selection == 'effects_a': return 5
    if selection == 'effects_b': return 6
    return 0

def selected(component, prefix):
    field = prefix.capitalize()
    index=source_index(component.par[field+'source'].eval(),
                        bool(component.par[field+'file'].eval().strip()),
                        len(component.inputs), 0 if prefix == 'backdrop' else 1)
    if index in (5,6):
        composition=component.parent().op('image_composition')
        if composition is not None and not composition.par['Avisible' if index==5 else 'Bvisible']: return 0
    return index

def uses_file(component, prefix):
    return selected(component, prefix) == 2

def status(component, prefix):
    index = selected(component, prefix)
    if index == 0: return 'Transparent (no selected source)'
    if index in (5,6):
        error=branch_error(component)
        return 'ERROR: '+error if error else 'Using independent Effects '+('A' if index==5 else 'B')
    if index != 2:
        port = (0 if prefix == 'backdrop' else 1) if index == 1 else index-3
        return 'Using effects result / TOP input 1' if port == 0 else 'Using TOP input 2'
    reader = component.op(prefix + '_file')
    if reader.isInvalid:
        return 'ERROR: file missing or unsupported (check path / codec)'
    if not reader.isOpen or not reader.isFullyPreRead:
        return 'Loading media...'
    return 'Ready: {} x {}'.format(reader.width, reader.height)
'''

CALLBACKS = r'''
def onValueChange(par, prev):
    component = par.owner
    for prefix in ('Backdrop', 'Top'):
        reader = component.op(prefix.lower() + '_file')
        if par.name in (prefix+'file', prefix+'source'):
            if component.op('media_status').module.uses_file(component, prefix.lower()):
                reader.preload()
                reader.par.cuepulse.pulse()
        elif par.name == prefix+'in' and component.par.Autotime:
            reader.par.cuepulse.pulse()
    return

def onPulse(par):
    component = par.owner
    if par.name in ('Aedit','Bedit','Aworkflow','Bworkflow','Apreview','Bpreview','Edita','Editb'):
        prefix=par.name[-1].upper() if par.name.startswith('Edit') else par.name[0]
        action='edit' if par.name.startswith('Edit') else par.name[1:]
        component.op('media_status').module.edit_action(component,prefix,action)
        return
    if par.name in ('Setupab','Edita','Editb','Abmedia'):
        demo=component.parent(); composition=demo.op('image_composition')
        if composition is None: return
        if par.name=='Setupab':
            workflow=demo.op('workflow').module
            order=workflow.current(demo)
            if order.index('image_composition')>order.index('layer_composite'):
                order.remove('image_composition'); order.insert(order.index('layer_composite'),'image_composition')
                workflow.apply_order(demo,order)
            component.par.Backdropsource='effects_a'; component.par.Topsource='effects_b'
            composition.par.Avisible=True; composition.par.Bvisible=True
            component.par.Enabled=True
        elif par.name=='Abmedia': composition.openParameters()
        return
    if par.name == 'Preview':
        component.op('out1_image').openViewer()
        return
    for prefix in ('Backdrop', 'Top'):
        reader = component.op(prefix.lower() + '_file')
        if par.name == prefix+'restart' and component.par.Autotime:
            reader.par.cuepulse.pulse()
        elif par.name == prefix+'reload':
            reader.par.reloadpulse.pulse()
            if component.par[prefix+'file'].eval().strip(): reader.preload()
'''


def install_independent_sources(component):
    """Additive, copy-safe upgrade. The A/B effects are shared with Composition.

    Select TOPs fall back to transparent if workflow ordering would form a
    cycle. Existing source choices/media/effect controls remain unchanged.
    """
    import td
    for name in ('Backdropsource','Topsource'):
        selected=component.par[name].eval()
        component.par[name].menuNames=SOURCE_NAMES
        component.par[name].menuLabels=SOURCE_LABELS
        component.par[name].val=selected
    page=next(p for p in component.customPages if p.name=='Images')
    for definition in PARAMETERS:
        if definition['name'] in ('Setupab','Edita','Editb','Abmedia'):
            if component.par[definition['name']] is None:
                page.appendPulse(definition['name'],label=definition['label'])
            component.par[definition['name']].enableExpr="me.parent().op('image_composition') is not None"
    component.op('media_status').text=STATUS
    targets=component.op('media_status').module.edit_targets(component)
    for definition in PARAMETERS:
        name=definition['name']
        if not (definition['page'].startswith('Effects ') or name=='Editstatus'): continue
        target_page=next((p for p in component.customPages if p.name==definition['page']),None)
        if target_page is None: target_page=component.appendCustomPage(definition['page'])
        parameter=component.par[name]
        if parameter is None:
            method={'menu':'appendMenu','pulse':'appendPulse','string':'appendStr'}[definition['type']]
            parameter=getattr(target_page,method)(name,label=definition['label'])[0]
            if 'default' in definition: parameter.default=parameter.val=definition['default']
        if definition['type']=='menu':
            selection=parameter.eval()
            parameter.menuNames=[n for n,path,label in targets]
            parameter.menuLabels=[label for n,path,label in targets]
            parameter.val=selection if selection in parameter.menuNames else 'workflow'
        parameter.readOnly=definition.get('read_only',False)
        if name!='Editstatus': parameter.enableExpr="me.parent().op('image_composition') is not None"
    definition=next(d for d in PARAMETERS if d['name']=='Topcanvas')
    if getattr(component.par,'Topcanvas',None) is None:
        placement=next(p for p in component.customPages if p.name=='Top Placement')
        parameter=placement.appendMenu('Topcanvas',label=definition['label'])[0]
        parameter.menuNames=definition['menu_names']; parameter.menuLabels=definition['menu_labels']
        parameter.default=parameter.val='full'
    # Fixed 1080p areas always contain the original aspect ratio. Existing
    # full-canvas Fit/Crop/Stretch behavior remains unchanged.
    component.par.Topfit.enableExpr="me.par.Topcanvas=='full'"
    shader=component.op('effect_glsl_layer_composite')
    if shader is not None:
        shader.par.pixeldat.eval().text=SHADER
        names=[shader.par['vec{}name'.format(i)].eval() for i in range(shader.seq.vec.numBlocks)]
        index=names.index('uTopCanvas') if 'uTopCanvas' in names else len(names)
        if index==len(names): shader.seq.vec.numBlocks=index+1
        shader.par['vec{}name'.format(index)]='uTopCanvas'
        shader.par['vec{}valuex'.format(index)].expr='parent().par.Topcanvas.menuIndex'
    for index,name in enumerate(('a','b'),5):
        select=component.op('independent_'+name) or component.create(td.selectTOP,'independent_'+name)
        select.par.top.expr="parent().op('media_status').module.branch_path(parent(), '{}')".format(name)
        for prefix in ('backdrop','top'):
            select.outputConnectors[0].connect(component.op(prefix+'_source').inputConnectors[index])
    component.op('media_status').text=STATUS
    callback=component.op('media_callbacks'); callback.text=CALLBACKS
    callback.par.pars='Backdropfile Topfile Backdropsource Topsource Backdropin Topin Preview Backdroprestart Toprestart Backdropreload Topreload Setupab Edita Editb Abmedia Aedit Bedit Aworkflow Bworkflow Apreview Bpreview'


SHADER = r"""
layout(location=0) out vec4 fragColor;
uniform float uBackdropFit, uTopFit, uOpacity, uHue, uSaturation, uContrast;
uniform float uBrightness, uExposure, uInvert, uScale, uRotation;
uniform float uTopCanvas;
uniform vec3 uTint;
uniform vec2 uPosition;
uniform float uFlickerEnabled, uFlickerMode, uFlickerRate, uFlickerDuty;
uniform float uFlickerMin, uFlickerSoftness, uPhase, uSeed, uTime;

vec2 fittedUV(vec2 p, vec2 imageSize, float mode, vec2 canvasSize) {
    float canvasAspect=canvasSize.x/max(canvasSize.y,1.);
    float ratio=(imageSize.x/max(imageSize.y,1.))/canvasAspect;
    vec2 extent=vec2(1.);
    if(mode>.5 && mode<1.5) extent=vec2(min(ratio,1.),min(1./ratio,1.));
    else if(mode>1.5) extent=vec2(max(ratio,1.),max(1./ratio,1.));
    return p/extent+.5;
}
float inside(vec2 p) {
    return step(0.,p.x)*step(p.x,1.)*step(0.,p.y)*step(p.y,1.);
}
vec3 hueRotate(vec3 c, float degrees) {
    // Rotate in YIQ chroma space while preserving luminance.
    float y=dot(c,vec3(.299,.587,.114));
    vec2 iq=vec2(dot(c,vec3(.596,-.274,-.322)),dot(c,vec3(.211,-.523,.312)));
    float a=radians(degrees), cs=cos(a), sn=sin(a);
    iq=mat2(cs,sn,-sn,cs)*iq;
    return vec3(y+.956*iq.x+.621*iq.y,y-.272*iq.x-.647*iq.y,y-1.106*iq.x+1.703*iq.y);
}
float flicker() {
    if(uFlickerEnabled<.5) return 1.;
    float cycle=uTime*uFlickerRate+uPhase;
    float gate=1.;
    if(uFlickerDuty<=0.) gate=0.;
    else if(uFlickerDuty>=1.) gate=1.;
    else if(uFlickerMode>1.5) {
        float h=fract(sin((floor(cycle)+uSeed*17.31)*12.9898+78.233)*43758.5453);
        gate=h<uFlickerDuty?1.:0.;
    } else if(uFlickerMode>.5) {
        float distanceFromCenter=abs(fract(cycle)-.5);
        float halfWidth=uFlickerDuty*.5;
        gate=1.-smoothstep(halfWidth*(1.-uFlickerSoftness),halfWidth,distanceFromCenter);
    } else gate=fract(cycle)<uFlickerDuty?1.:0.;
    return mix(uFlickerMin,1.,gate);
}
void main() {
    vec2 uv=vUV.st;
    vec2 canvasSize=uTDOutputInfo.res.zw;
    vec2 backUV=fittedUV(uv-.5,uTD2DInfos[0].res.zw,uBackdropFit,canvasSize);
    vec4 back=texture(sTD2DInputs[0],clamp(backUV,0.,1.))*inside(backUV);
    vec2 topSize=canvasSize,topCenter=canvasSize*.5;
    if(uTopCanvas>.5){
        topSize=vec2(1920.,1080.)*min(1.,min(canvasSize.x/1920.,canvasSize.y/1080.));
        if(uTopCanvas<1.5)topCenter.x=topSize.x*.5;
        else if(uTopCanvas>2.5)topCenter.x=canvasSize.x-topSize.x*.5;
    }
    vec2 region=(uv*canvasSize-topCenter)/topSize;
    vec2 p=region-uPosition;
    float aspect=topSize.x/max(topSize.y,1.);
    p.x*=aspect;
    float angle=radians(-uRotation), cs=cos(angle), sn=sin(angle);
    p=mat2(cs,sn,-sn,cs)*p;
    p.x/=aspect;
    vec2 topUV=fittedUV(p/max(uScale,.05),uTD2DInfos[1].res.zw,uTopCanvas>.5?1.:uTopFit,topSize);
    vec4 top=texture(sTD2DInputs[1],clamp(topUV,0.,1.));
    vec3 color=top.rgb;
    if(abs(uHue)>.00001) color=hueRotate(color,uHue);
    color=mix(vec3(dot(color,vec3(.2126,.7152,.0722))),color,uSaturation);
    color=((color-.5)*uContrast+.5)*exp2(uExposure)+uBrightness;
    color=clamp(color*uTint,0.,1.);
    if(uInvert>.5) color=1.-color;
    float alpha=clamp(top.a*uOpacity*flicker()*inside(topUV)*inside(region+.5),0.,1.);
    // Straight-alpha Porter-Duff Over; never invert or recolor the backdrop.
    float outAlpha=alpha+back.a*(1.-alpha);
    vec3 rgb=outAlpha>1e-7?(color*alpha+back.rgb*back.a*(1.-alpha))/outAlpha:vec3(0.);
    fragColor=TDOutputSwizzle(vec4(rgb,outAlpha));
}
"""
