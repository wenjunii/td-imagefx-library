"""Native Dance Puppet cue/control regression on a disposable Show Control.

No audience windows, audio devices, cameras, or analysis jobs are started.
Run this source as a Text DAT then call start(project_root).
"""
import copy
import json
from pathlib import Path
import traceback
import numpy as np

RUN={}


def start(root):
    if RUN: raise ValueError('Puppet validation already running')
    RUN['root']=Path(root)
    RUN['generator']=validate()
    advance()


def advance():
    try:
        next(RUN['generator'])
        run("op({!r}).module.advance()".format(me.path),delayFrames=2)
    except StopIteration: RUN.clear()
    except Exception:
        RUN.clear()
        raise


def validate():
    root=RUN['root']; folder=root/'build/dance-puppet'
    original=op('/project1/imagefx_demo/show_control')
    assert original.ext.ShowControlExt.engine.state=='stopped'
    assert original.ext.ShowControlExt._look_edit is None
    original_text=original.op('show_data').text
    session_path=root/'.imagefx/puppet-live.json'
    camera_session=session_path.read_bytes() if session_path.exists() else None
    assert original.parent().op('puppet_cue_qa') is None
    qa=original.parent().copy(original,name='puppet_cue_qa')
    qa.op('show_tick').par.active=False
    qa.initializeExtensions()
    ext=qa.ext.ShowControlExt
    checks={}; debug={}; error=None; clock=[0.]

    def check(name,value):
        checks[name]=bool(value)
        assert value,name

    def pixels(top):
        top.cook(force=True)
        a=top.numpyArray(delayed=False)
        assert a is not None and np.isfinite(a).all(),top.path
        assert not top.errors(),top.errors()
        return a.copy()

    def tick(dt=0):
        clock[0]+=dt; ext.Tick(); ext.UpdateMapping()
        assert not ext.engine.errors,str(ext.engine.errors)

    def until(test):
        for _ in range(900):
            tick(); yield
            if test(): return
        raise AssertionError('Puppet cue preparation timed out')

    try:
        yield
        qa.par.Renderwidth,qa.par.Renderheight=640,360
        qa.par.Masterblackout=False; qa.par.Audioenabled=False; qa.par.Testpattern=False
        qa.par.Routingmode='independent'
        for i in (1,2,3):
            qa.par['Output%dwidth'%i]=640; qa.par['Output%dheight'%i]=360
            qa.par['Output%dtrack'%i]=i; qa.par['Output%dblackout'%i]=False
        files={
            'Renderfile':str(folder/'integration-default/puppet-alpha.mov'),
            'Fanrenderfile':'','Chainrenderfile':'',
            'Motioncache':str(folder/'motion-rtm-full.json'),
            'Characterprofile':str(folder/'characters-default.json'),
            'Dancevideo':''}
        cue=dict(ext.model.new_cue(),name='Puppet QA',duration=0,fade=0,track=1,
                 look={'toggles':{'Dancepuppetenabled':True},
                       'modules':{'dance_puppet':{'Sourcemode':'recorded','Composite':False,'Transparent':True,
                                                'Monochrome':True,'Loop':False,'Zoom':1.,'Opacity':1.,'Fadein':0.}},
                       'puppet_files':files,'animation':{'dance_puppet':{'time':0.,'running':True}}})
        ext._replace_cues([cue]); ext.engine.clock=lambda:clock[0]; ext.engine._last=clock[0]
        ext.engine.go(0)
        yield from until(lambda:cue['id'] in ext.engine.active)
        deck=ext.tracks[1]['deck']; puppet=deck.op('dance_puppet'); output=puppet.op('puppet_rgba')
        check('native_reader_open_before_go',puppet.op('recorded_motion').isOpen)
        check('prepared_file_restored',puppet.par.Renderfile.eval()==files['Renderfile'])
        check('cue_clock_starts_at_zero',abs(float(puppet.par.Time))<.01)
        initial=pixels(output)
        check('real_transparent_background',initial[:,:,3].min()<.001 and initial[:,:,3].max()>.99)
        opaque=initial[:,:,3]>.99
        check('black_body_and_white_linework',np.min(initial[:,:,:3][opaque])<.02 and np.max(initial[:,:,:3][opaque])>.7)
        check('projection_has_puppet',pixels(qa.op('mapped1'))[:,:,:3].max()>.5)
        check('other_projectors_remain_black',pixels(qa.op('mapped2'))[:,:,:3].max()<.01 and pixels(qa.op('mapped3'))[:,:,:3].max()<.01)
        tick(1.); yield
        moved=pixels(output)
        check('motion_advances_with_cue',not np.allclose(initial,moved))
        ext.Pause(); hold=pixels(output); saved_time=float(puppet.par.Time)
        yield; tick(1.); yield
        check('pause_freezes_puppet',float(puppet.par.Time)==saved_time and np.allclose(hold,pixels(output)))
        ext.Resume(); tick(.5); yield
        check('resume_advances_puppet',float(puppet.par.Time)>saved_time and not np.allclose(hold,pixels(output)))
        # The QA engine clock is manual; keep cooking enabled while testing
        # controls at a fixed playhead (transport Pause deliberately locks it).
        ext.Resume()
        puppet.par.Fadein=1.
        puppet.op('puppet_runtime').module.reset_fade(puppet)
        yield
        check('fade_starts_transparent',pixels(output)[:,:,3].max()<.001)
        tick(.5); yield
        check('fade_halfway_alpha',abs(float(pixels(output)[:,:,3].max())-.5)<.015)
        ext.Pause(); fade_hold=pixels(output); tick(.5); yield
        check('fade_pause_holds_pixels',np.array_equal(fade_hold,pixels(output)))
        ext.Resume(); tick(.5); yield
        check('fade_resume_finishes',pixels(output)[:,:,3].max()>.99)
        puppet.par.Fadein=0.; yield
        check('zero_fade_keeps_full_alpha',pixels(output)[:,:,3].max()>.99)
        for name,value in [('Opacity',.35),('Zoom',1.4),('Panx',.2),('Pany',.2),('Mirror',True),
                           ('Framing','cropped'),('Monochrome',False),('Bodycolorr',.7),('Linecolorg',.1),
                           ('Transparent',False),('Composite',True),('Offset',2.)]:
            before=pixels(puppet.op('out1_image')); old=puppet.par[name].eval()
            puppet.par[name]=value; yield
            changed=pixels(puppet.op('out1_image'))
            check('control_pixels/'+name,not np.allclose(before,changed))
            puppet.par[name]=old; yield
        # Background tint is relevant only with an opaque background.
        puppet.par.Transparent=False; yield
        before=pixels(output); puppet.par.Backgroundg=.4; yield
        check('background_color_pixels',not np.allclose(before,pixels(output)))
        puppet.par.Backgroundg=0.; puppet.par.Transparent=True
        puppet.par.Enabled=False; yield
        check('module_switch_updates_master',not deck.par.Dancepuppetenabled)
        check('disabled_is_upstream_bypass',np.allclose(pixels(puppet.op('out1_image')),pixels(puppet.op('in1_image'))))
        deck.par.Dancepuppetenabled=True; yield
        check('master_switch_updates_module',bool(puppet.par.Enabled))
        ext.SelectCue(1); before_document=copy.deepcopy(ext.document)
        ext.EditRunningLook(); puppet.par.Zoom=1.3; yield
        check('running_edit_is_visible',float(puppet.par.Zoom)==1.3 and ext.document==before_document)
        ext.CancelLook(); yield
        check('discard_restores_zoom_and_file',float(puppet.par.Zoom)==1 and puppet.par.Renderfile.eval()==files['Renderfile'])
        ext.EditRunningLook(); puppet.par.Zoom=1.2; puppet.par.Feedbackenabled=True
        puppet.par.Trailamount=.45; puppet.par.Trailhalf=.25; puppet.par.Trailsoftness=1.5
        yield
        ext.UpdateLook(); yield
        check('update_saves_puppet_controls',ext.document['cues'][0]['look']['modules']['dance_puppet']['Zoom']==1.2)
        check('update_keeps_recorded_files',ext.document['cues'][0]['look']['puppet_files']==files)
        ext.Resume(); tick(.1); yield
        check('feedback_has_no_operator_errors',not puppet.errors(recurse=True))
        puppet.par.Clearhistory.pulse(); yield
        check('clear_history_pulse',not puppet.errors(recurse=True))
        ext.engine.stop(); ext.SelectCue(1); ext.RecallLook(); yield
        editor=ext._look_edit['deck'].op('dance_puppet')
        check('recall_restores_puppet_controls',float(editor.par.Zoom)==1.2 and bool(editor.par.Feedbackenabled))
        check('recall_restores_recorded_files',editor.par.Renderfile.eval()==files['Renderfile'])
        editor.par.Restartmotion.pulse(); yield
        check('reset_preview_opening_pose',not editor.par.Autotime and float(editor.par.Manualtime)==0)
        ext.CancelLook()
        qa.par.Showfile=str(folder/'puppet-cue-qa.show.json'); ext.SaveShow()
        document=json.loads((folder/'puppet-cue-qa.show.json').read_text(encoding='utf-8'))
        check('show_file_contains_puppet_look',document['cues'][0]['look']['puppet_files']['Renderfile']==files['Renderfile'])
        ext.LoadShow()
        check('show_file_reload_retains_puppet_look',ext.document['cues'][0]['look']==document['cues'][0]['look'])
        check('no_camera_started',(session_path.read_bytes() if session_path.exists() else None)==camera_session)
        check('original_cues_preserved',original.op('show_data').text==original_text)
        check('native_operator_errors_empty',not qa.errors(recurse=True))
        check('no_output_windows_opened',not any(w.isOpen for w in qa.op('show_output_mode').module.windows(qa) if w))
    except Exception:
        error=traceback.format_exc(); debug['status']=qa.par.Status.eval()
        debug['operator_errors']=qa.errors(recurse=True)
    finally:
        ext.engine.stop()
        if ext._look_edit is not None: ext.CancelLook()
        qa.destroy()
    result=dict(ok=error is None,checks=checks,error=error,debug=debug)
    (folder/'native-puppet-cue-validation.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print('PUPPET CUE QA:',len(checks),'checks;', 'PASS' if error is None else error)
    return result
