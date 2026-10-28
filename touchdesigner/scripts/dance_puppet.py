"""Opt-in Dance Puppet workflow module, backed by local motion preparation."""
from pathlib import Path


FILES = ('Renderfile','Fanrenderfile','Chainrenderfile','Dancevideo','Motioncache','Characterprofile')
PARAMETERS = (
    ('Puppet','Enabled','toggle',False,0,1,'Puppet Enabled'),
    ('Puppet','Sourcemode','menu','recorded',['recorded','live'],['Prepared Dance Video','Live Camera'],'Motion Source'),
    ('Puppet','Characters','menu','both',['both','fan','chain'],['Both Characters Together','Fan Character Only','Chain Character Only'],'Characters / Projection Mode'),
    ('Puppet','Composite','toggle',True,0,1,'Over Upstream Effects'),
    ('Puppet','Transparent','toggle',True,0,1,'Transparent Background'),
    ('Puppet','Monochrome','toggle',True,0,1,'Black / White Reference Palette'),
    ('Puppet','Bodycolor','rgb',(0,0,0),0,1,'Body Color'),
    ('Puppet','Linecolor','rgb',(.92,.92,.92),0,1,'Line Color'),
    ('Puppet','Background','rgb',(0,0,0),0,1,'Background Color'),
    ('Puppet','Opacity','float',1,0,1,'Puppet Opacity'),
    ('Puppet','Fadein','float',1.5,0,10,'Fade In (seconds; 0 = instant)'),
    ('Puppet','Openpuppet','pulse',0,0,1,'Open Puppet RGBA Preview'),
    ('Framing','Framing','menu','full',['full','cropped'],['Complete Bodies','Cropped Composition'],'Composition'),
    ('Framing','Zoom','float',1,.25,4,'Zoom'),
    ('Framing','Panx','float',0,-1,1,'Horizontal Position'),
    ('Framing','Pany','float',0,-1,1,'Vertical Position'),
    ('Framing','Mirror','toggle',False,0,1,'Mirror Dance'),
    ('Playback','Autotime','toggle',True,0,1,'Animate Preview (cue owns time during playback)'),
    ('Playback','Pausepreview','pulse',0,0,1,'Pause Preview'),
    ('Playback','Resumepreview','pulse',0,0,1,'Resume Preview'),
    ('Playback','Manualtime','float',0,-1e9,1e9,'Preview Time (seconds)'),
    ('Playback','Time','float',0,-1e9,1e9,'Effective Time'),
    ('Playback','Timescale','float',1,0,4,'Playback Speed'),
    ('Playback','Offset','float',0,0,3600,'Motion In Point (seconds)'),
    ('Playback','Loop','toggle',True,0,1,'Loop Motion'),
    ('Playback','Restartmotion','pulse',0,0,1,'Reset Preview to Opening Pose'),
    ('Playback','Duration','float',0,0,3600,'Prepared Motion Duration'),
    ('Motion Files','Renderfile','file','',0,1,'Prepared RGBA Movie'),
    ('Motion Files','Fanrenderfile','file','',0,1,'Prepared Fan-only RGBA Movie'),
    ('Motion Files','Chainrenderfile','file','',0,1,'Prepared Chain-only RGBA Movie'),
    ('Motion Files','Dancevideo','file','',0,1,'Dancers Video (for analysis)'),
    ('Motion Files','Motioncache','file','',0,1,'Analyzed Motion JSON'),
    ('Motion Files','Characterprofile','file','',0,1,'Calibrated Character Profile JSON'),
    ('Motion Files','Removecamera','toggle',True,0,1,'Remove Source Camera Motion (rebuild / restart live)'),
    ('Motion Files','Analyzevideo','pulse',0,0,1,'Analyze New Video and Build'),
    ('Motion Files','Buildmotion','pulse',0,0,1,'Build from Motion Cache'),
    ('Motion Files','Cancelbuild','pulse',0,0,1,'Cancel Preparation'),
    ('Motion Files','Buildstatus','str','No build running',0,1,'Preparation Status'),
    ('Live Camera','Cameraindex','int',0,0,16,'Local Camera Device Index'),
    ('Live Camera','Livesmoothing','float',.08,0,.3,'Live Smoothing (seconds; restart camera)'),
    ('Live Camera','Startcamera','pulse',0,0,1,'Start Camera / Tracking Explicitly'),
    ('Live Camera','Stopcamera','pulse',0,0,1,'Stop Camera'),
    ('Motion Finish','Feedbackenabled','toggle',False,0,1,'Feedback Trails'),
    ('Motion Finish','Trailamount','float',.25,0,1,'Trail Amount'),
    ('Motion Finish','Trailhalf','float',.18,.02,2,'Trail Half-Life (seconds)'),
    ('Motion Finish','Trailsoftness','float',0,0,8,'Trail Softness (pixels)'),
    ('Motion Finish','Clearhistory','pulse',0,0,1,'Clear Trails'),
    ('Status','Ready','toggle',False,0,1,'Motion Ready'),
    ('Status','Status','str','Choose a motion source',0,1,'Status'),
)

