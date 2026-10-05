"""Native UHD pixel/control checks in a disposable fixture; no display opens."""
from pathlib import Path
from datetime import datetime, timezone
import json
import traceback
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
REPORT=ROOT/'build/envoy-validation/wall-output.json'


def validate(write_report=True):
    wall=op('/project1/imagefx_demo/wall_output')
    checks={}
    report=dict(ok=False,generated_at=datetime.now(timezone.utc).isoformat(),hardware_output_tested=False)
    if wall is None:
        report['error']='wall_output is missing; rebuild the project'
        return report
    host=op('/project1').create(baseCOMP,'wall_output_qa')
    fixture=host.copy(wall,name='wall_output')
    controller=fixture.op('controller').module
    try:
        fixture.par.Sourcemode='independent'
        fixture.par.Blackout=False
        fixture.par.Testpattern=False
        fixture.par.Enabled=True
        fixture.par.Displayindex=-1
        fixture.par.Monitorenabled=True
        fixture.par.Showstats=True
        fixture.par.Fit='stretch'
        colors=[(1,0,0),(0,1,0),(0,0,1)]
        for i,color in enumerate(colors,1):
            source=host.create(constantTOP,'source{}'.format(i))
            source.par.outputresolution='custom'
            source.par.resolutionw,source.par.resolutionh=1920,1080
            source.par.colorr,source.par.colorg,source.par.colorb=color
            fixture.par['Projector{}top'.format(i)]='../source{}'.format(i)
        def pixels(node):
            node.cook(force=True)
            return np.array(node.numpyArray(delayed=False),copy=True)
        def packed(): return pixels(fixture.op('out1_wall_4k'))
        a=packed()
        checks['uhd_exact']=a.shape==(2160,3840,4)
        checks['q1_top_left_red']=np.allclose(a[1080:,:1920,:3],colors[0])
        checks['q2_top_right_green']=np.allclose(a[1080:,1920:,:3],colors[1])
        checks['q3_bottom_left_blue']=np.allclose(a[:1080,:1920,:3],colors[2])
        checks['q4_exact_monitor']=np.array_equal(a[:1080,1920:],pixels(fixture.op('comp_monitor_out')))
        checks['seams_no_gutters']=all(np.allclose(a[y,x,:3],c) for x,y,c in ((1919,1080,colors[0]),(1920,1080,colors[1]),(1919,1079,colors[2])))
        checks['opaque_output']=np.all(a[:,:,3]==1)
        multi=pixels(fixture.op('layout_multiview'))
        checks['multiview_16_by_9_tiles']=multi.shape==(360,1920,4) and all(np.allclose(multi[:,i*640:(i+1)*640,:3],c) for i,c in enumerate(colors))
        checks['stats_present']=np.max(a[:720,1920:,:3])>.5 and 'FPS:' in fixture.op('monitor_text').par.text.eval()
        checks['source_status_parameter_evaluates']=fixture.par.Sourcesstatus.eval()==controller.source_status(fixture)
        for state,expected in ((True,True),(False,False)):
            fixture.par.Blackout=state
            b=packed()
            checks['blackout_'+str(state)]=bool(np.all(b[1080:,:,:3]==0))==expected
            checks['confidence_survives_blackout_'+str(state)]=np.max(b[:720,1920:,:3])>.5
        fixture.par.Enabled=False
        b=packed()
        checks['enable_off_blacks_projectors']=np.all(b[1080:,:,:3]==0) and np.all(b[:1080,:1920,:3]==0)
        fixture.par.Enabled=True
        fixture.par.Monitorenabled=False
        b=packed()
        checks['monitor_off_q4_only']=np.all(b[:1080,1920:,:3]==0) and np.allclose(b[1500,200,:3],colors[0])
        fixture.par.Monitorenabled=True
        fixture.par.Showstats=False
        b=packed()
        checks['stats_off_keeps_previews']=np.all(b[:720,1920:,:3]==0) and np.any(b[720:1080,1920:,:3]>0)
        fixture.par.Showstats=True
        fixture.par.Sourcemode='identical'
        fixture.par.Mastertop='../source2'
        b=packed()
        checks['identical_master_routing']=all(np.allclose(b[y,x,:3],colors[1]) for x,y in ((200,1500),(2200,1500),(200,400)))
        source=host.create(glslTOP,'panorama')
        code=host.create(textDAT,'panorama_code')
        code.text='layout(location=0) out vec4 fragColor; void main(){vec3 c=vUV.x<1.0/3.0?vec3(1,0,0):(vUV.x<2.0/3.0?vec3(0,1,0):vec3(0,0,1)); fragColor=TDOutputSwizzle(vec4(c,1));}'
        source.par.pixeldat='panorama_code'
        source.par.outputresolution='custom'
        source.par.resolutionw,source.par.resolutionh=5760,1080
        fixture.par.Mastertop='../panorama'
        fixture.par.Sourcemode='panoramic'
        b=packed()
        checks['panorama_exact_three_slices']=all(np.allclose(b[y,x,:3],c,atol=.005) for x,y,c in ((960,1500,colors[0]),(2880,1500,colors[1]),(960,400,colors[2])))
        checks['panorama_native_status']='scaled' not in controller.source_status(fixture)
        for i in (1,2,3):
            p=pixels(fixture.op('p{}_out'.format(i)))
            checks['panorama_slice{}_edges'.format(i)]=np.allclose(p[540,[0,1919],:3],colors[i-1],atol=.005)
        fixture.par.Sourcemode='identical'
        fixture.par.Mastertop='../source1'
        host.op('source1').par.resolutionw=1080
        for fit in ('fit','fill','stretch'):
            fixture.par.Fit=fit
            p=pixels(fixture.op('p1_out'))
            checks['fit_'+fit]=(np.max(p[:,0,:3])==0 if fit=='fit' else np.allclose(p[:,:,:3],colors[0]))
        fixture.par.Mastertop='../does_not_exist'
        checks['missing_input_black']=np.all(pixels(fixture.op('p1_out'))[:,:,:3]==0)
        checks['missing_input_visible']='Missing' in controller.source_status(fixture)
        fixture.par.Mastertop='out1_wall_4k'
        checks['local_feedback_rejected']=controller.source_path(fixture,1)=='black'
        # Exercise Show Control adapter with a deterministic minimal sibling.
        show=host.create(baseCOMP,'show_control')
        page=show.appendCustomPage('Fixture')
        for name,value in (('Routingmode','independent'),('Transport','stopped'),('Status','QA fixture')):
            page.appendStr(name); show.par[name]=value
        page.appendToggle('Masterblackout')
        page.appendFloat('Showtime')
        page.appendInt('Selectedcue'); show.par.Selectedcue=1
        for i in (1,2,3):
            output=show.create(selectTOP,'out{}_projector'.format(i))
            output.par.top='../source{}'.format(i)
        fixture.par.Sourcemode='show'; fixture.par.Fit='stretch'
        b=packed()
        checks['show_control_routes_three_mapped_feeds']=all(np.allclose(b[y,x,:3],c) for x,y,c in ((960,1500,colors[0]),(2880,1500,colors[1]),(960,400,colors[2])))
        fixture.par.Testpattern=True; show.par.Masterblackout=True
        checks['show_master_blackout_beats_wall_pattern']=np.all(packed()[1080:,:,:3]==0)
        show.par.Masterblackout=False; fixture.par.Testpattern=False
        show.par.Transport='paused'; show.par.Showtime=12.5
        checks['cue_diagnostics_live']='paused' in controller.monitor_text(fixture) and '12.50' in controller.monitor_text(fixture)
        fixture.par.Sourcemode='independent'
        fixture.par.Projector1top='../source3'
        checks['independent_path_change_live']=np.allclose(pixels(fixture.op('p1_out'))[:,:,:3],colors[2])
        fixture.par.Projector1top='../source1'
        fixture.par.Testpattern=True
        fixture.par.Sourcemode='independent'
        b=packed()
        checks['test_pattern_changes_pixels']=not np.array_equal(a[1080:,:1920],b[1080:,:1920])
        for i,(x,y) in enumerate(((0,1080),(1920,1080),(0,0)),1):
            checks['pattern{}_upright'.format(i)]=np.allclose(b[y+1050,x+30,:3],(1,1,0)) and np.allclose(b[y+30,x+1890,:3],(0,1,1))
        fixture.par.Blackout=True
        checks['blackout_beats_test_pattern']=np.all(packed()[1080:,:,:3]==0)
        fixture.par.Displayindex=-1
        for action in ('Checkdisplay','Openwall','Closewall'):
            fixture.op('wall_parameters').module.onPulse(fixture.par[action])
            checks['button_'+action]=('NOT OPENED' in fixture.par.Status.eval() if action!='Closewall' else 'closed' in fixture.par.Status.eval())
        checks['display_native_and_borderless']=fixture.op('wall_window').par.size=='fill' and fixture.op('wall_window').par.dpiscaling=='native' and not fixture.op('wall_window').par.borders
        checks['window_never_auto_opens']='performance.pulse' not in fixture.op('safe_start').text
        checks['display_binding']=fixture.op('wall_window').par.display.expr=='max(0,int(parent().par.Displayindex))'
        checks['startup_callback_active']=bool(fixture.op('safe_start').par.start)
        controller.safe_start(fixture)
        checks['safe_start_blackout_and_no_pattern']=bool(fixture.par.Blackout) and not fixture.par.Testpattern
        checks['performance_real_channels']=all(fixture.op('performance')[name] is not None for name in ('fps','msec','gpu_mem_used','dropped_frames'))
        checks['no_glsl_errors']=not fixture.op('out1_wall_4k').errors(recurse=True)
        checks['all_wall_operator_diagnostics_clean']=not fixture.errors(recurse=True)
        checks['defaults_blackout_unassigned']=wall.par.Blackout.default and wall.par.Displayindex.default==-1
        checks['no_wall_in_cue_deck']=op('/project1/imagefx_demo/show_control/deck_template/wall_output') is None
        # Export a labeled calibration contact for visual review, not audience output.
        fixture.par.Blackout=False; fixture.par.Testpattern=True; fixture.par.Sourcemode='independent'
        fixture.op('out1_wall_4k').cook(force=True)
        preview=ROOT/'build/envoy-validation/wall-output-calibration.png'
        preview.parent.mkdir(parents=True,exist_ok=True)
        fixture.op('out1_wall_4k').save(str(preview))
        report['ok']=all(bool(v) for v in checks.values())
    except Exception: report['error']=traceback.format_exc()
    finally: host.destroy()
    report['checks']={k:bool(v) for k,v in checks.items()}
    if write_report:
        REPORT.parent.mkdir(parents=True,exist_ok=True)
        REPORT.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    return report


