"""V5 only: optional finite temporal blur and independently adjustable feedback."""
from pathlib import Path

BLUR_SHADER=r'''
layout(location=0) out vec4 fragColor;
uniform vec4 uBlur; // amount, clear, unused, unused
void main() {
    vec4 current=texture(sTD2DInputs[0],vUV.st);
    if(uBlur.y>.5 || uBlur.x<=0.) { fragColor=TDOutputSwizzle(current); return; }
    vec4 a=texture(sTD2DInputs[1],vUV.st), b=texture(sTD2DInputs[2],vUV.st);
    fragColor=TDOutputSwizzle(mix(current,current*.60+a*.30+b*.10,clamp(uBlur.x,0.,1.)));
}
'''

HOLD_SHADER=r'''
layout(location=0) out vec4 fragColor;
uniform vec4 uHold; // paused/hold, clear, unused, unused
void main() {
    vec4 color=texture(sTD2DInputs[(uHold.x>.5 && uHold.y<.5)?1:0],vUV.st);
    fragColor=TDOutputSwizzle(color);
}
'''

TRAIL_SHADER=r'''
layout(location=0) out vec4 fragColor;
uniform vec4 uTrail; // half-life seconds, blur pixels, elapsed seconds, clear
void main() {
    vec2 uv=vUV.st;
    vec4 current=texture(sTD2DInputs[0],uv);
    if(uTrail.w>.5) { fragColor=TDOutputSwizzle(current); return; }
    if(uTrail.z<=0.) { fragColor=TDOutputSwizzle(texture(sTD2DInputs[1],uv)); return; }
    vec2 d=uTD2DInfos[1].res.xy*max(0.,uTrail.y);
    vec3 history=texture(sTD2DInputs[1],uv).rgb*.25;
    history+=(texture(sTD2DInputs[1],uv+vec2(d.x,0.)).rgb+texture(sTD2DInputs[1],uv-vec2(d.x,0.)).rgb
             +texture(sTD2DInputs[1],uv+vec2(0.,d.y)).rgb+texture(sTD2DInputs[1],uv-vec2(0.,d.y)).rgb)*.125;
    history+=(texture(sTD2DInputs[1],uv+d).rgb+texture(sTD2DInputs[1],uv-d).rgb
             +texture(sTD2DInputs[1],uv+vec2(d.x,-d.y)).rgb+texture(sTD2DInputs[1],uv+vec2(-d.x,d.y)).rgb)*.0625;
    float decay=pow(.5,uTrail.z/max(.02,uTrail.x));
    // Light ink trails on navy: bounded max avoids additive brightness runaway.
    fragColor=TDOutputSwizzle(vec4(max(current.rgb,history*decay),current.a));
}
'''

MIX_SHADER=r'''
layout(location=0) out vec4 fragColor;
uniform vec4 uMix;
void main() {
    vec4 current=texture(sTD2DInputs[0],vUV.st);
    vec4 history=texture(sTD2DInputs[1],vUV.st);
    fragColor=TDOutputSwizzle(mix(current,history,clamp(uMix.x,0.,1.)));
}
'''


