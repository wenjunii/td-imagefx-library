"""Add branch effect status/explicit-enable UI without editing artist values."""
import copy
from pathlib import Path
import runpy

ROOT=Path(__file__).resolve().parents[2]


def install():
    import td
    demo=td.op('/project1/imagefx_demo')
    if demo is None: raise RuntimeError('Open the main ImageFX TOE first')
    show=demo.op('show_control');ext=show.ext.ShowControlExt
    if ext.engine.state!='stopped' or ext.tracks or ext.prepared or ext._look_edit is not None:
        raise RuntimeError('Stop All and finish Look Editor before installing branch controls')
    before=copy.deepcopy(ext.document)
    roots=[demo]+[child for child in show.children if child.op('workflow') is not None and child.op('layer_composite') is not None]
    workflows=list(roots)
    for root in roots:
        comp=root.op('image_composition')
        if comp is not None: workflows.extend([comp.op('a_effects'),comp.op('b_effects')])
    workflows=[d for d in workflows if d is not None]
    def values(layer):
        return {p.name:p.eval() for p in layer.customPars if not p.readOnly and not p.isPulse and p.name!='Manualtime'}
    layers=[d.op('layer_composite') for d in workflows]
    saved=[values(layer) for layer in layers]
    cooking=[(d,d.allowCooking) for d in workflows]
    patch=runpy.run_path(str(ROOT/'touchdesigner/scripts/layer_composite.py'))['install_independent_sources']
    try:
        for d,_ in cooking: d.allowCooking=True
        for layer in layers: patch(layer)
        for layer,old in zip(layers,saved):
            current=values(layer)
            if any(current[name]!=value for name,value in old.items()):
                raise RuntimeError('Existing layer control changed: '+layer.path)
        if ext.document!=before: raise RuntimeError('Cue document changed during UI installation')
    finally:
        for d,enabled in reversed(cooking): d.allowCooking=enabled
    return dict(ok=True,workflows_upgraded=len(workflows),cue_count=len(before['cues']),
                cue_values_preserved=True,artist_values_preserved=True,toe_saved=False)
