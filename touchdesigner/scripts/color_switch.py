"""Selective, soft-edged color replacement; no per-frame CPU pixel readback."""

PARAMETERS = (
    dict(name="Enabled", label="Color Switch Enabled", page="Color Switch", type="toggle", default=True),
    dict(name="Mix", label="Replacement Amount", page="Color Switch", type="float", default=1., min=0., max=1., uniform="uMix"),
    dict(name="Fromcolor", label="Color to Select", page="Color Switch", type="rgb", default=[1.,0.,0.], uniform="uFrom"),
    dict(name="Tocolor", label="Replace With Color", page="Color Switch", type="rgb", default=[0.,.5,1.], uniform="uTo"),
    dict(name="Matchmode", label="Match Method", page="Selection", type="menu", default="rgb", menu_names=["rgb","hue"], menu_labels=["RGB Color Distance","Hue (Across Shades)"], uniform="uMode"),
    dict(name="Tolerance", label="Color Tolerance", page="Selection", type="float", default=.12, min=0., max=1., uniform="uTolerance"),
    dict(name="Softness", label="Selection Edge Softness", page="Selection", type="float", default=.08, min=0., max=1., uniform="uSoftness"),
    dict(name="Minsaturation", label="Hue Mode Minimum Saturation", page="Selection", type="float", default=.1, min=0., max=1., uniform="uMinSaturation"),
    dict(name="Preserveshading", label="Preserve Original Shading", page="Color Switch", type="float", default=1., min=0., max=1., uniform="uPreserve"),
    dict(name="Showmask", label="Preview Selected Pixels", page="Selection", type="toggle", default=False, uniform="uShowMask"),
    dict(name="Samplepos", label="Sample Position X / Y (0-1)", page="Sample Color", type="xy", default=[.5,.5], min=0., max=1.),
    dict(name="Sample", label="Sample Input Color at Position", page="Sample Color", type="pulse"),
    dict(name="Previewinput", label="View Input for Sampling", page="Sample Color", type="pulse"),
    dict(name="Preview", label="Preview Color Switch", page="Color Switch", type="pulse"),
    dict(name="Status", label="Sample Status", page="Sample Color", type="string", default="Choose Color to Select, or sample the input. X left to right; Y bottom to top.", read_only=True, animatable=False),
)

CALLBACKS = r'''
def onPulse(par):
    c = par.owner
    if par.name == 'Preview': c.op('out1_image').openViewer()
    elif par.name == 'Previewinput': c.op('in1_image').openViewer()
    elif par.name == 'Sample':
        try:
            source = c.op('in1_image')
            source.cook(force=True)
            pixels = source.numpyArray(delayed=False)
            if pixels is None or not pixels.size: raise ValueError('No input pixels')
            h, w = pixels.shape[:2]
            x = min(w-1, max(0, int(float(c.par.Sampleposx)*(w-1)+.5)))
            y = min(h-1, max(0, int(float(c.par.Sampleposy)*(h-1)+.5)))
            color = pixels[y,x]
            if len(color)>3 and color[3] <= .001: raise ValueError('Selected pixel is transparent')
            import math
            if not all(math.isfinite(float(v)) for v in color[:3]): raise ValueError('Non-finite input pixel')
            for axis,value in zip('rgb', color): c.par['Fromcolor'+axis] = min(1.,max(0.,float(value)))
            c.par.Status = 'Sampled pixel ({}, {}) in {} x {} input'.format(x,y,w,h)
        except Exception as exc:
            c.par.Status = 'Sample unchanged: ' + str(exc)
'''

SHADER = r'''
layout(location=0) out vec4 fragColor;
uniform vec3 uFrom, uTo;
uniform float uMix, uMode, uTolerance, uSoftness, uMinSaturation, uPreserve, uShowMask;
vec3 hsv(vec3 c) {
    vec4 K=vec4(0.,-1./3.,2./3.,-1.);
    vec4 p=mix(vec4(c.bg,K.wz),vec4(c.gb,K.xy),step(c.b,c.g));
    vec4 q=mix(vec4(p.xyw,c.r),vec4(c.r,p.yzx),step(p.x,c.r));
    float d=q.x-min(q.w,q.y);
    return vec3(abs(q.z+(q.w-q.y)/(6.*d+1e-10)),d/(q.x+1e-10),q.x);
}
void main() {
    vec4 src=texture(sTD2DInputs[0],vUV.st);
    float distance=length(src.rgb-uFrom)/sqrt(3.);
    float eligible=1.;
    if(uMode>.5) {
        vec3 a=hsv(clamp(src.rgb,0.,1.)), b=hsv(uFrom);
        float dh=abs(a.x-b.x);
        distance=min(dh,1.-dh)*2.;
        eligible=step(max(.0001,uMinSaturation),a.y)*step(.0001,b.y);
    }
    float mask=uSoftness<=.000001?float(distance<=uTolerance+1e-6):1.-smoothstep(uTolerance,uTolerance+uSoftness,distance);
    mask*=eligible*step(.000001,src.a);
    float sourceValue=max(src.r,max(src.g,src.b));
    float targetValue=max(uFrom.r,max(uFrom.g,uFrom.b));
    // Black has no relative brightness to preserve; use the chosen color
    // instead of multiplying it by zero and making replacement invisible.
    float shade=targetValue>.001?clamp(sourceValue/targetValue,0.,8.):1.;
    vec3 replacement=mix(uTo,clamp(uTo*shade,0.,1.),uPreserve);
    vec3 color=mix(src.rgb,replacement,clamp(mask*uMix,0.,1.));
    if(uShowMask>.5) color=vec3(mask);
    fragColor=TDOutputSwizzle(vec4(color,src.a));
}
'''
