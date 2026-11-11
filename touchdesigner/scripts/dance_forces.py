"""Dancer-driven material advection inside Dream, Brush and Radial flow.

The source image, paper and composition envelope are never resampled. A small
GPU state texture integrates local velocity and extra flow phase over time.
"""
from pathlib import Path

MODULES = ('ink_dream_flow', 'ink_brush_flow', 'ink_radial_flow')
PARAMETERS = (
    ('Dance Forces', 'Danceenabled', 'toggle', False, 0, 1, 'Dance Forces Enabled'),
    ('Dance Forces', 'Danceamount', 'float', 1., 0, 1, 'Force Mix'),
    ('Dance Forces', 'Dancefadein', 'float', 1.5, 0, 10, 'Fade In (seconds; 0 = instant)'),
    ('Dance Forces', 'Danceresponse', 'float', .75, 0, 5, 'Force Response Delay (seconds; 0 = instant)'),
    ('Dance Forces', 'Dancestrength', 'float', 1., 0, 4, 'Movement Strength'),
    ('Dance Forces', 'Danceradius', 'float', .24, .04, .8, 'Influence Radius'),
    ('Dance Forces', 'Dancepush', 'float', 1., 0, 3, 'Directional Push'),
    ('Dance Forces', 'Danceswirl', 'float', .6, -3, 3, 'Swirl / Curl'),
    ('Dance Forces', 'Danceacceleration', 'float', 1., 0, 4, 'Flow Speed Response'),
    ('Dance Forces', 'Dancesmooth', 'float', .12, .015, 1., 'Movement Smoothing (seconds)'),
    ('Dance Forces', 'Dancedecay', 'float', .65, .03, 3., 'Force Release (seconds)'),
    ('Dance Forces', 'Dancethreshold', 'float', .015, 0, .3, 'Small Motion / Jitter Threshold'),
    ('Dance Forces', 'Danceconfidence', 'float', .3, 0, 1, 'Tracking Confidence Threshold'),
    ('Dance Influence', 'Dancespace', 'menu', 'pattern', ['canvas','pattern'],
     ['Full Canvas (Legacy)','Follow Pattern Composition'], 'Force Coordinate Space'),
    ('Dance Influence', 'Dancebody', 'float', .65, 0, 3, 'Body Movement'),
    ('Dance Influence', 'Dancehands', 'float', 1., 0, 3, 'Hand Movement'),
    ('Dance Influence', 'Dancefeet', 'float', .65, 0, 3, 'Foot Movement'),
    ('Dance Influence', 'Danceactor1', 'float', 1., 0, 2, 'Dancer 1 Influence'),
    ('Dance Influence', 'Danceactor2', 'float', 1., 0, 2, 'Dancer 2 Influence'),
    ('Dance Influence', 'Dancezoom', 'float', 1.5, .25, 4., 'Motion Area Scale'),
    ('Dance Influence', 'Dancepanx', 'float', 0., -2, 2, 'Motion Area X'),
    ('Dance Influence', 'Dancepany', 'float', 0., -2, 2, 'Motion Area Y'),
    ('Dance Influence', 'Dancemirror', 'toggle', False, 0, 1, 'Mirror Movement'),
    ('Dance Source', 'Dancesource', 'menu', 'recorded', ['recorded','live'], ['Analyzed Video','Live Camera (explicit start)'], 'Motion Source'),
    ('Dance Source', 'Dancevideo', 'file', '', 0, 1, 'Dancers Video to Analyze'),
    ('Dance Source', 'Dancecache', 'file', '', 0, 1, 'Prepared Dance Forces JSON'),
    ('Dance Source', 'Danceanalyze', 'pulse', 0, 0, 1, 'Analyze Video on CUDA'),
    ('Dance Source', 'Dancecancel', 'pulse', 0, 0, 1, 'Cancel Analysis'),
    ('Dance Source', 'Danceuselatest', 'pulse', 0, 0, 1, 'Use Latest Completed Analysis'),
    ('Dance Source', 'Danceloop', 'toggle', True, 0, 1, 'Loop Dancer Motion'),
    ('Dance Source', 'Danceoffset', 'float', 0., 0, 3600, 'Motion In Point (seconds)'),
    ('Dance Source', 'Dancespeed', 'float', 1., 0, 4., 'Dancer Motion Playback Speed'),
    ('Dance Source', 'Dancerestart', 'pulse', 0, 0, 1, 'Restart Dance Forces Preview'),
    ('Dance Source', 'Danceduration', 'float', 0., 0, 3600, 'Prepared Duration'),
    ('Dance Source', 'Dancestatus', 'str', 'Off — choose a dancers video and Analyze', 0, 1, 'Dance Forces Status'),
    ('Dance Camera', 'Dancecamera', 'int', 0, 0, 16, 'Camera Device Index'),
    ('Dance Camera', 'Dancestartcamera', 'pulse', 0, 0, 1, 'Start Live Camera on CUDA'),
    ('Dance Camera', 'Dancestopcamera', 'pulse', 0, 0, 1, 'Stop Live Camera'),
)

