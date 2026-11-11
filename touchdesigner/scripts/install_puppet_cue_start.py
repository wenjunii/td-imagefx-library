"""Upgrade the idle cue runtime; no saved look, media or camera is changed."""
import copy
import importlib
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]


def install(show=None):
    import td
    show=show or td.op('/project1/imagefx_demo/show_control')
    if show is None: raise RuntimeError('Open the main ImageFX TOE first')
    old=show.ext.ShowControlExt
    if old.engine.state!='stopped' or old.tracks or old.prepared or old._look_edit is not None:
        raise RuntimeError('Stop All and finish Look Editor before installing puppet cue restart')
    if show.fetch('imagefx_export_job',None,search=False): raise RuntimeError('Finish export first')
    before=copy.deepcopy(old.document)
    selected=int(show.par.Selectedcue)
    saved={p.name:(p.eval(),p.expr,p.bindExpr,p.mode) for p in show.customPars
           if not p.isPulse and not p.readOnly and p.name not in {'Audioenabled','Masterblackout'}}
    importlib.reload(old.model)
    show.op('ShowControlExt').text=(ROOT/'touchdesigner/extensions/ShowControlExt.py').read_text(encoding='utf-8')
    show.initializeExtensions()
    current=show.ext.ShowControlExt
    if current.document!=current.model.validate_show(before): raise RuntimeError('Saved cue preservation failed')
    show.op('show_review_export').text=(ROOT/'touchdesigner/scripts/show_review_export.py').read_text(encoding='utf-8')
    for name,(value,expression,binding,mode) in saved.items():
        p=show.par[name]
        if p.eval()!=value: p.val=value
        p.expr,p.bindExpr,p.mode=expression,binding,mode
    current.SelectCue(selected)
    current._save_document_dat()
    show.par.Masterblackout,show.par.Audioenabled=True,False
    current._status('Recorded puppets restart from their Motion In Point on every cue GO / Go Back.')
    return dict(ok=True,cues_preserved=len(before['cues']),toe_saved=False,camera_started=False)
