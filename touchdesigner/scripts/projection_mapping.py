"""Per-projector masks and calibration UI; embedded at build time, off by default."""
from pathlib import Path

MASK_SUFFIXES = ('maskenabled', 'maskshape', 'maskfile', 'maskchannel', 'maskinvert',
                 'maskopacity', 'maskx', 'masky', 'maskwidth', 'maskheight',
                 'maskrotate', 'maskfeather', 'edgeall', 'edgegamma', 'maskpolygon')
RESET_GROUPS = {
    'corners': ('blx','bly','brx','bry','trx','try','tlx','tly'),
    'crop': ('cropleft','cropright','cropbottom','croptop'),
    'transform': ('rotate','flipx','flipy'),
    'mask': tuple(s for s in MASK_SUFFIXES if s.startswith('mask')),
    'edges': ('edgeleft','edgeright','edgebottom','edgetop','edgeall','edgegamma'),
    'grade': ('brightness','gamma'),
    'resolution': ('width','height'),
}
RESET_CONTROLS = (
    ('Resetcorners', 'Reset Corner Pin', 'corners', 'Shape'),
    ('Resetcrop', 'Reset Source Crop', 'crop', 'Shape'),
    ('Resettransform', 'Reset Rotation / Flips', 'transform', 'Shape'),
    ('Resetmask', 'Reset Mask (Clear / Disable)', 'mask', 'Mask'),
    ('Resetedges', 'Reset Soft Edges', 'edges', 'Edges'),
    ('Resetgrade', 'Reset Brightness / Gamma', 'grade', 'Output'),
    ('Resetresolution', 'Reset Resolution to 1080p', 'resolution', 'Output'),
)
ACTIONS = ('Editmapping', 'Previewmapping', 'Drawmask', 'Resetmapping',
           *(name for name,_,_,_ in RESET_CONTROLS), 'Resetallprojectors', 'Savemapping')
