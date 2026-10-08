"""Two independent image/video workflows and a fixed-canvas GPU compositor."""
import math

CORE_FILES = {
    'reference_particle_field':'ReferenceParticleField.tox', 'calligraphic_shadow':'CalligraphicShadow.tox',
    'ink_orbit_canvas':'InkOrbitCanvas.tox', 'ink_dream_flow':'InkDreamFlow.tox',
    'ink_brush_flow':'InkBrushFlow.tox', 'ink_radial_flow':'InkRadialFlow.tox',
    'ink_flow':'InkFlowFusion.tox', 'particle_random_move':'ParticleRandomMove.tox',
    'glitch_fusion':'GlitchFusion.tox', 'color_adjustment':'ColorAdjustment.tox',
    'color_switch':'ColorSwitch.tox', 'motion_studio':'MotionStudio.tox',
    'fx_rack':'FxRack.tox', 'layer_composite':'LayerComposite.tox', 'final_crop':'FinalCrop.tox',
}
SPLITS = {'equal':.5, 'two_one':2/3, 'one_two':1/3, 'three_one':.75, 'one_three':.25}

def rectangles(layout='horizontal', ratio='equal', split=.5, gap=0., margin=0., a=(0.,0.,.5,1.), b=(.5,0.,.5,1.)):
    """Bottom-left normalized destination rectangles; crops are independent."""
    def bound(v, lo, hi, fallback):
        v=float(v)
        return min(hi,max(lo,v)) if math.isfinite(v) else fallback
    s=SPLITS.get(ratio,bound(split,.01,.99,.5))
    m=bound(margin,0.,.24,0.); g=bound(gap,0.,.25,0.); size=1.-2*m
    if layout=='horizontal':
        available=max(.01,size-g)
        return (m,m,available*s,size),(m+available*s+g,m,available*(1.-s),size)
    if layout=='vertical':
        available=max(.01,size-g)
        return (m,m+available*(1.-s)+g,size,available*s),(m,m,size,available*(1.-s))
    if layout=='pip': return (m,m,size,size),(1.-m-.32,m,.32,.32)
    if layout=='overlay': return (m,m,size,size),(m,m,size,size)
    if layout!='manual': raise ValueError('Unknown composition layout')
    return tuple(bound(v,-1.,1.,0.) if i<2 else bound(v,.01,2.,1.) for i,v in enumerate(a)), tuple(bound(v,-1.,1.,0.) if i<2 else bound(v,.01,2.,1.) for i,v in enumerate(b))

def scalar(name,label,page,default,low=0.,high=1.,**extra):
    return dict(name=name,label=label,page=page,type='float',default=default,min=low,max=high,**extra)

