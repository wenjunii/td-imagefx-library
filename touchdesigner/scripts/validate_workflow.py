"""Reorder every stage in a disposable deck and check real graph/pixel behavior."""
from pathlib import Path
from datetime import datetime, timezone
import json
import traceback
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
REPORT_PATH=ROOT/'build/envoy-validation/workflow.json'


def fixture():
    host=op('/project1').create(baseCOMP,'workflow_qa')
    demo=host.copy(op('/project1/imagefx_demo'),name='test')
    show=demo.op('show_control')
    if show is not None: show.destroy()
    demo.par.Resolutionpreset='custom'; demo.par.Customwidth=160; demo.par.Customheight=90
    for p in demo.customPars:
        if p.isToggle: p.val=False
    for node in demo.children:
        if node.par['Autotime'] is not None: node.par.Autotime=False
    demo.op('source_image').par.vec0valuex=0
    return host,demo


def correct_graph(demo,order):
    previous=demo.op('source_image')
    for name in order:
        node=demo.op(name)
        # COMP input lists resolve the upstream COMP's Out TOP, not its COMP.
        actual=node.inputs[0]
        if actual!=previous and actual.parent()!=previous: return False
        if name=='fx_rack':
            router=demo.op('video_fx_router')
            if router.inputs[0]!=actual or router.inputs[1]!=node.op('out1_image'): return False
            previous=router
        else: previous=node
    return demo.op('out1_image').inputs[0].parent()==previous or demo.op('out1_image').inputs[0]==previous


def validate(write_report=True):
    host,demo=fixture(); checks={}
    report=dict(ok=False,generated_at=datetime.now(timezone.utc).isoformat())
    try:
        workflow=demo.op('workflow').module
        original=list(workflow.DEFAULT_ORDER)
        before=demo.op('fx_rack').ExportPreset()
        for name in original:
            for action in ('Stagefirst','Stagelast','Stageup','Stagedown','Resetorder'):
                demo.par.Stageselection=name
                demo.op('workflow_callbacks').module.onPulse(demo.par[action])
                order=workflow.current(demo)
                checks[name+'_'+action]=correct_graph(demo,order)
        checks['rack_settings_retained']=before==demo.op('fx_rack').ExportPreset()
        checks['no_duplicate_or_missing']=workflow.current(demo)==original
        try: workflow.apply_order(demo,original[:-1])
        except ValueError: checks['invalid_order_rejected_before_rewire']=correct_graph(demo,original)
        checks['callbacks_active']=bool(demo.op('workflow_callbacks').par.active and demo.op('workflow_callbacks').par.onpulse)
        demo.par.Coloradjustmentenabled=True; demo.par.Layercompositeenabled=True
        demo.op('color_adjustment').par.Invert=1
        layer=demo.op('layer_composite')
        layer.par.Backdropsource='transparent'; layer.par.Topsource='effects'
        layer.par.Tintg=.25; layer.par.Topfit='stretch'
        def pixels():
            node=demo.op('out1_image'); node.cook(force=True)
            return np.array(node.numpyArray(delayed=False),copy=True)
        a=pixels()
        workflow.apply_order(demo,workflow.moved_order(original,'layer_composite','Stagefirst'))
        b=pixels()
        checks['order_changes_real_pixels']=a.shape==b.shape and float(np.mean(np.abs(a-b)))>.05
        checks['effects_result_tracks_new_upstream']=layer.inputs[0]==demo.op('source_image')
        demo.par.Applyvideofx=True
        workflow.apply_order(demo,list(reversed(original)))
        checks['reverse_order_with_rack']=correct_graph(demo,list(reversed(original))) and np.isfinite(pixels()).all()
        checks['no_output_errors']=not demo.op('out1_image').errors(recurse=True)
        report['ok']=all(bool(v) for v in checks.values())
    except Exception: report['error']=traceback.format_exc()
    finally: host.destroy()
    report['checks']={k:bool(v) for k,v in checks.items()}
    if write_report:
        REPORT_PATH.parent.mkdir(parents=True,exist_ok=True)
        REPORT_PATH.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    return report


def validate_deferred():
    """Exercise actual TD pulse delivery rather than directly calling handlers."""
    host,demo=fixture(); checks={}; workflow=demo.op('workflow').module
    report=dict(ok=False,generated_at=datetime.now(timezone.utc).isoformat())
    def steps():
        demo.par.Stageselection='layer_composite'
        for name,index in (('Stagefirst',0),('Stagedown',1),('Stagelast',13),('Stageup',12),('Resetorder',12)):
            demo.par[name].pulse()
            yield; yield
            checks[name]=workflow.current(demo).index('layer_composite')==index and correct_graph(demo,workflow.current(demo))
        crop=demo.op('final_crop'); crop.par.Left=24; crop.par.Aspect='1x1'
        crop.par.Reset.pulse()
        yield; yield
        checks['crop_reset_pulse']=crop.par.Left.eval()==0 and crop.par.Aspect.eval()=='free'
    sequence=steps()
    def advance():
        try: next(sequence)
        except StopIteration: finish()
        except Exception:
            report['error']=traceback.format_exc(); finish()
        else: run('args[0]()',advance,delayFrames=1)
    def finish():
        report.update(checks=checks,ok=bool(checks) and all(checks.values()) and 'error' not in report)
        REPORT_PATH.with_name('workflow-deferred.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        host.destroy(); print('Workflow button QA:',report)
    run('args[0]()',advance,delayFrames=1)


if __name__=='__main__': print(validate())
