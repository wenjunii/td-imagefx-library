"""Off-air pixel, persistence and control tests for per-projector mapping."""
import copy
import json
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[2]


def validate(write_report=True):
    original=op('/project1/imagefx_demo/show_control')
    original_doc=copy.deepcopy(original.ext.ShowControlExt.document)
    host=op('/project1').create(baseCOMP,'projection_mapping_qa')
    wall=host.copy(original.parent().op('wall_output'),name='wall_output')
    show=host.copy(original,name='show_control')
    show.op('show_tick').par.active=False
    ext=show.ext.ShowControlExt
    runtime=show.op('projection_mapping').module
    checks={}
    report=dict(ok=False,generated_at=datetime.now(timezone.utc).isoformat(),hardware_outputs_tested=False)
    try:
        pattern=host.create(glslTOP,'pattern')
        code=host.create(textDAT,'pattern_shader')
        code.text='layout(location=0) out vec4 fragColor;void main(){fragColor=TDOutputSwizzle(vec4(vUV.x,vUV.y,.3,1));}'
        pattern.par.pixeldat='pattern_shader';pattern.par.outputresolution='custom'
        pattern.par.resolutionw,pattern.par.resolutionh=320,180
        show.par.Masterblackout=False;show.par.Routingmode='independent'
        for i in (1,2,3):
            show.par['Output{}width'.format(i)]=320;show.par['Output{}height'.format(i)]=180
            show.op('output_source'+str(i)).par.top=pattern.path
            wall.par['Projector{}top'.format(i)]=pattern.path
        wall.par.Sourcemode='independent';wall.par.Fit='stretch'
        wall.par.Blackout=False;wall.par.Enabled=True;wall.par.Testpattern=False
        def pixels(node):
            ext.UpdateMapping();node.cook(force=True)
            a=np.array(node.numpyArray(delayed=False),copy=True)
            if not np.isfinite(a).all() or node.errors():raise AssertionError(node.path+' invalid pixels: '+node.errors())
            return a
        def direct(i=1):return pixels(show.op('mapped'+str(i)))
        def reset(i):
            show.par.Mappingprojector=str(i);runtime.reset_selected(show)
        baseline=direct()
        checks['neutral_output']=np.max(np.abs(baseline[:,:,:3]-pixels(pattern)[:,:,:3]))<.005
        for i in (1,2,3):
            prefix='Output'+str(i)
            show.par[prefix+'maskenabled']=True
            show.par[prefix+'maskwidth']=.65;show.par[prefix+'maskheight']=.45
            show.par[prefix+'maskfeather']=.03
            a=direct(i)
            checks['mask_on_'+str(i)]=np.max(a[0,:,:3])==0 and np.max(a[90,160,:3])>.1
            checks['independent_'+str(i)]=all(np.allclose(direct(j),baseline) for j in (1,2,3) if j!=i)
            sweeps={'maskx':.35,'masky':.35,'maskwidth':.4,'maskheight':.7,'maskrotate':32,
                    'maskfeather':.12,'maskopacity':.3,'maskinvert':True,'maskshape':'ellipse'}
            for suffix,value in sweeps.items():
                par=show.par[prefix+suffix];old=par.eval();par.val=value
                checks['pixels_'+prefix+suffix]=bool(np.max(np.abs(direct(i)-a))>.002)
                par.val=old
            editor=show.op('projection'+str(i))
            for par in editor.customPars:
                if par.isPulse:continue
                master=show.par[prefix+par.name.lower()]
                checks['binding_'+prefix+par.name]=par.bindMaster==master and par.eval()==master.eval()
            for suffix in runtime.MASK_SUFFIXES:
                par=show.par[prefix+suffix]
                if par.isNumber and not par.isMenu and not par.isToggle:
                    old=par.eval()
                    for endpoint in (par.min,par.max):
                        par.val=endpoint
                        checks['finite_'+prefix+suffix+'_'+str(endpoint)]=bool(np.isfinite(direct(i)).all())
                    par.val=old
            show.par[prefix+'maskenabled']=False
            checks['mask_off_exact_'+str(i)]=np.array_equal(direct(i),baseline)
            show.par[prefix+'edgeall']=.3
            edge=direct(i)
            checks['soft_edges_'+str(i)]=np.max(np.abs(edge-baseline))>.01
            show.par[prefix+'edgegamma']=2
            checks['edge_curve_'+str(i)]=np.max(np.abs(direct(i)-edge))>.01
            # Editing either surface writes to the same calibration values.
            editor.par.Edgeall=.2
            checks['editor_to_show_'+str(i)]=show.par[prefix+'edgeall']==.2
            show.par[prefix+'edgeall']=.1
            checks['show_to_editor_'+str(i)]=editor.par.Edgeall==.1
            reset(i)
        # Image-mask luminance and alpha are deliberately different.
        code.text='layout(location=0) out vec4 fragColor;void main(){fragColor=TDOutputSwizzle(vec4(step(.5,vUV.x),step(.5,vUV.x),step(.5,vUV.x),step(.5,vUV.y)));}'
        fixture=ROOT/'build/envoy-validation/projection-mask-fixture.png'
        fixture.parent.mkdir(parents=True,exist_ok=True)
        pattern.cook(force=True);pattern.save(str(fixture))
        show.par.Output1maskenabled=True;show.par.Output1maskshape='image'
        show.par.Output1maskfile=str(fixture);show.par.Output1maskfeather=0
        reader=show.op('projection_mask_file1');reader.preload()
        deadline=time.monotonic()+5
        while not runtime.mask_ready(show,1) and time.monotonic()<deadline:time.sleep(.02)
        checks['image_ready']=runtime.mask_ready(show,1)
        # Return source to white so the output exactly exposes the mask.
        code.text='layout(location=0) out vec4 fragColor;void main(){fragColor=TDOutputSwizzle(vec4(1));}'
        luma=direct();show.par.Output1maskchannel='alpha';alpha=direct()
        checks['mask_luma_vs_alpha']=np.max(np.abs(luma-alpha))>.1
        show.par.Output1maskfeather=.04
        soft=direct()
        checks['image_mask_softness']=np.max(np.abs(soft-alpha))>.01
        show.par.Output1maskfile='missing-mask.png';show.par.Output1maskinvert=True
        checks['missing_mask_closed_even_inverted']=np.max(direct()[:,:,:3])==0
        checks['missing_mask_visible_status']='MASK UNAVAILABLE' in runtime.status(show,1)
        reset(1);show.par.Output1maskenabled=True;show.par.Output1maskshape='ellipse'
        show.par.Output1maskwidth=.7;show.par.Output1maskheight=.8;show.par.Output1maskopacity=.4
        show.par.Output1width=1920;show.par.Output1height=1080
        expected=direct()
        checks['wall_independent_same_mapping']=np.max(np.abs(expected-pixels(wall.op('p1_out'))))<.01
        wall.par.Sourcemode='show'
        checks['wall_show_not_double_masked']=np.max(np.abs(expected-pixels(wall.op('p1_out'))))<.01
        wall.par.Testpattern=True
        calibration=pixels(wall.op('p1_out'))
        checks['wall_calibration_respects_mask']=np.max(calibration[0,:,:3])==0 and np.max(calibration[540,960,:3])>.05
        wall.par.Testpattern=False
        checks['confidence_not_masked']=np.max(pixels(wall.op('comp_monitor_out'))[:720,:,:3])>.5
        for mode in ('identical','panoramic','independent'):
            wall.par.Sourcemode=mode;wall.par.Mastertop=pattern.path
            checks['wall_mode_'+mode]=np.max(np.abs(expected-pixels(wall.op('p1_out'))))<.01
        reset(1);show.par.Output1blx=.15
        valid=direct();wall_valid=pixels(wall.op('p1_out'))
        show.par.Output1cropleft=1
        checks['invalid_geometry_retained_direct']=np.array_equal(direct(),valid)
        checks['invalid_geometry_retained_wall']=np.array_equal(pixels(wall.op('p1_out')),wall_valid)
        checks['invalid_geometry_status']='positive' in show.par.Mappingstatus.eval()
        reset(1)
        # A temporary show file only: never save over the operator's show.
        show.par.Showfile=str(ROOT/'build/envoy-validation/projection-mapping-show.json')
        show.par.Output2maskenabled=True;show.par.Output2maskfile=str(fixture)
        show.par.Output2edgeall=.13
        ext.SaveShow();saved=copy.deepcopy(ext.document)
        show.par.Output2maskenabled=False;show.par.Output2maskfile='';show.par.Output2edgeall=0
        ext.LoadShow()
        checks['save_load_mapping']=bool(show.par.Output2maskenabled) and show.par.Output2maskfile==str(fixture) and show.par.Output2edgeall==.13
        older=copy.deepcopy(saved)
        for key in list(older['mapping']):
            if any(key=='Output'+str(i)+s for i in (1,2,3) for s in runtime.MASK_SUFFIXES):del older['mapping'][key]
        old_path=ROOT/'build/envoy-validation/projection-mapping-old-show.json'
        old_path.write_text(json.dumps(older),encoding='utf-8')
        show.par.Showfile=str(old_path);ext.LoadShow()
        checks['old_show_resets_new_masks']=all(not show.par['Output'+str(i)+'maskenabled'] and show.par['Output'+str(i)+'edgeall']==0 for i in (1,2,3))
        checks['cue_data_preserved']=ext.document['cues']==saved['cues'] and original.ext.ShowControlExt.document==original_doc
        # Installation is safe on an existing show, including edited calibration.
        show.par.Output2maskenabled=True;show.par.Output2maskshape='ellipse'
        show.par.Output2maskwidth=.47;show.par.Output2edgeall=.12
        before={p.name:p.eval() for p in show.customPars if not p.readOnly and not p.isPulse}
        document=copy.deepcopy(ext.document)
        count=len(show.customPars)
        editor_count=len(show.op('polygon_editor').children)
        source=ROOT/'touchdesigner/scripts/build_show_control.py'
        scope=dict(globals(),__file__=str(source),__name__='_mapping_reinstall_shader')
        exec(compile(source.read_text(encoding='utf-8'),str(source),'exec'),scope)
        source=ROOT/'touchdesigner/scripts/projection_mapping.py'
        installer=dict(globals(),__file__=str(source),__name__='_mapping_reinstall')
        exec(compile(source.read_text(encoding='utf-8'),str(source),'exec'),installer)
        installer['install'](show,scope['MAPPING_SHADER'])
        checks['reinstall_preserves_values']=all(show.par[name].eval()==value for name,value in before.items())
        checks['reinstall_no_duplicate_controls']=len(show.customPars)==count
        checks['reinstall_no_duplicate_polygon_widgets']=len(show.op('polygon_editor').children)==editor_count
        checks['reinstall_preserves_cues']=ext.document==document
        checks['reinstall_keeps_two_way_bindings']=show.op('projection2').par.Maskwidth.bindMaster==show.par.Output2maskwidth
        checks['visible_mapping_tab']="'Projection Mapping'" in show.op('cue_inspector').par.pagescope.eval()
        checks['no_audience_windows_open']=not any(w is not None and w.isOpen for w in show.op('show_review_export').module._export_windows(show))
        checks['no_errors']=not show.errors(recurse=True) and not wall.errors(recurse=True)
        report['ok']=all(bool(v) for v in checks.values())
    except Exception:report['error']=traceback.format_exc()
    finally:host.destroy()
    report['checks']={k:bool(v) for k,v in checks.items()}
    if write_report:
        (ROOT/'build/envoy-validation/projection-mapping.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return report


def validate_resets(write_report=True):
    """Exercise every reset and complete show-file calibration persistence off-air."""
    original=op('/project1/imagefx_demo/show_control')
    original_doc=copy.deepcopy(original.ext.ShowControlExt.document)
    original_values={p.name:p.eval() for p in original.customPars if not p.isPulse}
    host=op('/project1').create(baseCOMP,'projection_reset_qa')
    wall=host.copy(original.parent().op('wall_output'),name='wall_output')
    show=host.copy(original,name='show_control')
    show.op('show_tick').par.active=False
    ext=show.ext.ShowControlExt;runtime=show.op('projection_mapping').module
    polygon=show.op('projection_polygon').module;editor=show.op('polygon_editor')
    checks={};report=dict(ok=False,generated_at=datetime.now(timezone.utc).isoformat(),hardware_outputs_tested=False)
    try:
        show.par.Masterblackout=True;show.par.Audioenabled=False;wall.par.Blackout=True
        show.par.Routingmode='independent';show.par.Outputmode='wall'
        samples=dict(blx=.07,bly=.09,brx=.92,bry=.08,trx=.94,try_=.91,tlx=.06,tly=.94,
                     cropleft=.1,cropright=.9,cropbottom=.05,croptop=.95,
                     rotate=17,flipx=True,flipy=True,maskenabled=True,maskshape='polygon',
                     maskpolygon='[[0.1,0.1],[0.9,0.1],[0.6,0.9]]',maskfile='assets/mask.png',
                     maskchannel='alpha',maskinvert=True,maskopacity=.6,maskx=.45,masky=.55,
                     maskwidth=.8,maskheight=.7,maskrotate=-23,maskfeather=.08,
                     edgeleft=.1,edgeright=.2,edgebottom=.15,edgetop=.12,edgeall=.06,edgegamma=1.7,
                     brightness=.7,gamma=1.4,width=640,height=360)
        samples['try']=samples.pop('try_')
        def seed():
            for i in (1,2,3):
                for suffix,value in samples.items():show.par['Output'+str(i)+suffix]=value
                show.par['Output'+str(i)+'track']=4-i
                show.par['Output'+str(i)+'blackout']=i==2
            show.UpdateMapping()
        def values():return {p.name:p.eval() for p in show.customPars if ext._mapping_parameter(p)}
        def expect_reset(before,indices,section):
            changed={'Output'+str(i)+s for i in indices for s in runtime.reset_suffixes(section)}
            return all(v==(show.par[k].default if k in changed else before[k]) for k,v in values().items())
        route=show.op('projection_mapping_callbacks')
        for i in (1,2,3):
            show.par.Mappingprojector=str(i)
            for name,_,section,_ in runtime.RESET_CONTROLS:
                seed();before=values()
                route.module.onPulse(show.par[name])
                checks['reset_'+str(i)+'_'+section]=expect_reset(before,(i,),section)
                # Separate native parameter panels target their own projector,
                # even when the global selector points elsewhere.
                seed();before=values();show.par.Mappingprojector=str(i%3+1)
                local=show.op('projection'+str(i))
                local.op('reset_callbacks').module.onPulse(local.par[name])
                checks['panel_reset_'+str(i)+'_'+section]=expect_reset(before,(i,),section)
                show.par.Mappingprojector=str(i)
            seed();before=values();route.module.onPulse(show.par.Resetmapping)
            checks['reset_all_selected_'+str(i)]=expect_reset(before,(i,),'all')
            seed();before=values();local=show.op('projection'+str(i))
            local.op('reset_callbacks').module.onPulse(local.par.Resetmapping)
            checks['panel_reset_all_'+str(i)]=expect_reset(before,(i,),'all')
        seed();polygon.open_editor(show,2,open_window=False)
        show.par.Mappingprojector='2';route.module.onPulse(show.par.Resetmask)
        checks['reset_mask_clears_open_draft']=polygon.state_for(editor)['points']==[] and not editor.par.Invert and editor.par.Feather==.02 and editor.par.Level==1
        seed();before=values();route.module.onPulse(show.par.Resetallprojectors)
        checks['reset_all_three']=expect_reset(before,(1,2,3),'all')
        checks['resets_keep_cues']=ext.document['cues']==original_doc['cues']
        checks['resets_keep_safety_and_mode']=bool(show.par.Masterblackout) and not show.par.Audioenabled and show.par.Outputmode=='wall' and bool(wall.par.Blackout)
        # Save the entire current calibration and all cues to a QA-only file.
        seed();expected=values();expected_cues=copy.deepcopy(ext.document['cues'])
        polygon.open_editor(show,1,open_window=False)
        draft=polygon.state_for(editor);draft['points'][0]=[.2,.2];polygon.refresh(editor,draft)
        destination=ROOT/'build/envoy-validation/projection-reset-show.json'
        show.par.Showfile=str(destination)
        route.module.onPulse(show.par.Savemapping)
        saved=json.loads(destination.read_text(encoding='utf-8'))
        checks['save_every_mapping_value']=saved['mapping']==expected
        checks['save_keeps_cues']=saved['cues']==expected_cues
        checks['save_excludes_unapplied_draft']=saved['mapping']['Output1maskpolygon']==samples['maskpolygon']
        route.module.onPulse(show.par.Resetallprojectors)
        ext.LoadShow()
        checks['load_every_mapping_value']=values()==expected
        checks['load_refreshes_polygon_editor']=polygon.state_for(editor)['points']==[[.1,.1],[.9,.1],[.6,.9]]
        checks['load_keeps_cues']=ext.document['cues']==expected_cues
        checks['load_safe']=bool(show.par.Masterblackout) and not show.par.Audioenabled
        checks['load_commits_matrices_immediately']=show.par.Mappingstatus=='Mapping valid' and ext._mapping_key==tuple((p.name,p.eval()) for p in show.customPars if ext._mapping_parameter(p))
        # Re-save creates the normal validated backup; it is not a new format.
        prior=set(destination.parent.glob('projection-reset-show.backup-*.json'))
        route.module.onPulse(show.par.Savemapping)
        backups=set(destination.parent.glob('projection-reset-show.backup-*.json'))-prior
        checks['normal_show_backup_created']=len(backups)==1 and json.loads(next(iter(backups)).read_text(encoding='utf-8'))['mapping']==expected
        # A minimal older show must not inherit stale geometry/grade/masks.
        older=copy.deepcopy(saved);older['mapping']={}
        oldpath=destination.with_name('projection-reset-legacy-show.json')
        oldpath.write_text(json.dumps(older),encoding='utf-8')
        show.par.Output1cropleft=1 # invalid CURRENT edit must not prevent valid file load
        show.par.Showfile=str(oldpath);ext.LoadShow()
        checks['legacy_defaults_every_mapping_control']=all(v==show.par[k].default for k,v in values().items())
        checks['legacy_draft_cleared']=polygon.state_for(editor)['points']==[]
        checks['legacy_load_valid']=show.par.Mappingstatus=='Mapping valid'
        # Bad data must reject the file without changing current calibration.
        corrupt=copy.deepcopy(saved);corrupt['mapping']['Output1maskpolygon']='[[0,0],[1,1],[0,1],[1,0]]'
        badpath=destination.with_name('projection-reset-invalid-show.json')
        badpath.write_text(json.dumps(corrupt),encoding='utf-8')
        show.par.Showfile=str(badpath);before=values();document=copy.deepcopy(ext.document)
        rejected=False
        try:ext.LoadShow()
        except ValueError:rejected=True
        checks['invalid_load_is_atomic']=rejected and values()==before and ext.document==document
        checks['no_output_windows']=not any(w is not None and w.isOpen for w in show.op('show_review_export').module._export_windows(show))
        checks['no_errors']=not show.errors(recurse=True) and not wall.errors(recurse=True)
        checks['original_cues_untouched']=original.ext.ShowControlExt.document==original_doc
        checks['original_controls_untouched']=all(original.par[k].eval()==v for k,v in original_values.items() if k not in ('Showtime','Transport','Status','Mappingstatus','Projectionstatus'))
        report['ok']=all(bool(v) for v in checks.values())
    except Exception:report['error']=traceback.format_exc()
    finally:host.destroy()
    report['checks']={k:bool(v) for k,v in checks.items()}
    if write_report:
        (ROOT/'build/envoy-validation/projection-resets.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return report


def validate_deferred():
    """Exercise native button delivery on real frames without opening displays."""
    original=op('/project1/imagefx_demo/show_control')
    original_doc=copy.deepcopy(original.ext.ShowControlExt.document)
    host=op('/project1').create(baseCOMP,'projection_mapping_events_qa')
    wall=host.copy(original.parent().op('wall_output'),name='wall_output')
    show=host.copy(original,name='show_control')
    show.op('show_tick').par.active=False
    show.par.Masterblackout=True;show.par.Audioenabled=False;wall.par.Blackout=True
    checks={}
    report=dict(ok=False,generated_at=datetime.now(timezone.utc).isoformat(),hardware_outputs_tested=False)
    # Record native dispatch; inspect the actual panels manually, not in the
    # disposable fixture. Reset still runs its real implementation here.
    runtime=show.op('projection_mapping')
    runtime.text += "\n_original_on_pulse=on_pulse\ndef on_pulse(show,action):\n    show.store('qa_actions',show.fetch('qa_actions',[],search=False)+[action])\n    return True if action in ('Editmapping','Previewmapping','Drawmask') else _original_on_pulse(show,action)\n"
    def steps():
        show.par.Mappingprojector='2'
        show.par.Output1maskenabled=True;show.par.Output1edgeall=.2
        show.par.Output2maskenabled=True;show.par.Output2maskwidth=.3
        show.par.Output2blx=.1;show.par.Output2edgeall=.25
        show.par.Output2brightness=.7;show.par.Output2gamma=1.4
        retained={name:show.par['Output2'+name].eval() for name in ('track','blackout')}
        for action in ('Editmapping','Previewmapping','Resetmapping'):
            show.par[action].pulse()
            yield;yield
        checks['native_buttons_dispatch_once']=show.fetch('qa_actions',[],search=False)==['Editmapping','Previewmapping','Resetmapping']
        checks['reset_selected_mask']=not show.par.Output2maskenabled and show.par.Output2maskwidth==1
        checks['reset_selected_shape_edges']=show.par.Output2blx==0 and show.par.Output2edgeall==0
        checks['reset_updates_bound_editor']=not show.op('projection2').par.Maskenabled and show.op('projection2').par.Edgeall==0
        checks['reset_keeps_other_projector']=bool(show.par.Output1maskenabled) and show.par.Output1edgeall==.2
        checks['reset_keeps_output_settings']=all(show.par['Output2'+name].eval()==value for name,value in retained.items())
        checks['reset_includes_resolution_grade']=show.par.Output2width==1920 and show.par.Output2height==1080 and show.par.Output2brightness==1 and show.par.Output2gamma==1
        # Deliver every new pulse through TD's real event queue, including the
        # section resets in all three dedicated projector parameter panels.
        # Window-opening actions above are dispatch-only; saving uses a QA file.
        destination=ROOT/'build/envoy-validation/projection-native-events-show.json'
        show.par.Showfile=str(destination)
        remaining=[name for name in runtime.module.ACTIONS if name not in ('Editmapping','Previewmapping','Resetmapping')]
        for action in remaining:
            show.par[action].pulse()
            yield;yield
        checks['every_mapping_pulse_delivered_once']=show.fetch('qa_actions',[],search=False)==['Editmapping','Previewmapping','Resetmapping']+remaining
        checks['native_save_writes_show']=destination.is_file() and json.loads(destination.read_text(encoding='utf-8'))['cues']==show.ext.ShowControlExt.document['cues']
        for i in (1,2,3):
            local=show.op('projection'+str(i))
            for action,_,section,_ in (*runtime.module.RESET_CONTROLS,('Resetmapping','','all','')):
                suffixes=runtime.module.reset_suffixes(section)
                parameters=[show.par['Output'+str(i)+suffix] for suffix in suffixes]
                # A valid non-default representative in each group proves the
                # event changed state rather than observing untouched defaults.
                representative={'corners':('blx',.1),'crop':('cropleft',.1),
                    'transform':('rotate',12),'mask':('maskenabled',True),
                    'edges':('edgeall',.2),'grade':('brightness',.5),
                    'resolution':('width',640),'all':('gamma',1.4)}[section]
                show.par['Output'+str(i)+representative[0]]=representative[1]
                local.par[action].pulse()
                yield;yield
                checks['native_panel_reset_{}_{}'.format(i,section)]=all(p.eval()==p.default for p in parameters)
        checks['events_keep_safety']=bool(show.par.Masterblackout) and bool(wall.par.Blackout) and not show.par.Audioenabled
        checks['events_keep_cues']=original.ext.ShowControlExt.document==original_doc
        checks['events_no_output_windows']=not any(w is not None and w.isOpen for w in show.op('show_review_export').module._export_windows(show))
        checks['events_no_errors']=not show.errors(recurse=True) and not wall.errors(recurse=True)
    sequence=steps()
    def finish():
        report.update(checks=checks,ok=bool(checks) and all(checks.values()) and 'error' not in report)
        (ROOT/'build/envoy-validation/projection-mapping-events.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        host.destroy()
        print('Projection mapping native events:',report)
    def advance():
        try:next(sequence)
        except StopIteration:finish()
        except Exception:
            report['error']=traceback.format_exc();finish()
        else:run('args[0]()',advance,delayFrames=1)
    run('args[0]()',advance,delayFrames=1)


if __name__=='__main__':print(validate())
