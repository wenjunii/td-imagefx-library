"""Native crop pixels, all value controls, preset sizes and reset dispatch."""
from pathlib import Path
from datetime import datetime, timezone
import json
import traceback
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
REPORT_PATH=ROOT/"build/envoy-validation/final-crop.json"


def validate(write_report=True):
    host=op('/project1').create(baseCOMP,'final_crop_qa')
    checks={}; controls={}
    report=dict(ok=False,generated_at=datetime.now(timezone.utc).isoformat())
    try:
        test=host.copy(op('/project1/imagefx_demo/final_crop'),name='test')
        code=host.create(textDAT,'fixture_code')
        code.text='layout(location=0) out vec4 fragColor; void main(){fragColor=TDOutputSwizzle(vec4(vUV.st,.3,.6));}'
        source=host.create(glslTOP,'source')
        source.par.pixeldat=source.relativePath(code)
        source.par.outputresolution='custom'
        source.par.resolutionw,source.par.resolutionh=160,90
        source.par.compilebehavior='stalluntildone'
        source.outputConnectors[0].connect(test.inputConnectors[0])
        output=test.op('out1_image')
        def reset(**values):
            for p in test.customPars:
                if not p.readOnly and not p.isPulse: p.val=p.default
            for k,v in values.items(): test.par[k]=v
        def pixels(node=output):
            node.cook(force=True)
            a=np.array(node.numpyArray(delayed=False),dtype=np.float32,copy=True)
            if not np.isfinite(a).all() or node.errors(): raise AssertionError('Invalid crop pixels')
            return a
        reset(); b=pixels(source)
        checks['neutral_exact']=np.array_equal(pixels(),b)
        for preset in test.par.Aspect.menuNames:
            reset(Aspect=preset)
            image=pixels(); g=test.op('crop_math').module.current(test)
            checks['preset_'+preset]=image.shape[:2]==g['size'][::-1]
        reset(Left=10,Right=20,Top=30,Bottom=10)
        checks['manual_pixel_crop']=bool(np.allclose(pixels(),b[9:63,16:128],atol=.005))
        reset(Aspect='1x1',Anchorx=0)
        checks['left_anchor']=bool(np.allclose(pixels(),b[:,:90],atol=.005))
        test.par.Anchorx=1
        checks['right_anchor']=bool(np.allclose(pixels(),b[:,70:],atol=.005))
        test.par.Outputmode='mask'
        masked=pixels()
        checks['mask_keeps_canvas']=masked.shape==b.shape and np.all(masked[:,:70]==0) and np.allclose(masked[:,70:],b[:,70:],atol=.005)
        test.par.Outputmode='fit'
        fitted=pixels()
        checks['fit_keeps_canvas']=fitted.shape==b.shape and np.all(fitted[:,:35]==0) and np.all(fitted[:,-35:]==0) and np.max(fitted[:,:,3])>.5
        test.par.Enabled=False
        checks['disabled_exact_bypass']=np.array_equal(pixels(),b)
        for p in test.customPars:
            if p.readOnly or p.isPulse: continue
            reset()
            if p.name in ('Anchorx','Anchory'): test.par.Aspect='1x1'
            if p.name=='Anchory': source.par.resolutionw,source.par.resolutionh=90,160
            if p.name in ('Ratiowidth','Ratioheight'): test.par.Aspect='custom'
            values=list(p.menuNames) if p.isMenu else [False,True] if p.isToggle else [p.min,p.default,p.max]
            accepted=[]
            for value in values:
                p.val=value; image=pixels()
                accepted.append(p.eval()==value and image.shape[0]>=1 and image.shape[1]>=1)
            controls[p.name]=dict(values=values,accepted=accepted)
            checks[p.name+'_all_values']=all(accepted)
            if p.isNumber and not p.isToggle:
                checks[p.name+'_range']=p.min<p.max and p.normMin<p.normMax and p.clampMin and p.clampMax
            source.par.resolutionw,source.par.resolutionh=160,90
        reset(Left=100,Right=100,Top=100,Bottom=100)
        image=pixels()
        checks['overlapping_trims_safe']=1<=image.shape[0]<=2 and 1<=image.shape[1]<=2 and 'limited' in test.par.Status.eval()
        callback=test.op('crop_callbacks')
        checks['active_button_dispatch']=bool(callback.par.active and callback.par.onpulse) and set(callback.par.pars.eval().split())=={'Reset','Preview'}
        callback.module.onPulse(test.par.Reset)
        checks['reset_handler']=all(p.eval()==p.default for p in test.customPars if not p.readOnly and not p.isPulse)
        checks['preview_target']=test.par.opviewer.eval()==output
        for w,h in ((1920,1080),(3840,2160)):
            source.par.resolutionw,source.par.resolutionh=w,h
            reset(Aspect='1x1'); image=pixels()
            checks[str(w)+'_crop_size']=image.shape[:2]==(h,h)
        checks['all_controls_covered']=set(controls)=={p.name for p in test.customPars if not p.readOnly and not p.isPulse}
        report.update(checks=checks,controls=controls,ok=all(bool(v) for v in checks.values()))
    except Exception: report['error']=traceback.format_exc()
    finally: host.destroy()
    report['checks']={k:bool(v) for k,v in checks.items()}
    if write_report:
        REPORT_PATH.parent.mkdir(parents=True,exist_ok=True)
        REPORT_PATH.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    return report


if __name__=='__main__': print(validate())