PARAMETERS = (
    dict(name='Enabled',label='Two-Image Composition Enabled',page='Composition',type='toggle',default=True),
    dict(name='Layout',label='Layout',page='Composition',type='menu',default='horizontal',menu_names=['horizontal','vertical','pip','overlay','manual'],menu_labels=['Side by Side','Top / Bottom','Picture in Picture (B over A)','Full Overlay','Manual Rectangles']),
    dict(name='Ratio',label='A : B Split Ratio',page='Composition',type='menu',default='equal',menu_names=[*SPLITS,'custom'],menu_labels=['1 : 1','2 : 1','1 : 2','3 : 1','1 : 3','Manual Split']),
    scalar('Split','Manual A Share','Composition',.5,.01,.99),
    scalar('Gap','Gap (Canvas Fraction)','Composition',0.,0.,.25),
    scalar('Margin','Outer Margin','Composition',0.,0.,.24),
    dict(name='Background',label='Canvas Background',page='Composition',type='rgba',default=[0.,0.,0.,1.],uniform='uBackground'),
    dict(name='Swap',label='Swap A / B Positions',page='Composition',type='toggle',default=False),
    dict(name='Ontop',label='Top Layer When Overlapping',page='Composition',type='menu',default='b',menu_names=['a','b'],menu_labels=['Image A','Image B'],uniform='uOnTop'),
    dict(name='Preview',label='Preview Composition',page='Composition',type='pulse'),
    dict(name='Resetlayout',label='Reset Layout Only',page='Composition',type='pulse'),
    dict(name='Status',label='Composition Status',page='Composition',type='string',default='',read_only=True,animatable=False),
    dict(name='Autotime',label='Auto Time',page='Timing',type='toggle',default=True),
    scalar('Timescale','Effect Time Scale / Reverse','Timing',1.,-5.,5.),
    scalar('Manualtime','Manual Time','Timing',0.,-100000.,100000.,norm_max=60.),
    scalar('Time','Effective Time','Timing',0.,-500000.,500000.,read_only=True,animatable=False),
)
for _p in ('A','B'):
    PARAMETERS += (
        dict(name=_p+'visible',label='Image '+_p+' Visible',page='Image '+_p,type='toggle',default=True),
        dict(name=_p+'source',label='Image '+_p+' Source',page='Image '+_p,type='menu',default='auto',menu_names=['auto','file','input','transparent'],menu_labels=['Auto (File / Input)','Image / Video File','TOP Input '+('1' if _p=='A' else '2'),'Transparent']),
        dict(name=_p+'file',label='Image '+_p+' / Video File',page='Image '+_p,type='file',default='',animatable=False),
        dict(name=_p+'fit',label='Fit in Frame',page='Image '+_p,type='menu',default='cover',menu_names=['contain','cover','stretch'],menu_labels=['Fit / Letterbox','Fill / Crop','Stretch']),
        scalar(_p+'opacity','Image '+_p+' Opacity','Image '+_p,1.),
        dict(name=_p+'effects',label='Edit Image '+_p+' Effects',page='Image '+_p,type='pulse'),
        dict(name=_p+'preview',label='Preview Image '+_p+' After Effects',page='Image '+_p,type='pulse'),
        dict(name=_p+'status',label='Media Status',page='Image '+_p,type='string',default='',read_only=True,animatable=False),
        dict(name=_p+'position',label='Manual Left / Bottom',page='Placement '+_p,type='xy',default=[0.,0.] if _p=='A' else [.5,0.],min=-1.,max=1.),
        dict(name=_p+'size',label='Manual Width / Height',page='Placement '+_p,type='xy',default=[.5,1.],min=.01,max=2.),
        dict(name=_p+'anchor',label='Fit / Fill Anchor X / Y',page='Placement '+_p,type='xy',default=[.5,.5],min=0.,max=1.),
        dict(name=_p+'flipx',label='Flip Horizontally',page='Placement '+_p,type='toggle',default=False),
        dict(name=_p+'flipy',label='Flip Vertically',page='Placement '+_p,type='toggle',default=False),
        dict(name=_p+'play',label='Play / Pause',page='Playback '+_p,type='toggle',default=True),
        dict(name=_p+'loop',label='Loop',page='Playback '+_p,type='toggle',default=True),
        scalar(_p+'speed','Speed / Reverse','Playback '+_p,1.,-4.,4.),
        scalar(_p+'in','Start / Seek (Seconds)','Playback '+_p,0.,0.,86400.,norm_max=60.),
        dict(name=_p+'restart',label='Restart',page='Playback '+_p,type='pulse'),
        dict(name=_p+'reload',label='Reload File',page='Playback '+_p,type='pulse'),
    )

RUNTIME = r'''
def selected(c, p):
    mode=c.par[p+'source'].eval()
    has_file=bool(c.par[p+'file'].eval().strip())
    port=0 if p=='A' else 1
    if not c.par[p+'visible']: return 0
    if mode=='file' or (mode=='auto' and has_file): return 2 if has_file else 0
    if mode in ('input','auto'): return 1 if len(c.inputs)>port else 0
    return 0

def status(c,p):
    index=selected(c,p)
    if index==0: return 'Transparent / hidden (no selected media)'
    if index==1: return 'Using TOP input '+('1' if p=='A' else '2')
    reader=c.op(p.lower()+'_file')
    if reader.isInvalid: return 'ERROR: missing or unsupported media'
    if not reader.isOpen or not reader.isFullyPreRead: return 'Loading media...'
    return 'Ready: {} x {}'.format(reader.width,reader.height)

def rect(c,p):
    values=lambda prefix: tuple(c.par[prefix+n].eval() for n in ('positionx','positiony','sizex','sizey'))
    boxes=rectangles(c.par.Layout.eval(),c.par.Ratio.eval(),c.par.Split.eval(),c.par.Gap.eval(),c.par.Margin.eval(),values('A'),values('B'))
    index=(0 if p=='A' else 1) ^ int(bool(c.par.Swap))
    return boxes[index]
'''