FORCE_FIELD = r'''
layout(location=0) out vec4 fragColor;
uniform vec4 uControl; // mix, radius, directional push, signed swirl
uniform vec4 uMotion; // elapsed seconds, reset, canvas aspect, speed response
uniform vec4 uForce0,uForce1,uForce2,uForce3,uForce4,uForce5;
uniform vec4 uForce6,uForce7,uForce8,uForce9,uForce10,uForce11;
vec3 velocityAt(vec2 uv){
    vec2 metric=vec2(uMotion.z,1.);
    vec4 forces[12]=vec4[12](uForce0,uForce1,uForce2,uForce3,uForce4,uForce5,
        uForce6,uForce7,uForce8,uForce9,uForce10,uForce11);
    vec2 velocity=vec2(0.); float activity=0.;
    for(int i=0;i<12;i++){
        vec2 q=(uv-forces[i].xy)*metric;
        float radius=max(.04,uControl.y);
        float weight=exp(-dot(q,q)/(2.*radius*radius));
        vec2 f=forces[i].zw*metric;
        // Curl of a local stream function: a push with recirculation, not a
        // radial stretch. Constant normalization preserves zero divergence.
        float stream=f.x*q.y-f.y*q.x;
        vec2 push=f+stream*vec2(-q.y,q.x)/(radius*radius);
        vec2 curl=vec2(-q.y,q.x)/radius*(f.x*.7+f.y*.3);
        velocity+=weight*(push*uControl.z+curl*uControl.w)*.65;
        activity+=weight*length(f)*.45;
    }
    velocity*=uControl.x;
    velocity*=min(1.,.35/max(1e-6,length(velocity)));
    return vec3(velocity,min(activity*uControl.x,1.)*uMotion.w);
}
'''

# Smooth the spatial velocity field on the GPU, not the final picture or the
# dancer clock. This also eases moving influence centers, radius/strength edits
# and local speed changes; delaying only tracked points would still jump fields.
RESPONSE_SHADER = FORCE_FIELD + r'''
// DANCE_FORCE_RESPONSE_V1: frame-rate-independent first-order response.
uniform float uResponse;
void main(){
    vec2 uv=vUV.st;
    if(uMotion.y>.5){fragColor=vec4(0.);return;}
    vec3 target=velocityAt(uv);
    if(uResponse<=0.){fragColor=TDOutputSwizzle(vec4(target,0.));return;}
    vec4 previous=texture(sTD2DInputs[0],uv);
    if(uMotion.x<=0.){fragColor=TDOutputSwizzle(previous);return;}
    float dt=clamp(uMotion.x,0.,.1);
    float blend=1.-exp(-dt/max(uResponse,.0001));
    fragColor=TDOutputSwizzle(vec4(mix(previous.xyz,target,blend),0.));
}
'''

