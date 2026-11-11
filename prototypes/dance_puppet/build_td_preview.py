"""Run inside TouchDesigner. Creates an isolated, initially paused preview.

Does not rebuild ImageFX, replace existing operators, arm outputs, play audio,
save the current TOE or change its routing. Use save_new_project explicitly
only from a separate scratch TouchDesigner session after validation.
"""
from pathlib import Path
import json

SHADER = r'''
layout(location=0) out vec4 fragColor;
uniform vec4 uView;
void main() {
    vec2 uv = (vUV.st-.5)/max(.1,uView.x)+.5+uView.yz;
    bool inside = all(greaterThanEqual(uv,vec2(0.))) && all(lessThanEqual(uv,vec2(1.)));
    vec4 color = inside ? texture(sTD2DInputs[0],uv) : vec4(.025,.07,.12,1.);
    fragColor = TDOutputSwizzle(color * uView.w);
}
'''


def build(project_root,version='v3'):
    root = Path(project_root).resolve()
    output = root/'build/dance-puppet'
    if version not in ('v1','v2','v3','v4','v5'):
        raise ValueError('Unknown prototype version')
    preview = output/('preview' if version=='v1' else 'preview-'+version)
    component_name = 'dance_puppet_preview'+('' if version=='v1' else '_'+version)
    report = json.loads((preview/'preview-report.json').read_text(encoding='utf-8'))
    if report.get('stills_only'):
        raise RuntimeError('A still-image review is not a playable preview; render videos first')
    duration = report['rendered_frames']/report['motion']['fps']
    fps = report['motion']['fps']
    modes = report.get('compositions',['full-body','cropped'])
    for mode in modes:
        if not (preview/f'dance-puppet-{mode}.mp4').is_file():
            raise RuntimeError('Render every framing preview before building the TD component')
    host = op('/project1')
    if host is None or host.op(component_name) is not None:
        raise RuntimeError('A /project1 host without an existing '+component_name+' is required')
    module = host.create(baseCOMP,component_name)
    module.nodeX,module.nodeY = 0,-500
    module.color = (.07,.18,.31)
    page = module.appendCustomPage('Puppet Preview')

    def par(kind,name,label,default=None,low=None,high=None):
        getattr(page,'append'+kind)(name,label=label)
        p = module.par[name]
        if default is not None:
            p.default=default; p.val=default
        if low is not None:
            p.min=low; p.normMin=low; p.clampMin=True
        if high is not None:
            p.max=high; p.normMax=high; p.clampMax=True
        return p

    par('Toggle','Enabled','Preview Enabled',True)
    framing = par('Menu','Composition','Composition')
    framing.menuNames = ['full' if mode=='full-body' else mode for mode in modes]
    labels = {'full-body':'Complete Bodies','cropped':'Dark Reference Crop','source':'Match Source Framing'}
    framing.menuLabels = [labels[mode] for mode in modes]
    framing.default='full'; framing.val='full'
    par('Float','Zoom','Additional Zoom',1.,.5,3.)
    par('Float','Panx','Pan X',0.,-.5,.5)
    par('Float','Pany','Pan Y',0.,-.5,.5)
    par('Pulse','Resetview','Reset Zoom / Pan')
    par('Toggle','Playing','Playing',False)
    par('Float','Position','Seek (Seconds)',0.,0.,duration)
    par('Float','Speed','Playback Speed',1.,-2.,2.)
    par('Toggle','Loop','Loop (Cut Jumps at End)',False)
    for name,label in [('Go','GO / Restart'),('Pause','Pause / Resume'),('Stop','Stop / Rewind'),('Preview','Open Preview')]:
        par('Pulse',name,label)
    par('Float','Duration','Clip Duration',duration).readOnly = True
    par('Float','Framerate','Clip Frame Rate',fps).readOnly = True
    status = par('Str','Status','Status','')
    status.readOnly = True
    status.expr = "me.op('runtime').module.status(me)"
    runtime = module.create(textDAT,'runtime')
    runtime.text = (root/'prototypes/dance_puppet/preview_controls.py').read_text(encoding='utf-8')
    runtime.nodeX,runtime.nodeY=-600,-300
    select = module.create(switchTOP,'composition')
    select.par.index.expr = "parent().par.Composition.menuIndex"
    for index,mode in enumerate(modes):
        movie = module.create(moviefileinTOP,'movie_'+mode.replace('-','_'))
        movie.par.file = str(preview/f'dance-puppet-{mode}.mp4')
        movie.par.playmode = 'specify'
        movie.par.indexunit = 'seconds'
        movie.par.index.expr = 'parent().par.Position'
        # TD still needs Play on to decode new specified indices while paused.
        movie.par.play = True
        movie.par.textendleft = 'hold'
        movie.par.textendright = 'hold'
        movie.par.alwaysloadinitial = True
        movie.nodeX,movie.nodeY = -500,-index*180
        movie.outputConnectors[0].connect(select.inputConnectors[index])
    select.nodeX,select.nodeY=-220,0
    shader = module.create(textDAT,'view_shader')
    shader.text=SHADER
    shader.nodeX,shader.nodeY=-200,-300
    framing_top=module.create(glslTOP,'framing')
    framing_top.par.pixeldat = shader.path
    framing_top.par.vec0name='uView'
    for axis,name in zip('xyzw',('Zoom','Panx','Pany','Enabled')):
        framing_top.par['vec0value'+axis].expr='parent().par.'+name
    select.outputConnectors[0].connect(framing_top.inputConnectors[0])
    framing_top.nodeX,framing_top.nodeY=40,0
    out=module.create(outTOP,'out1')
    framing_top.outputConnectors[0].connect(out.inputConnectors[0])
    out.nodeX,out.nodeY=270,0
    out.display=True; out.render=True
    module.par.opviewer='out1'; module.viewer=True
    callbacks=module.create(parameterexecuteDAT,'buttons')
    callbacks.par.op='..'
    callbacks.par.pars='Go Pause Stop Resetview Preview'
    callbacks.par.custom=True; callbacks.par.builtin=False
    callbacks.par.valuechange=False; callbacks.par.onpulse=True
    callbacks.text="def onPulse(par):\n    parent().op('runtime').module.action(parent(),par.name)\n"
    callbacks.nodeX,callbacks.nodeY=80,-300
    timer=module.create(executeDAT,'tick')
    timer.par.framestart=True
    timer.text="def onFrameStart(frame):\n    parent().op('runtime').module.tick(parent(),absTime.seconds)\n"
    timer.nodeX,timer.nodeY=260,-300
    if version=='v5':
        finish_builder=module.create(textDAT,'finish_builder')
        finish_builder.text=(root/'prototypes/dance_puppet/preview_effects.py').read_text(encoding='utf-8')
        finish_builder.module.install(module,root)
    readme=module.create(textDAT,'README')
    readme.text=('EXPERIMENTAL 2.5D mocap puppet preview, not the final show module.\n'
        f'All compositions use the same {duration:g}-second test choreography ({version}).\n'
        'v2/v3/v4/v5 start at source time zero, using tracked choreography in shared stage space.\n'
        'GO starts/restarts. Pause toggles pause/resume. Stop rewinds. Seek works while paused.\n'
        'Loop is off because this excerpt is not a seamless cycle.\n'
        'This component plays an offline render; the mesh rig and tracking scripts live under prototypes/dance_puppet.\n'+
        ('v5 refines relative rotations, view changes and joint bending. Motion Finish adds optional blur and trails, both OFF by default.\n'
         'History clears on seek, restart, stop, speed, framing and enable changes. Pause holds the current finish.\n'
         'The 60fps render uses interpolated 30fps observations; not new mocap measurements.\n' if version=='v5'
         else 'v4 preserves character proportions with connected joints and one deforming lower robe; not recovered 3D.\n' if version=='v4'
         else 'v3 uses separate view cards, overlapping robe panels, and independent props; not recovered 3D.\n' if version=='v3'
         else 'Legacy rig: front-facing connected mesh, with garment/prop stretching limitations.\n')+
        'No audio, no audience windows, no changes to production ImageFX routing.\n')
    readme.nodeX,readme.nodeY=470,-300
    module.par.Status.readOnly=True
    print('Created',module.path,'(paused; no show outputs attached)')
    return module


