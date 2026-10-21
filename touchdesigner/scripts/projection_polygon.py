"""Click/drag polygon-mask editor. Drafts never change projector output until Apply."""
import copy
import json
import math
from functools import lru_cache
from pathlib import Path

MAX_POINTS = 32
CANVAS = (960, 540)


def cross(a, b, c):
    return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])


def segments_intersect(a, b, c, d):
    def on_segment(p, q, r):
        return (min(p[0],q[0])-1e-9 <= r[0] <= max(p[0],q[0])+1e-9 and
                min(p[1],q[1])-1e-9 <= r[1] <= max(p[1],q[1])+1e-9)
    values = cross(a,b,c),cross(a,b,d),cross(c,d,a),cross(c,d,b)
    if values[0]*values[1] < 0 and values[2]*values[3] < 0:
        return True
    return any(abs(v)<1e-9 and on_segment(p,q,r) for v,p,q,r in
               ((values[0],a,b,c),(values[1],a,b,d),(values[2],c,d,a),(values[3],c,d,b)))


def validate_points(points, allow_empty=False):
    if not isinstance(points, (list,tuple)) or len(points)>MAX_POINTS:
        raise ValueError('Use at most 32 polygon points')
    if allow_empty and not points:
        return []
    if len(points)<3:
        raise ValueError('Add at least three points, then close the shape')
    clean=[]
    for p in points:
        if not isinstance(p,(list,tuple)) or len(p)!=2:
            raise ValueError('Each point needs X and Y coordinates')
        if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or not 0<=v<=1 for v in p):
            raise ValueError('Point coordinates must be finite numbers from 0 to 1')
        clean.append((float(p[0]),float(p[1])))
    if len(set(clean))!=len(clean):
        raise ValueError('Two points overlap; move or delete one')
    n=len(clean)
    for i in range(n):
        a,b=clean[i],clean[(i+1)%n]
        for j in range(i+1,n):
            if j==(i+1)%n or (j+1)%n==i:
                continue
            if segments_intersect(a,b,clean[j],clean[(j+1)%n]):
                raise ValueError('Outline crosses or touches itself; move the points')
    area=sum(clean[i][0]*clean[(i+1)%n][1]-clean[(i+1)%n][0]*clean[i][1] for i in range(n))
    if abs(area)<1e-7:
        raise ValueError('Shape has no usable area')
    # Reject a reversal along adjacent edges, not harmless straight segments.
    for i,b in enumerate(clean):
        a,c=clean[i-1],clean[(i+1)%n]
        if abs(cross(a,b,c))<1e-9 and (a[0]-b[0])*(c[0]-b[0])+(a[1]-b[1])*(c[1]-b[1])>0:
            raise ValueError('Adjacent edges overlap; move or delete a point')
    return clean


@lru_cache(maxsize=128)
def decode_polygon(value):
    if not isinstance(value,str) or len(value)>8192:
        raise ValueError('Polygon must be a small JSON coordinate list')
    try:
        return tuple(validate_points(json.loads(value),allow_empty=True))
    except (TypeError,json.JSONDecodeError) as exc:
        raise ValueError('Invalid polygon coordinate list') from exc


def show_for(owner):
    return owner if owner.par['Output1maskpolygon'] is not None else owner.parent().op('show_control')


def committed(owner,index):
    show=show_for(owner)
    if show is None or show.par['Output'+str(index)+'maskpolygon'] is None:
        return ()
    try:return decode_polygon(show.par['Output'+str(index)+'maskpolygon'].eval())
    except ValueError:return ()


def packed(points,block,axis):
    if block==0:return len(points) if axis==0 else 0
    point=(block-1)*2+axis//2
    return points[point][axis%2] if point<len(points) else 0


def uniform(owner,index,block,axis):
    return packed(committed(owner,index),block,axis)


def segment_distance(p,a,b):
    delta=(b[0]-a[0],b[1]-a[1])
    length=delta[0]**2+delta[1]**2
    t=max(0,min(1,((p[0]-a[0])*delta[0]+(p[1]-a[1])*delta[1])/length)) if length else 0
    return math.hypot(p[0]-a[0]-t*delta[0],p[1]-a[1]-t*delta[1])


