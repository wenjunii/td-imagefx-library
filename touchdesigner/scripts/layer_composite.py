"""Two-media, straight-alpha compositor with video transport and flicker."""


def control(name, label, page, default, minimum, maximum, **extra):
    return dict(name=name, label=label, page=page, type="float", default=default,
                min=minimum, max=maximum, **extra)


PARAMETERS = (
    dict(name="Enabled", label="Module Enabled", page="Images", type="toggle", default=True),
    dict(name="Backdropfile", label="Backdrop Image / Video (blank = Input 1)", page="Images", type="file", default="", animatable=False),
    dict(name="Topfile", label="Top Image / Video (blank = Input 2)", page="Images", type="file", default="", animatable=False),
    dict(name="Routingstatus", label="Output Status", page="Images", type="string", default="", read_only=True, animatable=False),
    dict(name="Backdropstatus", label="Backdrop Status", page="Images", type="string", default="", read_only=True, animatable=False),
    dict(name="Topstatus", label="Top Status", page="Images", type="string", default="", read_only=True, animatable=False),
    dict(name="Preview", label="Preview This Layer", page="Images", type="pulse"),
    dict(name="Backdropfit", label="Backdrop Fit", page="Images", type="menu", default="cover",
         menu_names=["stretch", "contain", "cover"], menu_labels=["Stretch", "Fit / Contain", "Fill / Crop"], uniform="uBackdropFit"),
    dict(name="Topfit", label="Top Image Fit", page="Images", type="menu", default="contain",
         menu_names=["stretch", "contain", "cover"], menu_labels=["Stretch", "Fit / Contain", "Fill / Crop"], uniform="uTopFit"),
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


STATUS = r'''
def status(component, prefix):
    field = prefix.capitalize() + 'file'
    if not component.par[field].eval().strip():
        port = 0 if prefix == 'backdrop' else 1
        return 'Using TOP input {}'.format(port+1) if len(component.inputs)>port else 'No file / transparent'
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
        if par.name == prefix+'file':
            if par.eval().strip():
                reader.preload()
                reader.par.cuepulse.pulse()
        elif par.name == prefix+'in' and component.par.Autotime:
            reader.par.cuepulse.pulse()
    return

def onPulse(par):
    component = par.owner
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


SHADER = r"""
layout(location=0) out vec4 fragColor;
uniform float uBackdropFit, uTopFit, uOpacity, uHue, uSaturation, uContrast;
uniform float uBrightness, uExposure, uInvert, uScale, uRotation;
uniform vec3 uTint;
uniform vec2 uPosition;
uniform float uFlickerEnabled, uFlickerMode, uFlickerRate, uFlickerDuty;
uniform float uFlickerMin, uFlickerSoftness, uPhase, uSeed, uTime;

vec2 fittedUV(vec2 p, vec2 imageSize, float mode) {
    float canvasAspect=uTDOutputInfo.res.z/max(uTDOutputInfo.res.w,1.);
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
    vec2 backUV=fittedUV(uv-.5,uTD2DInfos[0].res.zw,uBackdropFit);
    vec4 back=texture(sTD2DInputs[0],clamp(backUV,0.,1.))*inside(backUV);
    vec2 p=uv-.5-uPosition;
    float aspect=uTDOutputInfo.res.z/max(uTDOutputInfo.res.w,1.);
    p.x*=aspect;
    float angle=radians(-uRotation), cs=cos(angle), sn=sin(angle);
    p=mat2(cs,sn,-sn,cs)*p;
    p.x/=aspect;
    vec2 topUV=fittedUV(p/max(uScale,.05),uTD2DInfos[1].res.zw,uTopFit);
    vec4 top=texture(sTD2DInputs[1],clamp(topUV,0.,1.));
    vec3 color=top.rgb;
    if(abs(uHue)>.00001) color=hueRotate(color,uHue);
    color=mix(vec3(dot(color,vec3(.2126,.7152,.0722))),color,uSaturation);
    color=((color-.5)*uContrast+.5)*exp2(uExposure)+uBrightness;
    color=clamp(color*uTint,0.,1.);
    if(uInvert>.5) color=1.-color;
    float alpha=clamp(top.a*uOpacity*flicker()*inside(topUV),0.,1.);
    // Straight-alpha Porter-Duff Over; never invert or recolor the backdrop.
    float outAlpha=alpha+back.a*(1.-alpha);
    vec3 rgb=outAlpha>1e-7?(color*alpha+back.rgb*back.a*(1.-alpha))/outAlpha:vec3(0.);
    fragColor=TDOutputSwizzle(vec4(rgb,outAlpha));
}
"""
