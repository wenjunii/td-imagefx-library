"""Control inventory/range audit for the optional dance and puppet modules.

Uses disposable copies. Camera, analysis and viewer buttons are checked for
native callback routing, not activated; rendered behavior has real-frame tests.
"""
from datetime import datetime, timezone
from pathlib import Path
import json
import runpy
import traceback

ROOT = Path(__file__).resolve().parents[2]


def validate(write_report=True):
    demo = op('/project1/imagefx_demo')
    show = demo.op('show_control')
    assert show.ext.ShowControlExt.engine.state == 'stopped'
    before = show.op('show_data').text
    host = op('/project1').create(baseCOMP, 'motion_control_audit')
    page = host.appendCustomPage('Masters')
    for name in ('Inkdreamenabled', 'Inkbrushenabled', 'Inkradialenabled', 'Dancepuppetenabled'):
        page.appendToggle(name)[0].val = False
    force = runpy.run_path(str(ROOT / 'touchdesigner/scripts/dance_forces.py'))
    puppet = runpy.run_path(str(ROOT / 'touchdesigner/scripts/dance_puppet.py'))
    groups = [(n, force['PARAMETERS'], 'dance_forces_controls', 'dance_forces_runtime')
              for n in force['MODULES']]
    groups.append(('dance_puppet', puppet['PARAMETERS'], 'puppet_parameters', 'puppet_runtime'))
    checks, coverage, error = {}, {}, None
    try:
        for name, definitions, callback_name, runtime_name in groups:
            c = host.copy(demo.op(name), name=name)
            c.allowCooking = True
            callback, runtime = c.op(callback_name), c.op(runtime_name)
            prefix = name + '/'
            checks[prefix+'callback_active'] = bool(callback.par.active)
            checks[prefix+'callback_owner'] = callback.par.op.eval() == c
            checks[prefix+'callback_pulses'] = bool(callback.par.onpulse)
            checks[prefix+'callback_values'] = bool(callback.par.valuechange)
            checks[prefix+'callback_custom'] = bool(callback.par.custom)
            checks[prefix+'runtime_dispatch'] = runtime_name in callback.text
            declared = {d[1]+s for d in definitions for s in ('rgb' if d[2]=='rgb' else ('',))}
            installed = {p.name for p in c.customPars if name=='dance_puppet' or p.name.startswith('Dance')}
            checks[prefix+'complete_inventory'] = declared == installed
            coverage[name] = dict(controls=sorted(declared), wiring_only_buttons=[])
            for _, pname, kind, default, lo, hi, _ in definitions:
                pars = [c.par[pname+s] for s in ('rgb' if kind=='rgb' else ('',))]
                for p in pars:
                    key = prefix+p.name
                    checks[key+'/present'] = p is not None
                    if p is None:
                        continue
                    if p.readOnly:
                        checks[key+'/status_readonly'] = pname in {
                            'Time', 'Duration', 'Ready', 'Status', 'Buildstatus',
                            'Danceduration', 'Dancestatus'}
                        continue
                    if kind == 'pulse':
                        checks[key+'/dispatch_declared'] = repr(pname) in runtime.text
                        coverage[name]['wiring_only_buttons'].append(pname)
                        continue
                    original = (p.val, p.expr, p.mode)
                    try:
                        if kind in ('float', 'int', 'rgb'):
                            checks[key+'/range'] = (p.min,p.max,p.normMin,p.normMax)==(lo,hi,lo,hi)
                            checks[key+'/clamps'] = bool(p.clampMin and p.clampMax)
                            values = (lo, (lo+hi)/2 if kind!='int' else int((lo+hi)//2), hi)
                        elif kind=='menu':
                            checks[key+'/options'] = list(p.menuNames)==list(lo) and list(p.menuLabels)==list(hi)
                            values = lo
                        elif kind=='toggle':
                            values = (False, True)
                        elif kind=='file':
                            values = ('', 'build/qa-placeholder.mov')
                        else:
                            values = ('QA value',)
                        for index, value in enumerate(values):
                            p.val = value
                            checks[key+'/value/'+str(index)] = p.eval()==value
                    finally:
                        p.val,p.expr,p.mode = original
            c.destroy()
        checks['show_document_preserved'] = show.op('show_data').text == before
        checks['audience_windows_closed'] = not any(w.isOpen for w in
            show.op('show_output_mode').module.windows(show) if w)
    except Exception:
        error = traceback.format_exc()
    finally:
        host.destroy()
    report = dict(ok=error is None and all(checks.values()), checks=checks,
                  coverage=coverage, error=error, generated_at=datetime.now(timezone.utc).isoformat(),
                  camera_started=False, analysis_started=False)
    if write_report:
        path = ROOT/'build/envoy-validation/motion-controls.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    return report