def nearest(points,uv,edges=False):
    def px(p):return p[0]*CANVAS[0],p[1]*CANVAS[1]
    p=px(uv)
    if not points:return -1
    distances=[segment_distance(p,px(q),px(points[(i+1)%len(points)])) if edges else math.dist(p,px(q)) for i,q in enumerate(points)]
    i=min(range(len(distances)),key=distances.__getitem__)
    return i if distances[i]<=12 else -1


def checkpoint(state):
    state['undo']=(state.get('undo',[])+[copy.deepcopy({k:state[k] for k in ('points','closed','selected')})])[-50:]


def gesture(state,event,u,v):
    """Pure state transition, also exercised by portable mouse-gesture tests."""
    state=copy.deepcopy(state)
    uv=[max(0,min(1,float(u))),max(0,min(1,float(v)))]
    if event=='down':
        i=nearest(state['points'],uv)
        if not state['closed'] and i==0 and len(state['points'])>=3:
            checkpoint(state);state.update(closed=True,selected=0,drag=-1)
        elif i>=0:
            checkpoint(state);state.update(selected=i,drag=i)
        elif len(state['points'])<MAX_POINTS:
            edge=nearest(state['points'],uv,edges=True) if state['closed'] else len(state['points'])-1
            if state['closed'] and edge<0:return state
            checkpoint(state);i=edge+1;state['points'].insert(i,uv)
            state.update(selected=i,drag=i)
    elif event=='move' and 0<=state.get('drag',-1)<len(state['points']):
        state['points'][state['drag']]=uv
    elif event=='up':state['drag']=-1
    return state


def state_for(editor):
    return copy.deepcopy(editor.fetch('draft',dict(target=1,points=[],closed=False,selected=-1,drag=-1,undo=[]),search=False))


def refresh(editor,state,message=''):
    editor.store('draft',copy.deepcopy(state))
    error=''
    try:validate_points(state['points'])
    except ValueError as exc:error=str(exc)
    overlay=editor.op('overlay')
    for block in range(17):
        for axis_id,axis in enumerate('xyzw'):
            overlay.par['vec{}value{}'.format(block,axis)]=packed(state['points'],block,axis_id)
    overlay.par.vec17valuex=state['selected']
    overlay.par.vec17valuey=int(state['closed'])
    overlay.par.vec17valuez=int(not error)
    editor.par.Status='Projector {} | {} / 32 points | {}{}'.format(state['target'],len(state['points']),message+' | ' if message else '',error or ('Ready to Apply Mask' if state['closed'] else 'Click the first point or Close Shape'))


def pointer(editor,event):
    canvas=editor.op('canvas')
    if event=='move' and not canvas.panel.lselect:return
    state=gesture(state_for(editor),event,float(canvas.panel.u),float(canvas.panel.v))
    refresh(editor,state)


def open_editor(show,index,open_window=True):
    editor=show.op('polygon_editor')
    pts=list(committed(show,index))
    for suffix,target in (('maskfeather','Feather'),('maskinvert','Invert'),('maskopacity','Level')):
        editor.par[target]=show.par['Output'+str(index)+suffix].eval()
    refresh(editor,dict(target=index,points=[list(p) for p in pts],closed=bool(pts),selected=-1,drag=-1,undo=[]),'Draft only; Apply changes the live mask')
    if open_window:editor.openViewer()


