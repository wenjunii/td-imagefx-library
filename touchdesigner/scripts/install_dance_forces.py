"""Add Dance Forces to an idle main TOE without rebuilding user looks/cues."""
import importlib
import json
from datetime import datetime
from pathlib import Path
import runpy
import sys


def install(project_root, report_dir=None):
    root = Path(project_root)
    demo = op('/project1/imagefx_demo')
    if demo is None: raise ValueError('Open the main ImageFX TOE first')
    show = demo.op('show_control'); ext = show.ext.ShowControlExt
    if ext.engine.state!='stopped' or ext.tracks or ext.prepared or ext._look_edit:
        raise ValueError('Stop cues and close look editing before installation')
    saved = show.op('show_data').text
    folder = Path(report_dir) if report_dir is not None else root/'build/dance-forces'/('install-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    folder.mkdir(parents=True,exist_ok=True)
    snapshot = folder/'native-before.json'
    if not snapshot.exists():
        snapshot.write_text(json.dumps(dict(show=saved,cues=len(ext.document['cues']),
            main_look=ext._capture_look(demo),gpu=sysinfo.GPUName),indent=2),encoding='utf-8')
    build = runpy.run_path(str(root/'touchdesigner/scripts/dance_forces.py'))
    puppet = runpy.run_path(str(root/'touchdesigner/scripts/dance_puppet.py'))
    demos = [demo,show.op('deck_template')]
    for d in list(demos):
        comp = d.op('image_composition')
        if comp is not None: demos += [comp.op('a_effects'),comp.op('b_effects')]
    cooking = [(d,d.allowCooking) for d in demos]
    for d,_ in cooking: d.allowCooking=True
    installed=[]
    try:
        for d in demos:
            puppet['install_fade'](d.op('dance_puppet'),root)
            for name in build['MODULES']:
                c = d.op(name)
                source = c.op('flow_feedback_source')
                # Idempotent: the first input becomes a switch after migration.
                raw = c.op('dance_forces_switch').inputs[0] if c.op('dance_forces_switch') else source.inputs[0]
                build['install'](c,raw,root)
                installed.append(c.path)
    finally:
        for d,enabled in reversed(cooking): d.allowCooking=enabled
    source=str(root/'src')
    if source not in sys.path: sys.path.insert(0,source)
    from tdimagefx import show as model
    importlib.reload(model)
    show.op('ShowControlExt').text=(root/'touchdesigner/extensions/ShowControlExt.py').read_text(encoding='utf-8')
    if show.op('show_data').text!=saved: raise RuntimeError('Show data changed during migration')
    report=dict(installed=installed,show_preserved=True,camera_started=False,default_enabled=False)
    (folder/'native-install.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return report