CALLBACKS = r'''
def onValueChange(par,prev):
    c=par.owner
    for p in ('A','B'):
        reader=c.op(p.lower()+'_file')
        if par.name in (p+'file',p+'source',p+'visible') and c.op('composition_math').module.selected(c,p)==2:
            reader.preload(); reader.par.cuepulse.pulse()
        elif par.name==p+'in' and c.par.Autotime: reader.par.cuepulse.pulse()

def onPulse(par):
    c=par.owner
    if par.name=='Preview': c.op('out1_image').openViewer()
    elif par.name=='Resetlayout':
        for name in ('Layout','Ratio','Split','Gap','Margin','Swap','Ontop','Apositionx','Apositiony','Asizex','Asizey','Bpositionx','Bpositiony','Bsizex','Bsizey'):
            c.par[name].val=c.par[name].default
    for p in ('A','B'):
        branch=c.op(p.lower()+'_effects')
        if par.name==p+'effects':
            for pane in ui.panes:
                if pane.type=='NETWORKEDITOR': pane.owner=branch
            branch.openParameters()
        elif par.name==p+'preview': branch.op('out1_image').openViewer()
        elif par.name==p+'restart' and c.par.Autotime: c.op(p.lower()+'_file').par.cuepulse.pulse()
        elif par.name==p+'reload':
            reader=c.op(p.lower()+'_file'); reader.par.reloadpulse.pulse()
            if c.op('composition_math').module.selected(c,p)==2: reader.preload()
        elif par.name==p+'resetcrop':
            for parameter in c.customPars:
                if parameter.page.name=='Crop '+p and parameter.isNumber and not parameter.readOnly: parameter.val=parameter.default
            c.par[p+'aspect']='free'
'''

SHADER = r'''
layout(location=0) out vec4 fragColor;
uniform vec4 uBackground, uRectA, uRectB, uA, uB, uAnchorA, uAnchorB;
uniform float uOnTop;
float inside(vec2 p) { return float(all(greaterThanEqual(p,vec2(0)))&&all(lessThanEqual(p,vec2(1)))); }
vec4 layer(int index, vec4 rect, vec4 controls, vec4 anchor) {
    vec2 q=(vUV.st-rect.xy)/max(rect.zw,vec2(.00001));
    float visible=inside(q);
    vec2 imageSize=uTD2DInfos[index].res.zw;
    vec2 frameSize=rect.zw*uTDOutputInfo.res.zw;
    float ratio=(imageSize.x/max(imageSize.y,1.))/(frameSize.x/max(frameSize.y,1.));
    vec2 extent=vec2(1.);
    if(controls.y<.5) extent=vec2(min(1.,ratio),min(1.,1./ratio));
    else if(controls.y<1.5) extent=vec2(max(1.,ratio),max(1.,1./ratio));
    q=(q-(1.-extent)*anchor.xy)/extent;
    visible*=inside(q);
    if(anchor.z>.5) q.x=1.-q.x;
    if(anchor.w>.5) q.y=1.-q.y;
    vec4 color;
    if(index==0) color=texture(sTD2DInputs[0],clamp(q,0.,1.));
    else color=texture(sTD2DInputs[1],clamp(q,0.,1.));
    color.a*=controls.x*visible*controls.z;
    return color;
}
vec4 over(vec4 a,vec4 b) {
    float alpha=a.a+b.a*(1.-a.a);
    return vec4(alpha>1e-7?(a.rgb*a.a+b.rgb*b.a*(1.-a.a))/alpha:vec3(0),alpha);
}
void main() {
    vec4 a=layer(0,uRectA,uA,uAnchorA),b=layer(1,uRectB,uB,uAnchorB);
    fragColor=TDOutputSwizzle(uOnTop<.5?over(a,over(b,uBackground)):over(b,over(a,uBackground)));
}
'''


