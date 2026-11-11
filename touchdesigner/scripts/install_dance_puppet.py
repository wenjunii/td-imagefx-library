"""Additive migration for an idle existing ImageFX TOE; preserves show JSON.

Call install(project_root) from TouchDesigner's Python Textport. Saving is a
separate explicit step after validation. No camera, render job or cue is started.
"""
import importlib
import json
from pathlib import Path
import sys
import runpy


def install(project_root):
    root=Path(project_root)
    demo=op('/project1/imagefx_demo') or op('/imagefx_demo')
    if demo is None: raise ValueError('Open the main ImageFX TOE first')
    show=demo.op('show_control'); extension=show.ext.ShowControlExt
    if extension.engine.state!='stopped' or extension.tracks or extension.prepared or extension._look_edit:
        raise ValueError('Stop all cues and close look editing before installation')
    saved=show.op('show_data').text
    source=str(root/'src')
    if source not in sys.path: sys.path.insert(0,source)
    from tdimagefx import show as model
    importlib.reload(model)
    scope={}; exec((root/'touchdesigner/scripts/dance_puppet.py').read_text(encoding='utf-8'),scope)
    workflow=(root/'touchdesigner/scripts/workflow.py').read_text(encoding='utf-8')
    workflow_scope={}; exec(workflow,workflow_scope)
    layers=runpy.run_path(str(root/'touchdesigner/scripts/layer_composite.py'))
    composition_source=runpy.run_path(str(root/'touchdesigner/scripts/image_composition.py'))
    demos=[demo,show.op('deck_template')]
    for d in list(demos):
        comp=d.op('image_composition')
        if comp is not None: demos.extend([comp.op('a_effects'),comp.op('b_effects')])
    # Nested A/B branches need their deck-template ancestor enabled while DAT
    # modules compile. Restore every cooking flag after the additive migration.
    cooking=[(d,d.allowCooking) for d in demos]
    for d,_ in cooking: d.allowCooking=True
    try:
        for d in demos:
            scope['build'](d,root)
            layers['install_independent_sources'](d.op('layer_composite'))
            if d.op('image_composition') is not None:
                composition_source['install_layer_sources'](d.op('image_composition'))
            d.op('workflow').text=workflow
            order=workflow_scope['validate_order'](json.loads(d.op('workflow_order').text),d.fetch('imagefx_branch',False))
            workflow_scope['apply_order'](d,order)
            menu=d.par.Stageselection; selection=menu.eval()
            menu.menuNames=order; labels=dict(zip(workflow_scope['DEFAULT_ORDER'],workflow_scope['LABELS']))
            menu.menuLabels=[labels[n] for n in order]; menu.val=selection
    finally:
        for d,enabled in reversed(cooking): d.allowCooking=enabled
    show.op('ShowControlExt').text=(root/'touchdesigner/extensions/ShowControlExt.py').read_text(encoding='utf-8')
    # Source replacement can reinitialize the extension on the following frame.
    # Its public document remains byte-for-byte intact; no show file is loaded.
    nav={}; navpath=root/'touchdesigner/scripts/look_editor_controls.py'
    exec(compile(navpath.read_text(encoding='utf-8'),str(navpath),'exec'),nav)
    nav['install'](show,workflow_scope['DEFAULT_ORDER'],workflow_scope['LABELS'])
    if show.op('show_data').text!=saved: raise RuntimeError('Existing show data changed during installation')
    report={'installed':[d.path for d in demos],'existing_cues':len(json.loads(saved)['cues']),
            'show_preserved':True,'camera_started':False}
    (root/'build/dance-puppet/native-integration-install.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return report