SHADER = FORCE_FIELD + r'''
uniform float uResponse;
vec3 responseAt(vec2 uv){
    // Zero delay retains the original analytic field, including its midpoint
    // sampling, rather than adding low-resolution texture interpolation.
    if(uResponse<=0.) return velocityAt(uv);
    return texture(sTD2DInputs[1],clamp(uv,0.,1.)).xyz;
}
void main(){
    vec2 uv=vUV.st;
    if(uMotion.y>.5){fragColor=vec4(0.);return;}
    if(uMotion.x<=0.){fragColor=TDOutputSwizzle(texture(sTD2DInputs[0],uv));return;}
    float dt=clamp(uMotion.x,0.,.1);
    vec2 metric=vec2(uMotion.z,1.);
    vec3 v=responseAt(uv);
    // Midpoint backtrace integrates the material path, not the final picture.
    v=responseAt(uv-.5*dt*v.xy/metric);
    vec4 previous=texture(sTD2DInputs[0],clamp(uv-dt*v.xy/metric,0.,1.));
    vec2 travel=previous.xy+v.xy*dt;
    // Bound accumulated local travel for very long/repeated rehearsal cues.
    travel*=min(1.,.6/max(1e-6,length(travel)));
    fragColor=TDOutputSwizzle(vec4(travel,previous.z+v.z*dt,0.));
}
'''


LEGACY_FLOW_HELPER = r'''
// DANCE_MATERIAL_ADVECTION_V2: only foreground motion reads this texture.
uniform vec4 uDanceOutput; // enabled, unused, unused, unused
vec3 danceMaterial(vec2 uv) {
    if(uDanceOutput.x<.5) return vec3(0.);
    return texture(sTD2DInputs[1],clamp(uv,0.,1.)).xyz;
}
vec2 danceLocalTravel(vec2 screenTravel) {
    float a=radians(uRotation), c=cos(a), s=sin(a);
    vec2 p=mat2(c,-s,s,c)*screenTravel*uScale*2.;
    p.x/=max(uStretch,.25);
    return p;
}
'''


FLOW_HELPER = r'''
// DANCE_MATERIAL_ADVECTION_V3: optional pattern-local force coordinates.
uniform vec4 uDanceOutput; // enabled, pattern-local coordinates, unused, unused
vec3 danceMaterial(vec2 uv) {
    if(uDanceOutput.x<.5) return vec3(0.);
    // The old full-canvas path is intentionally unchanged.
    if(uDanceOutput.y<.5)
        return texture(sTD2DInputs[1],clamp(uv,0.,1.)).xyz;
    float aspect=uTD2DInfos[0].res.z/max(uTD2DInfos[0].res.w,1.);
    vec2 metric=vec2(aspect,1.);
    float a=radians(uRotation), c=cos(a), s=sin(a);
    mat2 toPattern=mat2(c,-s,s,c);
    float scale=max(uScale,.2), stretch=max(uStretch,.25);
    // The same coordinates as p/2 in the pattern renderer. Both response
    // and material histories stay local, so resizing never resets the dance.
    vec2 local=toPattern*((uv-.5)*metric-uCenter)*scale;
    local.x/=stretch;
    vec2 localUV=local/metric+.5;
    // Never smear a clamped edge force across the surrounding canvas.
    float edge=min(min(localUV.x,1.-localUV.x),min(localUV.y,1.-localUV.y));
    if(edge<=0.) return vec3(0.);
    float mask=smoothstep(0.,.06,edge);
    vec3 material=texture(sTD2DInputs[1],localUV).xyz;
    // Convert local travel back to screen units for both the flow and point
    // renderers. Speed-phase stays local; a smaller pattern gets smaller pushes.
    material.xy=transpose(toPattern)*(material.xy*vec2(stretch,1.))/scale;
    return material*mask;
}
vec2 danceLocalTravel(vec2 screenTravel) {
    float a=radians(uRotation), c=cos(a), s=sin(a);
    vec2 p=mat2(c,-s,s,c)*screenTravel*uScale*2.;
    p.x/=max(uStretch,.25);
    return p;
}
'''


