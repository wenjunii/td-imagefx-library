"""Upgrade export UI/runtime without replacing the show or effect workflows."""
import copy
from pathlib import Path
import runpy

ROOT = Path(__file__).resolve().parents[2]


def install(show=None):
    import td
    show = show or td.op('/project1/imagefx_demo/show_control')
    ext = show.ext.ShowControlExt
    if ext.engine.state != 'stopped' or ext.tracks or ext.prepared or ext._look_edit is not None:
        raise RuntimeError('Stop All and finish Look Editor before upgrading export controls')
    if show.fetch('imagefx_export_job', None, search=False):
        raise RuntimeError('Finish/cancel the existing export first')
    before = copy.deepcopy(ext.document)
    values = {p.name:p.eval() for p in show.customPars if not p.isPulse and not p.readOnly}
    runpy.run_path(str(ROOT/'touchdesigner/scripts/show_review_export.py'))['install'](show)
    if ext.document != before:
        raise RuntimeError('Cue preservation failed')
    changed = [name for name,value in values.items() if show.par[name].eval() != value]
    if changed:
        raise RuntimeError('Existing control preservation failed: ' + ', '.join(changed))
    return dict(ok=True, cues_preserved=len(before['cues']), controls_preserved=len(values),
                default_channel_mode=show.par.Exportchannels.eval(), toe_saved=False)
