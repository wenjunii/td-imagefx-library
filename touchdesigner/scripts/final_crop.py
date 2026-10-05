"""Final GPU crop: bounded pixel geometry, aspect presets and fixed-canvas modes."""

RATIOS = {"free": None, "source": None, "16x9": 16/9, "9x16": 9/16,
          "1x1": 1., "4x3": 4/3, "3x4": 3/4, "21x9": 21/9,
          "4x5": 4/5, "5x4": 5/4, "3x2": 3/2, "2x3": 2/3, "custom": None}

PARAMETERS = (
    dict(name="Enabled", label="Module Enabled", page="Crop", type="toggle", default=True),
    dict(name="Aspect", label="Crop Aspect Ratio", page="Crop", type="menu", default="free",
         menu_names=list(RATIOS), menu_labels=["Free / Manual", "Same as Source", "16:9", "9:16", "1:1 Square", "4:3", "3:4", "21:9", "4:5", "5:4", "3:2", "2:3", "Custom Ratio"]),
    dict(name="Ratiowidth", label="Custom Ratio Width", page="Crop", type="float", default=16., min=.01, max=8192., norm_min=1., norm_max=32.),
    dict(name="Ratioheight", label="Custom Ratio Height", page="Crop", type="float", default=9., min=.01, max=8192., norm_min=1., norm_max=32.),
    *(dict(name=edge, label="Trim "+edge+" (%)", page="Crop", type="float", default=0., min=0., max=100.) for edge in ("Left", "Right", "Top", "Bottom")),
    dict(name="Anchor", label="Ratio Crop Position X / Y", page="Crop", type="xy", default=[.5,.5], min=0., max=1.),
    dict(name="Outputmode", label="Output Mode", page="Crop", type="menu", default="crop",
         menu_names=["crop", "mask", "fit"], menu_labels=["Crop to Size", "Mask Outside (Keep Canvas)", "Fit Crop (Keep Canvas)"], uniform="uMode"),
    dict(name="Status", label="Effective Crop / Output", page="Crop", type="string", default="", read_only=True, animatable=False),
    dict(name="Reset", label="Reset Crop", page="Crop", type="pulse"),
    dict(name="Preview", label="Preview Final Crop", page="Crop", type="pulse"),
)

# Embedded in a Text DAT so copied TOXs remain self-contained.
RUNTIME = r'''
import math

RATIOS = {'16x9':16/9, '9x16':9/16, '1x1':1., '4x3':4/3, '3x4':3/4,
          '21x9':21/9, '4x5':4/5, '5x4':5/4, '3x2':3/2, '2x3':2/3}

def bounded(value, low, high, fallback):
    value = float(value)
    return min(high, max(low, value)) if math.isfinite(value) else fallback

def geometry(width, height, aspect='free', ratio=(16.,9.), trims=(0.,0.,0.,0.), anchor=(.5,.5)):
    """trims = left, right, top, bottom; coordinates use bottom-left origin.

    Overlapping trims are scaled proportionally to retain at least one pixel.
    Aspect cropping fits inside the trimmed region, positioned by anchor.
    """
    width, height = max(1,int(width)), max(1,int(height))
    trims = [bounded(v,0.,100.,0.) for v in trims]
    def axis(size, low, high):
        a,b = size*low/100., size*high/100.
        scale = min(1., (size-1)/max(a+b,1e-12))
        a,b = int(a*scale), int(b*scale)
        return a, max(1,size-a-b), scale < 1.
    x,w,limited_x = axis(width,trims[0],trims[1])
    y,h,limited_y = axis(height,trims[3],trims[2])
    target = RATIOS.get(aspect)
    if aspect == 'source': target = width/height
    if aspect == 'custom':
        target = bounded(ratio[0],.01,8192.,16.)/bounded(ratio[1],.01,8192.,9.)
    cw,ch = w,h
    if target:
        if w/h > target: cw = max(1,min(w,int(h*target+1e-9)))
        else: ch = max(1,min(h,int(w/target+1e-9)))
    x += int((w-cw)*bounded(anchor[0],0.,1.,.5)+.5)
    y += int((h-ch)*bounded(anchor[1],0.,1.,.5)+.5)
    return dict(pixels=(x,y,cw,ch), uv=(x/width,y/height,(x+cw)/width,(y+ch)/height),
                size=(cw,ch), canvas=(width,height), limited=limited_x or limited_y)

def current(component):
    source = component.inputs[0] if component.inputs else None
    size = (source.width,source.height) if source is not None else (1920,1080)
    p = component.par
    return geometry(*size, aspect=p.Aspect.eval(), ratio=(p.Ratiowidth.eval(),p.Ratioheight.eval()),
                    trims=tuple(p[n].eval() for n in ('Left','Right','Top','Bottom')),
                    anchor=(p.Anchorx.eval(),p.Anchory.eval()))

def output_size(component):
    g = current(component)
    return g['size'] if component.par.Enabled and component.par.Outputmode.eval() == 'crop' else g['canvas']

def status(component):
    g = current(component)
    if not component.par.Enabled: return 'BYPASSED: full input'
    return 'Crop x={}, y={}, {} x {}; output {} x {}{}'.format(*g['pixels'], *output_size(component),
        ' (overlapping trims limited to retain pixels)' if g['limited'] else '')
'''

exec(RUNTIME)

CALLBACKS = r'''
def onPulse(par):
    component = par.owner
    if par.name == 'Preview': component.op('out1_image').openViewer()
    elif par.name == 'Reset':
        for name in ('Aspect','Ratiowidth','Ratioheight','Left','Right','Top','Bottom','Anchorx','Anchory','Outputmode'):
            component.par[name].val = component.par[name].default
'''

SHADER = r'''
layout(location=0) out vec4 fragColor;
uniform vec4 uBounds;
uniform float uMode;
uniform vec2 uCropSize;
void main() {
    vec2 uv=vUV.st;
    vec2 p=uv;
    float visible=1.;
    if(uMode>.5 && uMode<1.5) {
        visible=step(uBounds.x,uv.x)*step(uv.x,uBounds.z)*step(uBounds.y,uv.y)*step(uv.y,uBounds.w);
    } else {
        if(uMode>1.5) {
            float ratio=(uCropSize.x/max(uCropSize.y,1.))/(uTDOutputInfo.res.z/max(uTDOutputInfo.res.w,1.));
            p=(uv-.5)/vec2(min(1.,ratio),min(1.,1./ratio))+.5;
            visible=step(0.,p.x)*step(p.x,1.)*step(0.,p.y)*step(p.y,1.);
        }
        uv=mix(uBounds.xy,uBounds.zw,clamp(p,0.,1.));
    }
    fragColor=TDOutputSwizzle(texture(sTD2DInputs[0],uv)*visible);
}
'''