def action(editor,name):
    state=state_for(editor)
    show=editor.parent()
    try:
        if name=='new':
            checkpoint(state);state.update(points=[],closed=False,selected=-1,drag=-1)
        elif name=='close':
            validate_points(state['points']);checkpoint(state);state.update(closed=True,drag=-1)
        elif name=='undo':
            if state['undo']:
                old=state['undo'].pop();state.update(old);state['drag']=-1
        elif name=='delete':
            i=state['selected']
            if 0<=i<len(state['points']):
                checkpoint(state);state['points'].pop(i);state.update(selected=-1,drag=-1)
                if len(state['points'])<3:state['closed']=False
        elif name=='reload':
            # Cancel/reload affects only the unsaved draft, never the output.
            open_editor(show,state['target'],open_window=False);return
        elif name=='apply':
            if not state['closed']:raise ValueError('Close Shape before Apply Mask')
            points=validate_points(state['points'])
            prefix='Output'+str(state['target'])
            show.par[prefix+'maskpolygon']=json.dumps(points,separators=(',',':'))
            for suffix,value in (('maskx',.5),('masky',.5),('maskwidth',1),('maskheight',1),('maskrotate',0),
                                 ('maskfeather',editor.par.Feather.eval()),('maskinvert',editor.par.Invert.eval()),
                                 ('maskopacity',editor.par.Level.eval()),('maskshape','polygon'),('maskenabled',True)):
                show.par[prefix+suffix]=value
            show.UpdateMapping()
            refresh(editor,state,'APPLIED to output; Save Show to keep this mask');return
        refresh(editor,state)
    except ValueError as exc:refresh(editor,state,'NOT APPLIED: '+str(exc))


def preview_path(editor):
    show=editor.parent();index=state_for(editor)['target']
    return show.op('show_review_export').module.review_path(show,index)


