import json
from pathlib import Path
import traceback
import numpy as np
def start(root):
    global generator, ROOT, FOLDER
    ROOT=Path(root)
    FOLDER=ROOT/'build/dance-forces/advection-20261027'
    FOLDER.mkdir(parents=True,exist_ok=True)
    generator=validate(); advance()
def advance():
    try:
        next(generator)
        run("op({!r}).module.advance()".format(me.path),delayFrames=2)
    except StopIteration: pass
def validate():
    show=op('/project1/imagefx_demo/show_control'); ext=show.ext.ShowControlExt
    original=show.op('show_data').text
    host=op('/project1').create(baseCOMP,'dance_cue_qa')
    checks={}; errors=[]
    def check(name,value):
        checks[name]=bool(value)
        assert value,name
    def field(c):
        node=c.op('dance_motion_out'); node.cook(force=True)
        return node.numpyArray(delayed=False).copy()
    try:
        deck=host.copy(show.op('deck_template'),name='cue')
        deck.allowCooking=True; deck.op('fx_rack').initializeExtensions()
        look=ext._capture_look(op('/project1/imagefx_demo'),active=False,capture_animation=True)
        look['toggles']['Inkdreamenabled']=True
        look['modules']['ink_dream_flow'].update(Danceenabled=True,Dancefadein=0.,Danceacceleration=2.2,Dancepush=.7,Danceoffset=12.)
        look['force_files']['ink_dream_flow']={'Dancecache':str(ROOT/'.imagefx/dance-forces-jobs/main-edit-20261027/motion.json'),'Dancevideo':''}
        ext._apply_look(deck,look); yield
        c=deck.op('ink_dream_flow'); runtime=c.op('dance_forces_runtime').module
        check('recall/speed_response',float(c.par.Danceacceleration)==2.2)
        check('recall/direction',float(c.par.Dancepush)==.7)
        check('recall/zero_material',np.abs(field(c)).max()==0.)
        check('recall/inpoint',abs(runtime.motion_time(c)-12.)<1e-6)
        for i in range(20):
            c.par.Manualtime=float(c.par.Manualtime)+1/30
            yield
            field(c)
        check('play/motion_history',np.abs(field(c)).max()>1e-5)
        saved=ext._capture_look(deck,active=False,capture_animation=True)
        check('capture/speed_response',saved['modules']['ink_dream_flow']['Danceacceleration']==2.2)
        c.par.Danceacceleration=.2; yield
        held=field(c); phase=runtime.motion_time(c)
        ext._restore_running_values(deck,saved); yield
        check('live_edit/discard_values',float(c.par.Danceacceleration)==2.2)
        check('live_edit/no_clock_jump',abs(runtime.motion_time(c)-phase)<1e-6)
        check('live_edit/no_history_reset',np.array_equal(held,field(c)))
        ext._apply_look(deck,look); yield
        check('retrigger/zero_material',np.abs(field(c)).max()==0.)
        check('retrigger/inpoint',abs(runtime.motion_time(c)-12.)<1e-6)
        check('main/cues_unchanged',show.op('show_data').text==original)
        check('native/no_errors',not deck.errors(recurse=True))
    except Exception: errors.append(traceback.format_exc())
    finally:
        host.destroy()
        (FOLDER/'cue-validation.json').write_text(json.dumps(dict(ok=not errors,checks=checks,errors=errors),indent=2),encoding='utf-8')
        print('Cue material checks:',not errors,len(checks),errors)