IMAGE_SUFFIXES = {'.png', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff', '.exr'}


def mask_file_value(value):
    if not isinstance(value, str) or len(value) > 4096 or '\x00' in value or '://' in value:
        raise ValueError('Mask file must be a local image path (up to 4096 characters)')
    return value


def mask_file(show, index):
    prefix = 'Output' + str(index)
    if not show.par[prefix + 'maskenabled'] or show.par[prefix + 'maskshape'] != 'image':
        return ''
    value = mask_file_value(show.par[prefix + 'maskfile'].eval()).strip()
    if not value:
        return ''
    path = Path(value)
    if not path.is_absolute():
        path = Path(show.par.Libraryroot.eval()) / path
    return str(path) if path.suffix.lower() in IMAGE_SUFFIXES and path.is_file() else ''


def mask_ready(show, index):
    reader = show.op('projection_mask_file' + str(index))
    return bool(mask_file(show, index) and reader is not None and reader.isOpen and not reader.isInvalid)


def mask_source(show, index):
    return 'projection_mask_file' + str(index) if mask_ready(show, index) else 'black'


def status(show, index):
    prefix = 'Output' + str(index)
    state = show.par.Mappingstatus.eval()
    if not show.par[prefix + 'maskenabled']:
        return state + ' | Mask off'
    if show.par[prefix + 'maskshape'] == 'image' and not mask_ready(show, index):
        return state + ' | MASK UNAVAILABLE: output masked black (check local image)'
    if show.par[prefix + 'maskshape'] == 'polygon' and not show.op('projection_polygon').module.committed(show,index):
        return state + ' | POLYGON EMPTY / INVALID: draw and apply a mask (output black)'
    return state + ' | ' + show.par[prefix + 'maskshape'].eval().title() + ' mask active'


def wall_uniform(wall, index, block, axis):
    """Mirror committed geometry, not invalid edits; tolerate standalone wall copies."""
    show = wall.parent().op('show_control')
    mapped = show.op('mapped' + str(index)) if show is not None else None
    defaults = ((1,0,0,0),(0,1,0,0),(0,0,1,0),(0,0,1,1),(1,1,0,0),
                (0,0,0,0),(0,0,0,index),(0,0,0,1),(.5,.5,1,1),(0,0,0,0),(0,1,0,0))
    if mapped is None or mapped.par['vec10name'] is None:
        return defaults[block][axis]
    if block == 3:
        data = show.op('projection_crop_data')
        return float(data[index-1, axis]) if data is not None else defaults[3][axis]
    if block == 4 and axis == 2:
        # Wall's own safety gate handles master blackout; individual blackout
        # still belongs to this projector in non-show source modes.
        return float(show.par['Output' + str(index) + 'blackout'])
    if block == 4 and axis == 3:
        return 0  # Preserve the wall's numbered calibration image.
    return mapped.par['vec{}value{}'.format(block, 'xyzw'[axis])].eval()


def wall_mask_source(wall, index):
    show = wall.parent().op('show_control')
    node = show.op('projection_mask' + str(index)) if show is not None else None
    return node.path if node is not None else wall.op('black').path


def reset_suffixes(section):
    if section in RESET_GROUPS:
        return RESET_GROUPS[section]
    if section not in ('mapping', 'all'):
        raise ValueError('Unknown mapping reset section')
    # "mapping" retains the original helper's geometry-only contract.
    groups = RESET_GROUPS if section == 'all' else tuple(RESET_GROUPS)[:5]
    return tuple(s for group in groups for s in RESET_GROUPS[group])


def reset_mapping(show, indices, section='all'):
    indices=tuple(indices)
    if not indices or any(type(i) is not int or i not in (1,2,3) for i in indices):
        raise ValueError('Choose projector 1, 2 or 3')
    suffixes=reset_suffixes(section)
    # Resolve every parameter before changing anything. Routing, cue state,
    # output mode and safety gates are deliberately outside this allowlist.
    parameters=[show.par['Output'+str(i)+s] for i in indices for s in suffixes]
    if any(p is None for p in parameters):
        raise ValueError('Mapping controls are incomplete; rebuild this project')
    for parameter in parameters:
        parameter.val=parameter.default
    show.UpdateMapping()
    if 'maskpolygon' in suffixes:
        polygon=show.op('projection_polygon')
        editor=show.op('polygon_editor')
        if polygon is not None and editor is not None:
            target=polygon.module.state_for(editor)['target']
            if target in indices:
                polygon.module.open_editor(show,target,open_window=False)
    show.par.Mappinghelp='Reset {} on projector(s) {}. Save Show to keep this change; routing and blackouts unchanged.'.format(section,', '.join(map(str,indices)))


def reset_selected(show, section='mapping'):
    reset_mapping(show,(int(show.par.Mappingprojector.eval()),),section)


def on_editor_pulse(editor, action):
    show=editor.parent()
    try:
        index=int(editor.fetch('projection_index',0,search=False))
        section=next((group for name,_,group,_ in RESET_CONTROLS if name==action),None)
        if action=='Resetmapping':section='all'
        if section is None:return False
        reset_mapping(show,(index,),section)
        return True
    except Exception as exc:
        show.par.Mappinghelp=str(exc)
        return False


def on_pulse(show, action):
    if action not in ACTIONS:
        return False
    try:
        index = int(show.par.Mappingprojector.eval())
        if action == 'Editmapping':
            target = show.op('projection' + str(index))
            target.currentPage = target.customPages[0]
            target.openParameters()
        elif action == 'Previewmapping':
            path = show.op('show_review_export').module.review_path(show, index)
            show.op(path).openViewer()
        elif action == 'Drawmask':
            show.op('projection_polygon').module.open_editor(show,index)
        elif action == 'Savemapping':
            show.SaveShow()
            show.par.Mappinghelp='Mapping and cues saved to '+show.par.Showfile.eval()+'. Unapplied mask drafts are not saved.'
        elif action == 'Resetallprojectors':
            reset_mapping(show,(1,2,3),'all')
        else:
            section=next((group for name,_,group,_ in RESET_CONTROLS if name==action),'all')
            reset_selected(show,section)
        return True
    except Exception as exc:
        show.par.Mappinghelp = str(exc)
        return False


POLYGON_SHADER = r'''
uniform vec4 uPolygon;
uniform vec4 uPoly0,uPoly1,uPoly2,uPoly3,uPoly4,uPoly5,uPoly6,uPoly7;
uniform vec4 uPoly8,uPoly9,uPoly10,uPoly11,uPoly12,uPoly13,uPoly14,uPoly15;
vec2 polyPoint(int i){
    vec4 points[16]=vec4[16](uPoly0,uPoly1,uPoly2,uPoly3,uPoly4,uPoly5,uPoly6,uPoly7,
                            uPoly8,uPoly9,uPoly10,uPoly11,uPoly12,uPoly13,uPoly14,uPoly15);
    return i%2==0?points[i/2].xy:points[i/2].zw;
}
float segmentDistance(vec2 p,vec2 a,vec2 b){
    vec2 v=b-a;
    return length(p-a-v*clamp(dot(p-a,v)/max(dot(v,v),1e-12),0.,1.));
}
float polygonDistance(vec2 p){
    int count=clamp(int(uPolygon.x),0,32);
    bool inside=false;float distance=2.;
    for(int i=0;i<32;i++){
        if(i>=count)break;
        vec2 a=polyPoint(i),b=polyPoint((i+1)%max(count,1));
        distance=min(distance,segmentDistance(p,a,b));
        if((a.y>p.y)!=(b.y>p.y)){
            float x=(b.x-a.x)*(p.y-a.y)/(b.y-a.y)+a.x;
            if(p.x<x)inside=!inside;
        }
    }
    return inside?-distance:distance;
}
'''

SHADER_MASK = r'''
uniform vec4 uMask, uMaskpose, uMaskstyle, uEdgeextra, uMapping;
float imageMask(vec2 uv) {
    if(any(lessThan(uv,vec2(0)))||any(greaterThan(uv,vec2(1)))) return 0.;
    vec4 t=texture(sTD2DInputs[1],uv);
    return uMaskstyle.z>.5 ? t.a : dot(t.rgb,vec3(.2126,.7152,.0722))*t.a;
}
float projectionMask(vec2 local) {
    if(uMask.x<.5) return 1.;
    vec2 size=max(uMaskpose.zw,vec2(.001));
    float angle=radians(uMaskstyle.x);
    vec2 p=mat2(cos(angle),-sin(angle),sin(angle),cos(angle))*(local-uMaskpose.xy);
    float feather=max(uMaskstyle.y,0.);
    float mask=1.;
    if(uMask.y>2.5) {
        // Polygons are drawn in the projector frame, after corner-pin shaping.
        // Empty/invalid polygons fail closed before inversion.
        if(uPolygon.x<3.)return 0.;
        vec2 uv=mat2(cos(angle),-sin(angle),sin(angle),cos(angle))*(vUV.st-uMaskpose.xy)/size+.5;
        float d=polygonDistance(uv);
        mask=feather>0.?1.-smoothstep(-feather,0.,d):step(d,0.);
    } else if(uMask.y>1.5) {
        // Missing/invalid files fail closed even with inversion enabled.
        if(uMaskstyle.w<.5) return 0.;
        vec2 uv=p/size+.5;
        if(feather<=0.) mask=imageMask(uv);
        else {
            vec2 radius=vec2(feather)/size;
            mask=0.;
            for(int y=-1;y<=1;y++) for(int x=-1;x<=1;x++) {
                float weight=float((x==0?2:1)*(y==0?2:1));
                mask+=imageMask(uv+vec2(x,y)*radius)*weight/16.;
            }
        }
    } else {
        vec2 d=abs(p)-size*.5;
        float distance=length(max(d,vec2(0)))+min(max(d.x,d.y),0.);
        if(uMask.y>.5) distance=(length(p/(size*.5))-1.)*min(size.x,size.y)*.5;
        mask=feather>0. ? 1.-smoothstep(-feather,0.,distance) : step(distance,0.);
    }
    if(uMask.z>.5) mask=1.-mask;
    return clamp(mask,0.,1.)*uMask.w;
}
'''


def enhanced_shader(original):
    source = original.replace('void main() {', POLYGON_SHADER + SHADER_MASK + '\nvoid main() {', 1)
    source = source.replace('    vec3 q =', '    if(uMapping.x>.5){fragColor=TDOutputSwizzle(vec4(texture(sTD2DInputs[0],vUV.st).rgb,1));return;}\n    vec3 q =', 1)
    source = source.replace('    float edge = 1.0;', '    vec4 edges=max(uEdges,vec4(uEdgeextra.x));\n    float edge = 1.0;')
    for axis in 'xyzw':
        source = source.replace('uEdges.'+axis, 'edges.'+axis)
    source = source.replace('    color = pow(', '    edge=pow(clamp(edge,0.,1.),max(uEdgeextra.y,.1))*projectionMask(local);\n    color = pow(', 1)
    return source


def install(show, mapping_shader):
    """Add neutral controls and two-way editors without reinitializing cue state."""
    import td
    runtime = show.op('projection_mapping') or show.create(td.textDAT, 'projection_mapping')
    runtime.text = Path(__file__).read_text(encoding='utf-8').split('\ndef install(show, mapping_shader):')[0]
    def page(owner, name):
        return next((p for p in owner.customPages if p.name == name), None) or owner.appendCustomPage(name)
    def parameter(p, name, kind, label, default, limits=None, menu=None):
        item = show.par[name]
        if item is None:
            item = getattr(p, 'append'+kind)(name, label=label)[0]
            if menu:item.menuNames, item.menuLabels = [a for a,b in menu], [b for a,b in menu]
            item.default, item.val = default, default
        if menu:
            previous=item.eval()
            item.menuNames, item.menuLabels = [a for a,b in menu], [b for a,b in menu]
            item.val=previous
        if limits:
            item.min,item.max=limits; item.normMin,item.normMax=limits
            item.clampMin=item.clampMax=True
        return item
    definitions = (
        ('maskenabled','Toggle','Enable Mask',False,None,None),
        ('maskshape','Menu','Mask Shape','rectangle',None,[('rectangle','Rectangle'),('ellipse','Ellipse / Circle'),('image','Image Mask'),('polygon','Custom Polygon (Draw Mask)')]),
        ('maskpolygon','Str','Applied Polygon Points','[]',None,None),
        ('maskfile','File','Local Mask Image','',None,None),
        ('maskchannel','Menu','Image Mask Channel','luma',None,[('luma','White Visible / Black Blocked'),('alpha','Alpha Channel')]),
        ('maskinvert','Toggle','Invert Mask / Cut a Hole',False,None,None),
        ('maskopacity','Float','Masked Output Level',1,(0,1),None),
        ('maskx','Float','Mask Center X',.5,(-1,2),None),
        ('masky','Float','Mask Center Y',.5,(-1,2),None),
        ('maskwidth','Float','Mask Width',1,(.001,2),None),
        ('maskheight','Float','Mask Height',1,(.001,2),None),
        ('maskrotate','Float','Mask Rotation',0,(-180,180),None),
        ('maskfeather','Float','Mask Feather / Image Softness',.02,(0,.25),None),
        ('edgeall','Float','All Edges Softness',0,(0,.45),None),
        ('edgegamma','Float','Edge Blend Curve',1,(.1,4),None),
    )
    data=show.op('projection_crop_data') or show.create(td.tableDAT,'projection_crop_data')
    if data.numRows != 3:
        data.clear()
        for i in (1,2,3): data.appendRow([0,0,1,1])
    for index in (1,2,3):
        prefix='Output'+str(index)
        p=page(show,'Output '+str(index))
        for suffix,kind,label,default,limits,menu in definitions:
            parameter(p,prefix+suffix,kind,label,default,limits,menu)
        show.par[prefix+'maskpolygon'].readOnly=True
        reader=show.op('projection_mask_file'+str(index)) or show.create(td.moviefileinTOP,'projection_mask_file'+str(index))
        reader.par.file.expr="parent().op('projection_mapping').module.mask_file(parent(),{})".format(index)
        reader.par.play=False
        mask=show.op('projection_mask'+str(index)) or show.create(td.selectTOP,'projection_mask'+str(index))
        mask.par.top.expr="parent().op('projection_mapping').module.mask_source(parent(),{})".format(index)
        mapped=show.op('mapped'+str(index))
        show.op('mapped'+str(index)+'_shader').text=enhanced_shader(mapping_shader)
        mask.outputConnectors[0].connect(mapped.inputConnectors[1])
        mapped.seq.vec.numBlocks=12
        groups=(('uMask',('maskenabled','maskshape','maskinvert','maskopacity')),
                ('uMaskpose',('maskx','masky','maskwidth','maskheight')),
                ('uMaskstyle',('maskrotate','maskfeather','maskchannel',None)),
                ('uEdgeextra',('edgeall','edgegamma',None,None)))
        for block,(name,suffixes) in enumerate(groups,7):
            mapped.par['vec{}name'.format(block)]=name
            for axis,suffix in zip('xyzw',suffixes):
                if suffix:
                    mapped.par['vec{}value{}'.format(block,axis)].expr='parent().par.'+prefix+suffix+('.menuIndex' if suffix in ('maskshape','maskchannel') else '')
        mapped.par.vec9valuew.expr="parent().op('projection_mapping').module.mask_ready(parent(),{})".format(index)
        mapped.par.vec11name='uMapping';mapped.par.vec11valuex=0
        editor=show.op('projection'+str(index)) or show.create(td.baseCOMP,'projection'+str(index))
        editor.store('projection_index',index)
        editor.comment='Projector {} mapping; two-way links to Show Control. X right, Y up, normalized 0..1.'.format(index)
        for source in show.customPars:
            if not source.name.startswith(prefix): continue
            suffix=source.name[len(prefix):]
            group=('Mask' if suffix.startswith('mask') else 'Edges' if suffix.startswith('edge') else
                   'Output' if suffix in ('width','height','track','blackout','brightness','gamma') else 'Shape')
            alias=source.name[len(prefix):].capitalize()
            item=editor.par[alias]
            kind = ('Menu' if source.isMenu else 'Toggle' if source.isToggle else
                    'Int' if source.isInt else 'Float' if source.isNumber else 'Str' if suffix=='maskpolygon' else 'File')
            label=source.label + (' '+suffix[-1].upper() if suffix in ('blx','bly','brx','bry','trx','try','tlx','tly') else '')
            if item is None: item=getattr(page(editor,group),'append'+kind)(alias,label=label)[0]
            item.default=source.default
            item.readOnly=source.readOnly
            if source.isMenu:item.menuNames,item.menuLabels=source.menuNames,source.menuLabels
            if source.isNumber:
                item.min,item.max=source.min,source.max;item.normMin,item.normMax=source.normMin,source.normMax
                item.clampMin,item.clampMax=source.clampMin,source.clampMax
            item.bindExpr='me.parent().par.'+source.name;item.mode=type(item.mode).BIND
        for name,label,_,group in (*RESET_CONTROLS,('Resetmapping','Reset ALL Mapping (This Projector)','all','Output')):
            item=editor.par[name]
            if item is None:item=page(editor,group).appendPulse(name,label=label)[0]
            item.label=label
        events=editor.op('reset_callbacks') or editor.create(td.parameterexecuteDAT,'reset_callbacks')
        events.par.op='..';events.par.pars=' '.join([name for name,_,_,_ in RESET_CONTROLS]+['Resetmapping'])
        events.par.onpulse=True;events.par.valuechange=False;events.par.custom=True;events.par.builtin=False
        events.text="def onPulse(par):\n    e=parent()\n    e.parent().op('projection_mapping').module.on_editor_pulse(e,par.name)\n"
        editor.sortCustomPages('Shape','Mask','Edges','Output')
    p=page(show,'Projection Mapping')
    parameter(p,'Mappingprojector','Menu','Projector to Adjust','1',menu=[('1','1 / Left'),('2','2 / Center'),('3','3 / Right')])
    labels=dict(Editmapping='Open Mapping Controls',Previewmapping='Preview Mapped Projector',
                Drawmask='Draw Custom Mask (Mouse)',Resetmapping='Reset ALL Mapping (Selected Projector)',
                Resetallprojectors='Reset ALL Mapping (All 3 Projectors)',Savemapping='Save Mapping + Cues to Show File')
    labels.update({name:label for name,label,_,_ in RESET_CONTROLS})
    for name in ACTIONS:
        item=show.par[name]
        if item is None:item=p.appendPulse(name,label=labels[name])[0]
        item.label=labels[name]
    info=parameter(p,'Projectionstatus','Str','Selected Mapping Status','')
    info.readOnly=True;info.expr="me.op('projection_mapping').module.status(me,int(me.par.Mappingprojector.eval()))"
    info=parameter(p,'Mappinghelp','Str','Mapping Help','Reset ALL includes resolution and grade, not routing/blackout. Stop All, then Save Mapping + Cues. Apply polygon drafts first.')
    info.readOnly=True
    callback=show.op('projection_mapping_callbacks') or show.create(td.parameterexecuteDAT,'projection_mapping_callbacks')
    callback.par.op='..';callback.par.pars=' '.join(ACTIONS);callback.par.onpulse=True
    callback.par.valuechange=False;callback.par.custom=True;callback.par.builtin=False
    callback.text="def onPulse(par):\n    parent().op('projection_mapping').module.on_pulse(parent(),par.name)\n"
    guard="    if parent().op('projection_mapping') is not None and par.name in parent().op('projection_mapping').module.ACTIONS:\n        return\n"
    actions=show.op('show_parameters')
    if guard not in actions.text:actions.text=actions.text.replace('def onPulse(par):\n','def onPulse(par):\n'+guard,1)
    inspector=show.op('cue_inspector')
    scope=inspector.par.pagescope.eval()
    if "'Projection Mapping'" not in scope:inspector.par.pagescope=scope.replace("'Wall Output'","'Wall Output' 'Projection Mapping'",1)
    order=[p.name for p in show.customPages if p.name!='Projection Mapping']
    order.insert(order.index('Wall Output')+1,'Projection Mapping');show.sortCustomPages(*order)
    wall=show.parent().op('wall_output')
    if wall is not None:
        code=wall.op('projection_mapping') or wall.create(td.textDAT,'projection_mapping')
        code.text=runtime.text
        for index in (1,2,3):
            name='projection_map'+str(index)
            text=wall.op(name+'_shader') or wall.create(td.textDAT,name+'_shader');text.text=enhanced_shader(mapping_shader)
            mask=wall.op(name+'_mask') or wall.create(td.selectTOP,name+'_mask')
            mask.par.top.expr="parent().op('projection_mapping').module.wall_mask_source(parent(),{})".format(index)
            node=wall.op(name) or wall.create(td.glslTOP,name)
            node.par.pixeldat=node.relativePath(text);node.par.glslversion='glsl460'
            node.par.outputresolution='custom';node.par.resolutionw,node.par.resolutionh=1920,1080
            node.par.format='rgba8fixed';node.par.inputextenduv='hold'
            wall.op('projector'+str(index)).outputConnectors[0].connect(node.inputConnectors[0])
            mask.outputConnectors[0].connect(node.inputConnectors[1])
            node.seq.vec.numBlocks=12
            names=('uRow0','uRow1','uRow2','uCrop','uGrade','uEdges','uTransform','uMask','uMaskpose','uMaskstyle','uEdgeextra')
            for block,name in enumerate(names):
                node.par['vec{}name'.format(block)]=name
                for axis_id,axis in enumerate('xyzw'):
                    node.par['vec{}value{}'.format(block,axis)].expr="parent().op('projection_mapping').module.wall_uniform(parent(),{},{},{})".format(index,block,axis_id)
            node.par.vec11name='uMapping';node.par.vec11valuex.expr="int(parent().par.Sourcemode == 'show' and not parent().par.Testpattern)"
            node.outputConnectors[0].connect(wall.op('p'+str(index)+'_out').inputConnectors[0])
    polygon_path=Path(__file__).with_name('projection_polygon.py')
    scope=dict(__file__=str(polygon_path),__name__='_projection_polygon_install')
    exec(compile(polygon_path.read_text(encoding='utf-8'),str(polygon_path),'exec'),scope)
    scope['install'](show,POLYGON_SHADER)
    show.ext.ShowControlExt._mapping_key=None
    show.UpdateMapping()
    if show.op('show_panel_layout') is not None:
        show.op('show_panel_layout').module.configure(show)
