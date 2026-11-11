"""Update idle Show Control's file budget without changing cue looks or media."""
import copy
import importlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def install(show=None):
    import td
    show = show or td.op('/project1/imagefx_demo/show_control')
    if show is None:
        raise RuntimeError('Open the main ImageFX TOE first')
    old = show.ext.ShowControlExt
    if old.engine.state != 'stopped' or old.tracks or old.prepared or old._look_edit is not None:
        raise RuntimeError('Stop All and finish Look Editor before updating show-file support')
    if show.fetch('imagefx_export_job', None, search=False):
        raise RuntimeError('Finish export first')
    before = copy.deepcopy(old.document)
    selected = int(show.par.Selectedcue)
    saved = {p.name: (p.eval(), p.expr, p.bindExpr, p.mode) for p in show.customPars
             if not p.isPulse and not p.readOnly and p.name not in {'Audioenabled', 'Masterblackout'}}
    importlib.reload(old.model)
    show.op('ShowControlExt').text = (ROOT / 'touchdesigner/extensions/ShowControlExt.py').read_text(encoding='utf-8')
    show.initializeExtensions()
    current = show.ext.ShowControlExt
    if current.document != current.model.validate_show(before):
        raise RuntimeError('Saved cue preservation failed')
    for name, (value, expression, binding, mode) in saved.items():
        p = show.par[name]
        if p.eval() != value:
            p.val = value
        p.expr, p.bindExpr, p.mode = expression, binding, mode
    current.SelectCue(selected)
    current._save_document_dat()
    show.par.Masterblackout, show.par.Audioenabled = True, False
    current._status('Show files now support up to 64 MiB; cue validation and automatic backups remain enabled.')
    return dict(ok=True, cues_preserved=len(before['cues']), max_show_bytes=current.model.MAX_SHOW_BYTES,
                toe_saved=False, camera_started=False)
