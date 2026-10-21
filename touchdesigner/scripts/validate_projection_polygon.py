"""Off-air GPU, editor, persistence and safety checks for click-drawn masks."""
import copy
import json
import traceback
from datetime import datetime,timezone
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[2]


def validate(write_report=True):
    original=op('/project1/imagefx_demo/show_control')
    before=copy.deepcopy(original.ext.ShowControlExt.document)
    host=op('/project1').create(baseCOMP,'polygon_qa')
    wall=host.copy(original.parent().op('wall_output'),name='wall_output')
    show=host.copy(original,name='show_control');show.op('show_tick').par.active=False
    runtime=show.op('projection_polygon').module;editor=show.op('polygon_editor')
    checks={};report=dict(ok=False,generated_at=datetime.now(timezone.utc).isoformat(),hardware_outputs_tested=False)
    try:
        white=host.create(constantTOP,'white');white.par.outputresolution='custom'
        white.par.resolutionw,white.par.resolutionh=320,180
        white.par.colorr,white.par.colorg,white.par.colorb=1,1,1
        show.par.Masterblackout=False;show.par.Routingmode='independent'
        for i in (1,2,3):
            show.par['Output{}width'.format(i)]=320;show.par['Output{}height'.format(i)]=180
            show.op('output_source'+str(i)).par.top=white.path
        def pixels(node):
            show.UpdateMapping();node.cook(force=True)
            if node.errors():raise AssertionError(node.errors())
            return np.array(node.numpyArray(delayed=False),copy=True)
        def output(i):return pixels(show.op('mapped'+str(i)))[:,:,0]
        def draft(i,points,closed=True):
            state=dict(target=i,points=copy.deepcopy(points),closed=closed,selected=-1,drag=-1,undo=[])
            runtime.refresh(editor,state)
            editor.par.Feather=0;editor.par.Invert=False;editor.par.Level=1
        triangle=[[.15,.1],[.85,.1],[.5,.9]]
        for i in (1,2,3):
            prefix='Output'+str(i)
            baseline=output(i)
            draft(i,triangle)
            checks['draft_keeps_output_'+str(i)]=np.array_equal(output(i),baseline)
            runtime.action(editor,'apply');a=output(i)
            checks['apply_enables_polygon_'+str(i)]=bool(show.par[prefix+'maskenabled']) and show.par[prefix+'maskshape']=='polygon'
            checks['triangle_coverage_'+str(i)]=a[90,160]>.9 and a[165,15]==0 and a[5,160]==0
            checks['other_outputs_unchanged_'+str(i)]=all(np.min(output(j))>.99 for j in (1,2,3) if j!=i)
            show.par[prefix+'maskinvert']=True
            checks['inversion_'+str(i)]=np.max(np.abs(output(i)+a-1))<.005
            show.par[prefix+'maskinvert']=False;show.par[prefix+'maskfeather']=.08
            soft=output(i)
            checks['feather_'+str(i)]=np.any((soft>.01)&(soft<.99)) and np.sum(soft)<np.sum(a)
            show.par[prefix+'maskopacity']=.3
            checks['level_'+str(i)]=.29<output(i)[90,160]<.31
            show.par[prefix+'maskenabled']=False
            checks['bypass_exact_'+str(i)]=np.array_equal(output(i),baseline)
            show.par.Mappingprojector=str(i);show.op('projection_mapping').module.reset_selected(show)
        # Concave contour is checked pixel-for-pixel against CPU even/odd fill.
        concave=[[.1,.1],[.9,.1],[.9,.9],[.5,.4],[.1,.9]]
        draft(1,concave);runtime.action(editor,'apply');a=output(1)
        x,y=np.meshgrid((np.arange(320)+.5)/320,(np.arange(180)+.5)/180)
        expected=np.zeros(x.shape,dtype=bool)
        for j,p in enumerate(concave):
            q=concave[(j+1)%len(concave)]
            if p[1]!=q[1]:expected^=((p[1]>y)!=(q[1]>y))&(x<(q[0]-p[0])*(y-p[1])/(q[1]-p[1])+p[0])
        checks['concave_gpu_matches_cpu']=np.count_nonzero((a>.5)!=expected)<4
        # Invalid drafts do not replace the previously committed contour.
        saved=show.par.Output1maskpolygon.eval();stable=output(1)
        draft(1,[[0,0],[1,1],[0,1],[1,0]]);runtime.action(editor,'apply')
        checks['invalid_apply_keeps_mask']=show.par.Output1maskpolygon==saved and np.array_equal(output(1),stable)
        checks['invalid_apply_status']='NOT APPLIED' in editor.par.Status.eval()
        draft(1,triangle,closed=False);runtime.action(editor,'apply')
        checks['open_draft_rejected']=show.par.Output1maskpolygon==saved
        runtime.action(editor,'close');runtime.action(editor,'apply')
        checks['close_then_apply']=show.par.Output1maskpolygon!=saved
        state=runtime.state_for(editor);state['selected']=1;runtime.refresh(editor,state)
        runtime.action(editor,'delete');checks['delete_selected']=len(runtime.state_for(editor)['points'])==2
        runtime.action(editor,'undo');checks['undo_restores_point']=len(runtime.state_for(editor)['points'])==3
        runtime.action(editor,'new');checks['new_is_draft_only']=runtime.state_for(editor)['points']==[] and bool(show.par.Output1maskenabled)
        # Reset empty geometry fails closed, including inverted masks.
        show.par.Output1maskpolygon='[]';show.par.Output1maskinvert=True
        checks['empty_polygon_fail_closed']=np.max(output(1))==0
        draft(1,triangle);runtime.action(editor,'apply')
        # Wall mapping uses the same screen-space mask; never applied twice.
        show.par.Output1width=1920;show.par.Output1height=1080
        wall.par.Enabled=True;wall.par.Blackout=False;wall.par.Testpattern=False;wall.par.Sourcemode='show'
        checks['wall_same_pixels']=np.max(np.abs(output(1)-pixels(wall.op('p1_out'))[:,:,0]))<.005
        wall.par.Sourcemode='independent';wall.par.Projector1top=white.path;wall.par.Fit='stretch'
        checks['wall_independent_same_pixels']=np.max(np.abs(output(1)-pixels(wall.op('p1_out'))[:,:,0]))<.005
        # Masks and editor geometry are show calibration, not cue looks.
        path=ROOT/'build/envoy-validation/polygon-mask-show.json'
        show.par.Showfile=str(path);show.SaveShow()
        saved=show.par.Output1maskpolygon.eval();show.par.Output1maskpolygon='[]';show.LoadShow()
        checks['save_load_points']=show.par.Output1maskpolygon==saved and bool(show.par.Output1maskenabled)
        doc=json.loads(path.read_text(encoding='utf-8'))
        for i in (1,2,3):doc['mapping'].pop('Output'+str(i)+'maskpolygon',None)
        old=path.with_name('polygon-mask-old-show.json');old.write_text(json.dumps(doc),encoding='utf-8')
        show.par.Showfile=str(old);show.LoadShow()
        checks['old_show_clears_polygon']=show.par.Output1maskpolygon=='[]'
        for button in ('new','close','undo','delete','apply','reload'):
            callback=editor.op('button_'+button+'/clicked')
            if callback is None:
                raise AssertionError('Missing callback '+button+'; editor children: '+str([(c.name,[d.name for d in c.children] if c.isCOMP else []) for c in editor.children]))
            calls=[];handler=runtime.action
            try:
                runtime.action=lambda owner,name:calls.append(name)
                callback.module.onOffToOn(None)
                checks['button_'+button]=calls==[button]
            finally:runtime.action=handler
        checks['mouse_event_wiring']=editor.op('canvas/pointer_events').par.panelvalue.eval()=='lselect u v'
        checks['editor_not_in_show_layout']=not editor.par.display
        checks['editor_overlay_compiles']=np.isfinite(pixels(editor.op('overlay'))).all()
        checks['cue_data_preserved']=original.ext.ShowControlExt.document==before
        checks['windows_closed']=not any(w is not None and w.isOpen for w in show.op('show_review_export').module._export_windows(show))
        checks['no_errors']=not show.errors(recurse=True) and not wall.errors(recurse=True)
        report['ok']=all(bool(v) for v in checks.values())
    except Exception:report['error']=traceback.format_exc()
    finally:host.destroy()
    report['checks']={key:bool(value) for key,value in checks.items()}
    if write_report:
        target=ROOT/'build/envoy-validation/projection-polygon.json'
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(json.dumps(report,indent=2),encoding='utf-8')
    return report


if __name__=='__main__':print(validate())