def validate_deferred():
    """Deliver native pulse events on actual TD frames; never arm an output."""
    host=op('/project1').create(baseCOMP,'wall_events_qa')
    wall=host.copy(op('/project1/imagefx_demo/wall_output'),name='wall_output')
    checks={}
    def steps():
        wall.par.Displayindex=-1
        wall.par.Checkdisplay.pulse()
        yield; yield
        checks['native_check_button']='NOT OPENED' in wall.par.Status.eval()
        wall.par.Status='test pending'
        wall.par.Openwall.pulse()
        yield; yield
        checks['native_open_button_fails_closed']='NOT OPENED' in wall.par.Status.eval()
        wall.par.Closewall.pulse()
        yield; yield
        checks['native_close_button']='closed' in wall.par.Status.eval()
        wall.par.Allowprimary=True
        yield; yield
        checks['changing_display_policy_closes_window']='Closed after display' in wall.par.Status.eval()
    sequence=steps()
    report=dict(ok=False,generated_at=datetime.now(timezone.utc).isoformat(),hardware_output_tested=False)
    def finish():
        report.update(checks=checks,ok=bool(checks) and all(checks.values()) and 'error' not in report)
        REPORT.with_name('wall-output-events.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        host.destroy()
        print('Wall native events:',report)
    def advance():
        try: next(sequence)
        except StopIteration: finish()
        except Exception:
            report['error']=traceback.format_exc(); finish()
        else: run('args[0]()',advance,delayFrames=1)
    run('args[0]()',advance,delayFrames=1)


if __name__=='__main__': print(validate())