def save_new_project(project_root,version='v3'):
    """Save a new prototype filename only; refuses existing destinations."""
    root = Path(project_root).resolve()
    folder = root/'build/dance-puppet'
    if version not in ('v1','v2','v3','v4','v5'):
        raise ValueError('Unknown prototype version')
    suffix = '' if version=='v1' else '_'+version
    toe = folder/f'DancePuppet25D_Prototype{suffix}.toe'
    tox = folder/f'DancePuppet25D_Preview{suffix}.tox'
    if toe.exists() or tox.exists():
        raise RuntimeError('Prototype destination already exists; not overwriting')
    if op('/project1/imagefx_demo') is not None or op('/project1/td_imagefx') is not None:
        raise RuntimeError('Refusing to save an ImageFX production / harness session as the prototype')
    module = op('/project1/dance_puppet_preview'+suffix)
    if module is None:
        raise RuntimeError('Build and validate the prototype first')
    module.par.Playing=False
    module.par.Position=0
    module.par.Enabled=True
    module.par.Composition='full'
    module.op('runtime').module.action(module,'Resetview')
    if version=='v5':
        module.op('effects_runtime').module.action(module,'Resetfx')
    module.save(str(tox))
    if project.save(str(toe),saveExternalToxs=False) is not True:
        raise RuntimeError('TouchDesigner did not confirm saving the prototype')
    print('Saved new prototype only:',toe)
    return str(toe)