def install(show,polygon_shader):
    import td
    source=Path(__file__).read_text(encoding='utf-8').split('\ndef install(show,polygon_shader):')[0]
    runtime=show.op('projection_polygon') or show.create(td.textDAT,'projection_polygon');runtime.text=source
    for owner in (show,show.parent().op('wall_output')):
        if owner is None:continue
        code=owner.op('projection_polygon') or owner.create(td.textDAT,'projection_polygon');code.text=source
        for i in (1,2,3):
            node=owner.op(('mapped' if owner==show else 'projection_map')+str(i))
            node.seq.vec.numBlocks=29
            for block in range(17):
                node.par['vec{}name'.format(block+12)]='uPolygon' if block==0 else 'uPoly'+str(block-1)
                for a,axis in enumerate('xyzw'):
                    node.par['vec{}value{}'.format(block+12,axis)].expr="op('projection_polygon').module.uniform(parent(),{},{},{})".format(i,block,a)
    editor=show.op('polygon_editor') or show.create(td.containerCOMP,'polygon_editor')
    editor.par.w,editor.par.h=1000,800
    editor.par.display=False # opens only in its own operator viewer
    page=next((p for p in editor.customPages if p.name=='Draft'),None) or editor.appendCustomPage('Draft')
    for name,kind,label,value,limits in (('Invert','Toggle','Invert / Cut a Hole',False,None),('Feather','Float','Soft Edge Width',.02,(0,.25)),('Level','Float','Visible Level',1,(0,1)),('Feed','Toggle','Show Current Projector Feed',True,None)):
        par=editor.par[name]
        if par is None:
            par=getattr(page,'append'+kind)(name,label=label)[0];par.default,par.val=value,value
        if limits:par.min,par.max=limits;par.normMin,par.normMax=limits;par.clampMin=par.clampMax=True
    if editor.par['Status'] is None:
        p=editor.appendCustomPage('Info').appendStr('Status')[0];p.readOnly=True
    def panel(kind,name,x,y,w,h):
        # TouchDesigner's default Button COMP template may append a numeric
        # suffix at creation. Normalize it so upgrades don't stack duplicates.
        item=editor.op(name) or editor.op(name+'1') or editor.create(kind,name)
        item.name=name
        item.par.x,item.par.y,item.par.w,item.par.h=x,y,w,h
        return item
    title=panel(td.textCOMP,'title',20,754,960,32)
    title.par.text='POLYGON MASK | click points / drag handles / click an edge to insert'
    title.par.fontsize=18
    for j,(name,label) in enumerate((('new','New Shape'),('close','Close Shape'),('undo','Undo'),('delete','Delete Point'),('apply','Apply Mask'),('reload','Cancel / Reload'))):
        button=panel(td.buttonCOMP,'button_'+name,20+j*160,708,154,38)
        button.par.label=label;button.par.fontsize=16
        callback=button.op('clicked') or button.create(td.panelexecuteDAT,'clicked')
        callback.par.panels='..';callback.par.panelvalue='lselect';callback.par.offtoon=True
        callback.text="def onOffToOn(panelValue):\n    e=parent().parent()\n    e.parent().op('projection_polygon').module.action(e,{!r})\n".format(name)
    preview=editor.op('feed') or editor.create(td.selectTOP,'feed')
    preview.par.top.expr="parent().parent().op('projection_polygon').module.preview_path(parent())"
    shader=editor.op('overlay_shader') or editor.create(td.textDAT,'overlay_shader')
    shader.text=polygon_shader+r'''
layout(location=0) out vec4 fragColor;
uniform vec4 uEditor, uStyle; // selected, closed, valid; feather,invert,level,feed
void main(){
    vec2 uv=vUV.st, px=uv*vec2(960,540);
    vec3 color=texture(sTD2DInputs[0],uv).rgb*uStyle.w*.6+vec3(.035);
    vec2 grid=mod(px,vec2(60));
    if(min(grid.x,grid.y)<1.)color+=vec3(.09);
    int count=int(uPolygon.x);
    vec3 tint=uEditor.z>.5?vec3(.1,.9,.6):vec3(1.,.25,.15);
    if(uEditor.y>.5&&count>=3){
        float d=polygonDistance(uv);
        float m=uStyle.x>0.?1.-smoothstep(-uStyle.x,0.,d):step(d,0.);
        if(uStyle.y>.5)m=1.-m;
        color=mix(color,color*.4+tint*.25,m*.6*uStyle.z);
    }
    for(int i=0;i<32;i++){
        if(i>=count)break;
        vec2 p=polyPoint(i)*vec2(960,540);
        if(i<count-1||uEditor.y>.5){
            vec2 q=polyPoint((i+1)%max(count,1))*vec2(960,540);
            if(segmentDistance(px,p,q)<1.5)color=tint;
        }
        float radius=length(px-p);
        if(radius<7.)color=(i==int(uEditor.x))?vec3(1,.8,.15):(i==0?vec3(.2,.7,1):vec3(1));
        if(radius<3.)color=vec3(.08);
    }
    fragColor=TDOutputSwizzle(vec4(color,1));
}
'''
    overlay=editor.op('overlay') or editor.create(td.glslTOP,'overlay')
    overlay.par.pixeldat='overlay_shader';overlay.par.glslversion='glsl460'
    overlay.par.outputresolution='custom';overlay.par.resolutionw,overlay.par.resolutionh=CANVAS
    preview.outputConnectors[0].connect(overlay.inputConnectors[0])
    overlay.seq.vec.numBlocks=19
    for block in range(17):overlay.par['vec{}name'.format(block)]='uPolygon' if block==0 else 'uPoly'+str(block-1)
    overlay.par.vec17name='uEditor';overlay.par.vec18name='uStyle'
    for axis,name in zip('xyzw',('Feather','Invert','Level','Feed')):overlay.par['vec18value'+axis].expr='parent().par.'+name
    canvas=panel(td.containerCOMP,'canvas',20,162,*CANVAS);canvas.par.top='overlay'
    callback=canvas.op('pointer_events') or canvas.create(td.panelexecuteDAT,'pointer_events')
    callback.par.panels='..';callback.par.panelvalue='lselect u v'
    callback.par.offtoon=True;callback.par.ontooff=True;callback.par.valuechange=True
    callback.text="def send(event):\n    e=parent().parent()\n    e.parent().op('projection_polygon').module.pointer(e,event)\ndef onOffToOn(panelValue):\n    if panelValue.name=='lselect':send('down')\ndef onOnToOff(panelValue):\n    if panelValue.name=='lselect':send('up')\ndef onValueChange(panelValue,prev):\n    if panelValue.name in ('u','v'):send('move')\n"
    controls=panel(td.parameterCOMP,'draft_controls',20,52,960,106)
    controls.par.op='..';controls.par.builtin=False;controls.par.custom=True
    controls.par.pagescope='Draft';controls.par.pagenames=False
    status=panel(td.textCOMP,'status',20,6,960,42)
    status.par.text.expr='parent().par.Status';status.par.fontsize=14;status.par.wordwrap=True
    refresh(editor,state_for(editor))