STYLE = r'''
layout(location=0) out vec4 fragColor;
uniform vec4 uFrame,uStyle,uBody,uLine,uBack;
void main(){
    vec2 uv=(vUV.st-.5-uFrame.yz)/max(uFrame.x,.001)+.5;
    // Fit the 16:9 prepared canvas into any output without stretching bodies.
    float ratio=(uTDOutputInfo.res.z/uTDOutputInfo.res.w)/(16./9.);
    if(ratio>1.)uv.x=(uv.x-.5)*ratio+.5; else uv.y=(uv.y-.5)/ratio+.5;
    if(uFrame.w>.5)uv.x=1.-uv.x;
    float inside=float(all(greaterThanEqual(uv,vec2(0)))&&all(lessThanEqual(uv,vec2(1))));
    vec4 c=texture(sTD2DInputs[0],clamp(uv,0.,1.)); c*=inside;
    vec3 rgb=c.a>1e-5?c.rgb/c.a:vec3(0);
    float ink=smoothstep(.12,.72,dot(rgb,vec3(.2126,.7152,.0722)));
    if(uStyle.x>.5)rgb=mix(uBody.rgb,uLine.rgb,ink);
    c=vec4(rgb,c.a*uStyle.y);
    // Keep the motion buffer transparent; the background is added AFTER trails.
    fragColor=TDOutputSwizzle(c);
}
'''
TRAIL = r'''
layout(location=0) out vec4 fragColor;
uniform vec4 uTrail,uClock;
vec4 premul(vec4 c){return vec4(c.rgb*c.a,c.a);}
void main(){
    vec4 c=texture(sTD2DInputs[0],vUV.st);
    if(uTrail.x<.5||uTrail.y<=0.||uClock.y>.5){fragColor=TDOutputSwizzle(c);return;}
    vec2 d=uTDOutputInfo.res.xy*uTrail.w;
    vec4 h=vec4(0);
    for(int x=-1;x<=1;x++)for(int y=-1;y<=1;y++)h+=premul(texture(sTD2DInputs[1],vUV.st+vec2(x,y)*d))/9.;
    if(uClock.z>.5){fragColor=TDOutputSwizzle(texture(sTD2DInputs[1],vUV.st));return;}
    h*=pow(.5,uClock.x/max(.02,uTrail.z));
    vec4 a=premul(c); vec4 p=a+h*(1.-a.a);
    // Store full-strength history. Trail Amount is a display mix, not a
    // per-frame multiplier (which made .25 vanish almost immediately).
    fragColor=TDOutputSwizzle(vec4(p.a>1e-6?p.rgb/p.a:vec3(0),p.a));
}
'''
FINISH = r'''
layout(location=0) out vec4 fragColor;
uniform vec4 uFinish,uBackground;
void main(){
    vec4 current=texture(sTD2DInputs[0],vUV.st),history=texture(sTD2DInputs[1],vUV.st);
    vec4 c=vec4(current.rgb*current.a,current.a);
    if(uFinish.x>.5)c=mix(c,vec4(history.rgb*history.a,history.a),uFinish.y);
    if(uFinish.z<.5)c=vec4(c.rgb+uBackground.rgb*(1.-c.a),1.);
    else c.rgb=c.a>1e-6?c.rgb/c.a:vec3(0.);
    // Apply after feedback: trails cannot bypass the entrance fade.
    c.a*=clamp(uFinish.w,0.,1.);
    fragColor=TDOutputSwizzle(c);
}
'''
COMPOSITE = r'''
layout(location=0) out vec4 fragColor;
uniform float uOver;
void main(){
    vec4 a=texture(sTD2DInputs[1],vUV.st),b=texture(sTD2DInputs[0],vUV.st);
    if(uOver<.5){fragColor=TDOutputSwizzle(a);return;}
    float alpha=a.a+b.a*(1.-a.a);
    vec3 rgb=alpha>1e-6?(a.rgb*a.a+b.rgb*b.a*(1.-a.a))/alpha:vec3(0);
    fragColor=TDOutputSwizzle(vec4(rgb,alpha));
}
'''