def integrate_shader(shader):
    """Extend an existing packed renderer; retain its exact disabled path."""
    if 'DANCE_MATERIAL_ADVECTION_V3' in shader: return shader
    if 'DANCE_MATERIAL_ADVECTION_V2' in shader:
        if shader.count(LEGACY_FLOW_HELPER)!=1:
            raise ValueError('Legacy force helper changed; refusing to replace the renderer')
        return shader.replace(LEGACY_FLOW_HELPER,FLOW_HELPER,1)
    def replace(old,new,count=1):
        nonlocal shader
        if shader.count(old)!=count: raise ValueError('Flow motion anchor changed: '+old[:70])
        shader=shader.replace(old,new)
    replace('float hash21(vec2 p)',FLOW_HELPER+'\nfloat hash21(vec2 p)')
    replace('    float t=uTime*uFlowSpeed;',
        '    vec3 dance=danceMaterial(uv);\n    vec2 flowP=p-danceLocalTravel(dance.xy);\n    float t=uTime*uFlowSpeed+dance.z;')
    # Only foreground sampling positions change. p still controls the fixed
    # envelope, radial center, paper, static glitter and source composition.
    main_at=shader.index('void main() {')
    before,main=shader[:main_at],shader[main_at:]
    main=main.replace('vec2 moving=p-direction*t*uDrift*.15;', 'vec2 moving=flowP-direction*t*uDrift*.15;')
    main=main.replace('currentCoordinates(p,t,seed)', 'currentCoordinates(flowP,t,seed)')
    main=main.replace('float pt=uTime*uParticleSpeed;', 'float pt=uTime*uParticleSpeed+dance.z;')
    main=main.replace('mix(p,flow(p,pt,seed),uParticleFlow)', 'mix(flowP,flow(flowP,pt,seed),uParticleFlow)')
    main=main.replace('mix(p,currentCoordinates(p,pt,seed),uParticleFlow)', 'mix(flowP,currentCoordinates(flowP,pt,seed),uParticleFlow)')
    main=main.replace('float patternTime=uTime*uPatternSpeed;', 'float patternTime=uTime*uPatternSpeed+dance.z;')
    main=main.replace('mix(p,flow(p,patternTime,seed),uPatternFlow)', 'mix(flowP,flow(flowP,patternTime,seed),uPatternFlow)')
    main=main.replace('mix(p,currentCoordinates(p,patternTime,seed),uPatternFlow)', 'mix(flowP,currentCoordinates(flowP,patternTime,seed),uPatternFlow)')
    shader=before+main
    replace('    return fieldGrains(screen,seed);',
        '    float aspect=uTD2DInfos[0].res.z/max(uTD2DInfos[0].res.w,1.);\n'
        '    vec3 dance=danceMaterial(screen/vec2(aspect,1.)+.5);\n'
        '    return fieldGrains(screen-dance.xy,seed);')
    # Animated glitter follows the moving material; static glitter stays fixed.
    replace('    float gt=uTime*uGlitterSpeed;',
        '    float aspect=uTD2DInfos[0].res.z/max(uTD2DInfos[0].res.w,1.);\n'
        '    vec3 dance=danceMaterial(screen/vec2(aspect,1.)+.5);\n'
        '    screen-=dance.xy;\n    float gt=uTime*uGlitterSpeed+dance.z;')
    return shader