def install(component,root):
    import td
    page=next((p for p in component.customPages if p.name=='Motion Finish'),None)
    if page is None: page=component.appendCustomPage('Motion Finish')
    def make(kind,name):
        return component.op(name) or component.create(kind,name)
    def par(kind,name,label,value=None,low=None,high=None):
        if component.par[name] is None: getattr(page,'append'+kind)(name,label=label)
        p=component.par[name]
        if value is not None: p.default=value; p.val=value
        if low is not None: p.min=p.normMin=low; p.clampMin=True
        if high is not None: p.max=p.normMax=high; p.clampMax=True
    par('Toggle','Motionblur','Short Motion Blur',False)
    par('Float','Bluramount','Motion Blur Amount',.35,0.,1.)
    par('Toggle','Feedbackenabled','Feedback Trails',False)
    par('Float','Trailamount','Feedback / Trail Mix',.25,0.,1.)
    par('Float','Trailhalf','Trail Half-Life (Seconds)',.18,.02,2.)
    par('Float','Trailblur','Trail Softness (Pixels)',0.,0.,8.)
    par('Pulse','Cleartrails','Clear Blur / Trail History')
    par('Pulse','Resetfx','Reset Motion Finish')
    runtime=make(td.textDAT,'effects_runtime')
    runtime.text=(Path(root)/'prototypes/dance_puppet/preview_effects_runtime.py').read_text(encoding='utf-8')
    sample="parent().op('effects_runtime').module.sample(parent())"
    raw=component.op('framing')
    def history(name,source,target):
        h=make(td.feedbackTOP,name)
        source.outputConnectors[0].connect(h.inputConnectors[0])
        h.par.top=target
        h.par.reset.expr=sample+"['clear']"
        return h
    def shader(name,code,inputs,uniform,expressions):
        dat=make(td.textDAT,name+'_pixel'); dat.text=code
        node=make(td.glslTOP,name); node.par.pixeldat=dat.name
        node.par.glslversion='glsl460'; node.par.format='rgba16float'
        node.par.compilebehavior='stalluntildone'; node.par.errorbehavior='showerror'
        for i,item in enumerate(inputs): item.outputConnectors[0].connect(node.inputConnectors[i])
        node.par.vec0name=uniform
        for axis,expr in zip('xyzw',expressions): node.par['vec0value'+axis].expr=expr
        return node
    prior=history('blur_previous',raw,raw.name)
    older=history('blur_older',raw,prior.name)
    held=history('blur_hold',raw,'blur_hold_output')
    # GLSL TOP has three wired inputs; hold the completed blur in a separate pass.
    blur=shader('motion_blur',BLUR_SHADER,[raw,prior,older],'uBlur',
                ['parent().par.Bluramount',sample+"['clear']",'0','0'])
    hold=shader('blur_hold_output',HOLD_SHADER,[blur,held],'uHold',
                [sample+"['hold']",sample+"['clear']",'0','0'])
    choose_blur=make(td.switchTOP,'blur_select')
    raw.outputConnectors[0].connect(choose_blur.inputConnectors[0]); hold.outputConnectors[0].connect(choose_blur.inputConnectors[1])
    choose_blur.par.index.expr='int(bool(parent().par.Enabled and parent().par.Motionblur and parent().par.Bluramount>0))'
    previous=history('trail_history',choose_blur,'trail_accumulate')
    accum=shader('trail_accumulate',TRAIL_SHADER,[choose_blur,previous],'uTrail',
                 ['parent().par.Trailhalf','parent().par.Trailblur',sample+"['dt']",sample+"['clear']"])
    mix=shader('trail_mix',MIX_SHADER,[choose_blur,accum],'uMix',['parent().par.Trailamount','0','0','0'])
    choose=make(td.switchTOP,'finish_select')
    choose_blur.outputConnectors[0].connect(choose.inputConnectors[0]); mix.outputConnectors[0].connect(choose.inputConnectors[1])
    choose.par.index.expr='int(bool(parent().par.Enabled and parent().par.Feedbackenabled and parent().par.Trailamount>0))'
    choose.outputConnectors[0].connect(component.op('out1').inputConnectors[0])
    # Position changes from the player's clock are not external seeks.
    component.op('runtime').text=(Path(root)/'prototypes/dance_puppet/preview_controls.py').read_text(encoding='utf-8')+'''
_base_tick = tick
def tick(component, now):
    before=float(component.par.Position)
    component.store('puppet_internal_tick',True)
    try:
        _base_tick(component,now)
    finally:
        component.store('puppet_internal_tick',False)
    after=float(component.par.Position)
    if abs(after-before)>1e-7:
        component.store('puppet_clock_change',dict(before=before,after=after))
        component.storeStartupValue('puppet_clock_change',None)
'''
    buttons=component.op('buttons')
    buttons.par.pars='Go Pause Stop Resetview Preview Cleartrails Resetfx'
    buttons.text='''def onPulse(par):
    component=parent()
    component.op('effects_runtime').module.action(component,par.name)
    if par.name not in ('Cleartrails','Resetfx'):
        component.op('runtime').module.action(component,par.name)
'''
    changes=make(td.parameterexecuteDAT,'effect_changes')
    changes.par.op='..'; changes.par.custom=True; changes.par.builtin=False
    changes.par.pars='Position Composition Zoom Panx Pany Enabled Motionblur Feedbackenabled Speed'
    changes.par.valuechange=True
    changes.text="def onValueChange(par,prev):\n    parent().op('effects_runtime').module.changed(parent(),par.name,prev)\n"
    start=make(td.executeDAT,'effect_startup'); start.par.start=True
    start.text="def onStart():\n    parent().op('effects_runtime').module.clear(parent())\n"
    for index,node in enumerate((prior,older,held,blur,hold,choose_blur,previous,accum,mix,choose,runtime,changes,start)):
        node.nodeX=700+(index%4)*180; node.nodeY=100-(index//4)*160
    runtime.module.clear(component)
    return choose