def build(demo, project_root):
    import td
    project_root=Path(project_root)
    c=demo.op('dance_puppet')
    if c is None: c=demo.create(td.baseCOMP,'dance_puppet')
    c.store('imagefx_puppet_root',str(project_root))
    c.storeStartupValue('imagefx_puppet_root', '')
    if 'puppet_live_maps' in c.storage: c.unstore('puppet_live_maps')
    pages={p.name:p for p in c.customPages}
    for page,name,kind,default,lo,hi,label in PARAMETERS:
        if c.par[name] is None:
            p=pages.get(page)
            if p is None: p=c.appendCustomPage(page); pages[page]=p
            method={'str':'appendStr','file':'appendFile','toggle':'appendToggle','pulse':'appendPulse','menu':'appendMenu','float':'appendFloat','int':'appendInt','rgb':'appendRGB'}[kind]
            pars=getattr(p,method)(name,label=label)
            for index,parameter in enumerate(pars):
                if kind=='pulse': continue
                if kind=='menu': parameter.menuNames=lo; parameter.menuLabels=hi
                value=default[index] if kind=='rgb' else default
                parameter.default=value; parameter.val=value
                if kind in {'float','int','rgb'}:
                    parameter.min,parameter.max=lo,hi; parameter.normMin,parameter.normMax=lo,hi
                    parameter.clampMin=parameter.clampMax=True
    for name in ('Time','Duration','Ready','Status','Buildstatus'): c.par[name].readOnly=True
    c.par.Time.expr="me.op('puppet_runtime').module.preview_time(me)"
    c.par.Manualtime.enableExpr='not me.par.Autotime'
    if demo.fetch('imagefx_branch',False):
        c.par.Autotime=False
        c.par.Manualtime.expr='parent(2).par.Time'
    if demo.par['Dancepuppetenabled'] is None:
        p=next(iter(demo.customPages),None) or demo.appendCustomPage('Effects')
        master=p.appendToggle('Dancepuppetenabled',label='Dance Puppet Enabled')[0]
        master.default=False; master.val=False
    c.par.Enabled.bindExpr='parent().par.Dancepuppetenabled'; c.par.Enabled.mode=type(c.par.Enabled.mode).BIND
    def node(kind,name): return c.op(name) or c.create(kind,name)
    runtime=node(td.textDAT,'puppet_runtime'); runtime.text=(project_root/'touchdesigner/scripts/dance_puppet_runtime.py').read_text(encoding='utf-8')
    incoming=node(td.inTOP,'in1_image')
    empty=node(td.constantTOP,'empty'); empty.par.alpha=0; empty.par.resolutionw=2; empty.par.resolutionh=2
    reader=node(td.moviefileinTOP,'recorded_motion')
    reader.par.file.expr="parent().par[{'both':'Renderfile','fan':'Fanrenderfile','chain':'Chainrenderfile'}[parent().par.Characters.eval()]] if parent().par.Enabled and parent().par.Sourcemode=='recorded' else ''"
    reader.par.playmode='specify'; reader.par.play=True; reader.par.indexunit='seconds'
    reader.par.index.expr='parent().par.Time+parent().par.Offset'
    reader.par.premultrgbbyalpha='off'; reader.par.alwaysloadinitial=True
    reader.par.textendleft.expr=reader.par.textendright.expr="'cycle' if parent().par.Loop else 'hold'"
    live_cb=node(td.textDAT,'live_callbacks'); live_cb.text="def onCook(scriptOp):\n    c=scriptOp.parent()\n    c.op('puppet_runtime').module.copy_live(c,scriptOp)\n"
    live=node(td.scriptTOP,'live_rgba'); live.par.callbacks='live_callbacks'
    source=node(td.switchTOP,'motion_source')
    for i,n in enumerate((empty,reader,live)): n.outputConnectors[0].connect(source.inputConnectors[i])
    source.par.index.expr="(2 if parent().par.Sourcemode=='live' else (1 if parent().op('recorded_motion').par.file else 0)) if parent().par.Enabled else 0"
    def shader(name,code,inputs,bindings):
        dat=node(td.textDAT,name+'_shader'); dat.text=code
        top=node(td.glslTOP,name); top.par.pixeldat=dat.name; top.par.glslversion='glsl460'
        top.par.compilebehavior='stalluntildone'; top.par.outputresolution='custom'
        top.par.resolutionw.expr="max(16,parent().op('in1_image').width)"
        top.par.resolutionh.expr="max(16,parent().op('in1_image').height)"
        top.par.format='rgba16float'
        for i,src in enumerate(inputs): src.outputConnectors[0].connect(top.inputConnectors[i])
        top.seq.vec.numBlocks=len(bindings)
        for i,(uniform,values) in enumerate(bindings):
            top.par['vec{}name'.format(i)]=uniform
            for suffix,value in zip('xyzw',values): top.par['vec{}value{}'.format(i,suffix)].expr=value
        return top
    exp=lambda name:'parent().par.'+name
    style=shader('puppet_style',STYLE,[source],[('uFrame',["parent().par.Zoom*(1.45 if parent().par.Framing=='cropped' else 1.)",exp('Panx'),exp('Pany'),exp('Mirror')]),
        ('uStyle',[exp('Monochrome'),exp('Opacity'),exp('Transparent'),'0']),('uBody',[exp('Bodycolor'+s) for s in 'rgb']),
        ('uLine',[exp('Linecolor'+s) for s in 'rgb']),('uBack',[exp('Background'+s) for s in 'rgb'])])
    history=node(td.feedbackTOP,'puppet_history')
    style.outputConnectors[0].connect(history.inputConnectors[0])
    accumulation=shader('puppet_trail_accum',TRAIL,[style,history],[('uTrail',[exp(n) for n in ('Feedbackenabled','Trailamount','Trailhalf','Trailsoftness')]),
        ('uClock',["parent().op('puppet_runtime').module.finish_clock(parent())[{}]".format(i) for i in range(4)])])
    history.par.top=accumulation.name
    finished=shader('puppet_finish',FINISH,[style,accumulation],[
        ('uFinish',[exp('Feedbackenabled'),exp('Trailamount'),exp('Transparent'),"parent().op('puppet_runtime').module.fade_gain(parent())"]),
        ('uBackground',[exp('Background'+s) for s in 'rgb'])])
    rgba=node(td.nullTOP,'puppet_rgba'); finished.outputConnectors[0].connect(rgba.inputConnectors[0])
    composite=shader('puppet_composite',COMPOSITE,[incoming,rgba],[('uOver',[exp('Composite')])])
    gate=node(td.switchTOP,'enabled_switch')
    incoming.outputConnectors[0].connect(gate.inputConnectors[0]); composite.outputConnectors[0].connect(gate.inputConnectors[1])
    gate.par.index.expr='int(parent().par.Enabled)'
    out=node(td.outTOP,'out1_image'); gate.outputConnectors[0].connect(out.inputConnectors[0])
    c.par.opviewer=out.name; c.viewer=True
    cb=node(td.parameterexecuteDAT,'puppet_parameters'); cb.par.op='..'; cb.par.custom=True; cb.par.builtin=False
    cb.par.pars='*'; cb.par.onpulse=True; cb.par.valuechange=True
    cb.text="def onPulse(par):\n    parent().op('puppet_runtime').module.on_pulse(parent(),par.name)\ndef onValueChange(par,prev):\n    parent().op('puppet_runtime').module.on_value(parent(),par.name,prev)\n"
    poll=node(td.executeDAT,'puppet_poll'); poll.par.active=True; poll.par.framestart=True
    poll.text="def onFrameStart(frame):\n    c=parent()\n    c.op('puppet_runtime').module.poll(c)\n    if c.allowCooking and c.par.Enabled and c.par.Sourcemode=='live':\n        c.op('live_rgba').cook(force=True)\n"
    c.comment='Local two-person 2.5D puppet. Prepared RGBA clips for cues; explicit camera start for live mode. Transparent output: puppet_rgba.'
    return c


def install_fade(c, project_root):
    """Additive migration; leave existing readers, timing and cue data alone."""
    if c.par['Fadein'] is None:
        page=next(p for p in c.customPages if p.name=='Puppet')
        p=page.appendFloat('Fadein',label='Fade In (seconds; 0 = instant)')[0]
        p.default=p.val=1.5; p.min=p.normMin=0; p.max=p.normMax=10
        p.clampMin=p.clampMax=True
    c.op('puppet_runtime').text=(Path(project_root)/'touchdesigner/scripts/dance_puppet_runtime.py').read_text(encoding='utf-8')
    c.op('puppet_finish_shader').text=FINISH
    c.op('puppet_finish').par.vec0valuew.expr="parent().op('puppet_runtime').module.fade_gain(parent())"