def install(component, raw, root=None):
    """Idempotent: preserve existing look values and never launch a worker."""
    import td
    root = Path(root or Path(__file__).resolve().parents[2])
    component.store('imagefx_dance_forces_root', str(root))
    component.storeStartupValue('imagefx_dance_forces_root', '')
    pages = {p.name:p for p in component.customPages}
    for page, name, kind, default, lo, hi, label in PARAMETERS:
        if component.par[name] is not None:
            continue
        if page not in pages:
            pages[page] = component.appendCustomPage(page)
        method = {'toggle':'appendToggle','float':'appendFloat','int':'appendInt','file':'appendFile',
                  'pulse':'appendPulse','str':'appendStr','menu':'appendMenu'}[kind]
        par = getattr(pages[page], method)(name, label=label)[0]
        if kind == 'pulse': continue
        if kind == 'menu': par.menuNames, par.menuLabels = lo, hi
        par.default = default; par.val = default
        if kind in {'float', 'int'}:
            par.min, par.max, par.normMin, par.normMax = lo, hi, lo, hi
            par.clampMin = par.clampMax = True
    for name in ('Danceduration', 'Dancestatus'):
        component.par[name].readOnly = True
    def node(kind, name): return component.op(name) or component.create(kind, name)
    for name in ('dance_forces_math', 'dance_forces_runtime'):
        node(td.textDAT, name).text = (root/'touchdesigner/scripts'/(name+'.py')).read_text(encoding='utf-8')
    # A small field texture carries displacement + speed phase, never color.
    zero=node(td.constantTOP,'dance_motion_zero')
    zero.par.outputresolution='custom'; zero.par.resolutionh=135
    zero.par.resolutionw.expr="max(16,round(135*parent().op('in1_image').width/max(1,parent().op('in1_image').height)))"
    zero.par.colorr=zero.par.colorg=zero.par.colorb=zero.par.alpha=0
    zero.par.format='rgba32float'
    history=node(td.feedbackTOP,'dance_motion_history')
    zero.outputConnectors[0].connect(history.inputConnectors[0])
    pixel=node(td.textDAT,'dance_motion_pixel'); pixel.text=SHADER
    top=node(td.glslTOP,'dance_motion_step')
    history.outputConnectors[0].connect(top.inputConnectors[0])
    history.par.top=top.name
    top.par.pixeldat=pixel.name; top.par.glslversion='glsl460'
    # A feedback texture retains its old size until reset; do not inherit that
    # size when switching a cue between HD and the panoramic master canvas.
    top.par.outputresolution='custom'; top.par.resolutionh=135
    top.par.resolutionw.expr=zero.par.resolutionw.expr
    top.par.format='rgba32float'
    top.par.compilebehavior = 'stalluntildone'; top.par.errorbehavior = 'showerror'
    top.seq.vec.numBlocks = 14
    top.par.vec0name = 'uControl'
    for axis, name in zip('xyzw', ('Danceamount', 'Danceradius', 'Dancepush', 'Danceswirl')):
        top.par['vec0value'+axis].expr = 'parent().par.'+name
    for i in range(12):
        top.par[f'vec{i+1}name'] = f'uForce{i}'
        for axis, j in zip('xyzw', range(4)):
            top.par[f'vec{i+1}value{axis}'].expr = f"parent().op('dance_forces_runtime').module.sample(parent())[{i}][{j}]"
    top.par.vec13name='uMotion'
    top.par.vec13valuex.expr="parent().op('dance_forces_runtime').module.flow_step(parent())['dt']"
    top.par.vec13valuey.expr="parent().op('dance_forces_runtime').module.flow_step(parent())['reset']"
    top.par.vec13valuez.expr="parent().op('in1_image').width/max(1,parent().op('in1_image').height)"
    top.par.vec13valuew.expr='parent().par.Danceacceleration'
    # A second tiny feedback texture carries the gradually responding velocity.
    # The existing material texture still carries accumulated travel/phase only.
    response_history=node(td.feedbackTOP,'dance_response_history')
    zero.outputConnectors[0].connect(response_history.inputConnectors[0])
    response_pixel=node(td.textDAT,'dance_response_pixel'); response_pixel.text=RESPONSE_SHADER
    response=node(td.glslTOP,'dance_response_step')
    response_history.outputConnectors[0].connect(response.inputConnectors[0])
    response_history.par.top=response.name
    response.par.pixeldat=response_pixel.name; response.par.glslversion='glsl460'
    response.par.outputresolution='custom'; response.par.resolutionh=135
    response.par.resolutionw.expr=zero.par.resolutionw.expr
    response.par.format='rgba32float'
    response.par.compilebehavior='stalluntildone'; response.par.errorbehavior='showerror'
    response.seq.vec.numBlocks=top.seq.vec.numBlocks
    for i in range(top.seq.vec.numBlocks):
        response.par[f'vec{i}name']=top.par[f'vec{i}name'].eval()
        for axis in 'xyzw':
            response.par[f'vec{i}value{axis}'].expr=top.par[f'vec{i}value{axis}'].expr
    for shader in (top,response):
        shader.seq.vec.numBlocks=15
        shader.par.vec14name='uResponse'
        shader.par.vec14valuex.expr='parent().par.Danceresponse'
    response.outputConnectors[0].connect(top.inputConnectors[1])
    field=node(td.switchTOP,'dance_motion_out')
    zero.outputConnectors[0].connect(field.inputConnectors[0]); top.outputConnectors[0].connect(field.inputConnectors[1])
    enabled="parent().op('dance_forces_runtime').module.output_enabled(parent())"
    field.par.index.expr=enabled
    field.outputConnectors[0].connect(raw.inputConnectors[1])
    shader_dat=component.op(raw.par.pixeldat.eval())
    if not any(v in shader_dat.text for v in ('DANCE_MATERIAL_ADVECTION_V2','DANCE_MATERIAL_ADVECTION_V3')):
        node(td.textDAT,'dance_forces_original_shader').text=shader_dat.text
    shader_dat.text=integrate_shader(shader_dat.text)
    rows=[i for i in range(raw.seq.vec.numBlocks) if raw.par[f'vec{i}name'].eval()=='uDanceOutput']
    index=rows[0] if rows else raw.seq.vec.numBlocks
    if not rows: raw.seq.vec.numBlocks=index+1
    raw.par[f'vec{index}name']='uDanceOutput'; raw.par[f'vec{index}valuex'].expr=enabled
    raw.par[f'vec{index}valuey'].expr='parent().par.Dancespace.menuIndex'
    # Retain the legacy named output for references, but retire its image warp.
    switch = node(td.switchTOP, 'dance_forces_switch')
    raw.outputConnectors[0].connect(switch.inputConnectors[0])
    switch.par.index=0
    old=component.op('dance_forces_warp')
    if old is not None: old.bypass=True
    feedback = component.op('flow_feedback_source')
    if feedback is not None:
        switch.outputConnectors[0].connect(feedback.inputConnectors[0])
    changes = node(td.parameterexecuteDAT, 'dance_forces_controls')
    changes.par.op = '..'; changes.par.custom = True; changes.par.builtin = False
    changes.par.pars = 'Dance* Enabled'; changes.par.valuechange = True; changes.par.onpulse = True
    changes.text = "def onPulse(par):\n    parent().op('dance_forces_runtime').module.pulse(parent(),par.name)\ndef onValueChange(par,prev):\n    parent().op('dance_forces_runtime').module.changed(parent(),par.name,prev)\n"
    poll = node(td.executeDAT, 'dance_forces_poll'); poll.par.framestart = True
    poll.par.active.expr = "bool(parent().fetch('dance_force_job',None,search=False) or parent().fetch('dance_force_camera_owner',None,search=False))"
    poll.text = "def onFrameStart(frame):\n    parent().op('dance_forces_runtime').module.poll(parent())\n"
    component.op('dance_forces_runtime').module.reset_flow(component)
    return switch