def build(parent, context):
    """Build from the approved core modules, excluding recursive composition."""
    import inspect
    import json
    import td
    from tdimagefx.show import MODULE_TOGGLES
    root=context['PROJECT_ROOT']; core=context['CORE_ROOT']
    crop_scope={}
    exec((root/'touchdesigner/scripts/final_crop.py').read_text(encoding='utf-8'),crop_scope)
    definitions=list(PARAMETERS)
    crop_names=[]
    for p in ('A','B'):
        for definition in crop_scope['PARAMETERS']:
            if definition['name'] in {'Enabled','Status','Preview','Reset','Outputmode'}: continue
            d=dict(definition,name=p+definition['name'].lower(),page='Crop '+p)
            d.pop('uniform',None)
            # Separate crop anchor from the placement Fit / Fill anchor.
            if definition['name']=='Anchor': d['name']=p+'cropanchor'
            definitions.append(d)
            crop_names.append((p,definition['name'],d['name']))
        definitions.append(dict(name=p+'resetcrop',label='Reset Crop '+p,page='Crop '+p,type='pulse'))

    def inputs(c, source):
        runtime=c.create(td.textDAT,'composition_math')
        runtime.text='import math\nSPLITS='+repr(SPLITS)+'\n'+inspect.getsource(rectangles)+'\n'+RUNTIME
        other=c.create(td.inTOP,'in2_image'); other.par.label='image B (optional)'
        source.par.label='image A / upstream effects / output resolution'
        empty=c.create(td.constantTOP,'transparent'); empty.par.alpha=0
        empty.par.outputresolution='custom'; empty.par.resolutionw=16; empty.par.resolutionh=16
        outputs=[]
        for p,port in (('A',source),('B',other)):
            name=p.lower()
            reader=c.create(td.moviefileinTOP,name+'_file')
            reader.par.file.expr="parent().par.{}file if parent().op('composition_math').module.selected(parent(),'{}')==2 else ''".format(p,p)
            reader.par.playmode.expr="'sequential' if parent().par.Autotime else 'specify'"
            reader.par.play.expr="parent().par.Enabled and (not parent().par.Autotime or parent().par.{}play)".format(p)
            reader.par.speed.expr='parent().par.'+p+'speed'
            reader.par.indexunit='seconds'; reader.par.cuepointunit='seconds'
            reader.par.index.expr='parent().par.{0}in + parent().par.Manualtime * parent().par.{0}speed'.format(p)
            reader.par.cuepoint.expr='parent().par.'+p+'in'
            for par in (reader.par.textendleft,reader.par.textendright): par.expr="'cycle' if parent().par.{}loop else 'hold'".format(p)
            reader.par.premultrgbbyalpha='off'; reader.par.alwaysloadinitial=True
            select=c.create(td.switchTOP,name+'_source')
            for i,s in enumerate((empty,port,reader)): s.outputConnectors[0].connect(select.inputConnectors[i])
            select.par.index.expr="parent().op('composition_math').module.selected(parent(),'{}')".format(p)
            crop=context['load_tox_component'](c,core/'FinalCrop.tox',name+'_crop')
            select.outputConnectors[0].connect(crop.inputConnectors[0])
            crop.par.Enabled=True; crop.par.Outputmode='crop'
            for prefix,original,promoted in crop_names:
                if prefix!=p: continue
                for par in (par for par in crop.customPars if par.name in (original,original+'x',original+'y')):
                    suffix=par.name[len(original):]
                    par.expr='parent().par.'+promoted+suffix
            branch=c.create(td.baseCOMP,name+'_effects')
            branch.store('imagefx_branch',True)
            branch.comment='Independent Image '+p+' workflow; all effects start OFF. Select child modules to edit their controls.'
            page=branch.appendCustomPage('Effects')
            for module_name,toggle in MODULE_TOGGLES.items():
                if module_name not in CORE_FILES: continue
                context['_append_parameter'](branch,page,dict(name=toggle,label=module_name.replace('_',' ').title()+' Enabled',type='toggle',default=False))
            context['_append_parameter'](branch,page,dict(name='Applyvideofx',label='Apply Eight-Slot FX Rack',type='toggle',default=False))
            incoming=branch.create(td.inTOP,'source_image')
            crop.outputConnectors[0].connect(branch.inputConnectors[0])
            for module_name,filename in CORE_FILES.items():
                child=context['load_tox_component'](branch,core/filename,module_name)
                if module_name=='fx_rack':
                    child.par.Rootfolder=str(root)
                else: child.par.Enabled.expr='parent().par.'+MODULE_TOGGLES[module_name]
                if child.par['Autotime'] is not None:
                    child.par.Autotime=False
                    child.par.Manualtime.expr='parent(2).par.Time'
            router=branch.create(td.switchTOP,'video_fx_router'); router.par.index.expr='int(parent().par.Applyvideofx)'
            out=branch.create(td.outTOP,'out1_image'); out.display=True; out.render=True
            context['build_workflow'](branch,branch=True)
            branch.par.opviewer.expr="me.op('out1_image')"; branch.viewer=True
            outputs.append(out)
            c.par[p+'status'].expr="me.op('composition_math').module.status(me,'{}')".format(p)
            for suffix in ('play','restart'): c.par[p+suffix].enableExpr='me.par.Autotime'
            for suffix in ('positionx','positiony','sizex','sizey'): c.par[p+suffix].enableExpr="me.par.Layout=='manual'"
            for suffix in ('ratiowidth','ratioheight'): c.par[p+suffix].enableExpr="me.par.{}aspect=='custom'".format(p)
        cb=c.create(td.parameterexecuteDAT,'composition_callbacks'); cb.text=CALLBACKS
        cb.par.op='..'; cb.par.custom=True; cb.par.builtin=False; cb.par.valuechange=True; cb.par.onpulse=True
        cb.par.pars='Preview Resetlayout Afile Bfile Asource Bsource Avisible Bvisible Ain Bin Aeffects Beffects Apreview Bpreview Arestart Brestart Areload Breload Aresetcrop Bresetcrop'
        c.par.Split.enableExpr="me.par.Ratio=='custom' and me.par.Layout in ('horizontal','vertical')"
        c.par.Ratio.enableExpr="me.par.Layout in ('horizontal','vertical')"
        c.par.Gap.enableExpr="me.par.Layout in ('horizontal','vertical')"
        c.par.Status.expr="'A and B independent workflows; output follows input 1 canvas' if me.par.Enabled else 'BYPASSED: enable Two-Image Composition on the parent workflow'"
        return outputs

    bindings=[]
    for p in ('A','B'):
        bindings.append(('uRect'+p,["parent().op('composition_math').module.rect(parent(),'{}')[{}]".format(p,i) for i in range(4)]))
        bindings.append(('u'+p,['parent().par.'+p+'opacity','parent().par.'+p+'fit.menuIndex','int(parent().par.'+p+'visible)','0']))
        bindings.append(('uAnchor'+p,['parent().par.'+p+s for s in ('anchorx','anchory','flipx','flipy')]))
    # Packed binding mode binds color/xy definitions only, so bind Ontop here.
    bindings.append(('uOnTop',['parent().par.Ontop.menuIndex']))
    module,path=context['_build_reference_video_module'](parent,component_name='image_composition',component_label='Two-Image Composition',shader_source=SHADER,parameter_definitions=definitions,storage_key='tdimagefx_image_composition',module_id='tdimagefx.core.image-composition',tox_name='ImageComposition.tox',color=(.18,.36,.42),reference_video='independent two-source layouts',input_setup=inputs,packed_scalar_bindings=bindings)
    module.viewer=True
    module.par.opviewer.expr="me.op('out1_image')"
    module.save(str(path),createFolders=True)
    return module,path
