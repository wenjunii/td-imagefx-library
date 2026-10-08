"""State-isolated native pixels, control endpoints, and real-frame media QA."""
from pathlib import Path
from datetime import datetime, timezone
import json
import traceback
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
REPORT=ROOT/'build/envoy-validation/color-composition.json'


def _fixture():
    host=op('/project1').create(baseCOMP,'color_composition_qa')
    # Supply binding targets before copying, so on-create evaluation is valid.
    page=host.appendCustomPage('Fixture')
    for name in ('Colorswitchenabled','Imagecompositionenabled'):
        page.appendToggle(name)[0].val=True
    def image(name,color):
        node=host.create(constantTOP,name)
        node.par.outputresolution='custom'; node.par.resolutionw=160; node.par.resolutionh=90
        for suffix,value in zip(('colorr','colorg','colorb','alpha'),color): node.par[suffix]=value
        return node
    a=image('red', (1.,0.,0.,1.)); b=image('blue',(0.,0.,1.,1.))
    color=host.copy(op('/project1/imagefx_demo/color_switch'),name='color')
    composition=host.copy(op('/project1/imagefx_demo/image_composition'),name='composition')
    for module in (color,composition):
        module.par.Enabled.mode=ParMode.CONSTANT
        module.par.Enabled.bindExpr=""
    color.par.Enabled=True; composition.par.Enabled=True; composition.par.Autotime=False
    a.outputConnectors[0].connect(color.inputConnectors[0])
    a.outputConnectors[0].connect(composition.inputConnectors[0])
    b.outputConnectors[0].connect(composition.inputConnectors[1])
    return host,a,b,color,composition


def _pixels(component):
    output=component.op('out1_image') if component.family=='COMP' else component
    output.cook(force=True)
    data=output.numpyArray(delayed=False)
    if data is None: data=output.numpyArray(delayed=False)
    if data is None or not np.isfinite(data).all(): raise AssertionError('Missing/non-finite pixels: '+output.path)
    if output.errors(recurse=True): raise AssertionError(str(output.errors(recurse=True)))
    return np.array(data,copy=True)


def validate(write_report=True):
    report=dict(ok=False,generated_at=datetime.now(timezone.utc).isoformat(),checks={})
    checks=report['checks']; host=None
    try:
        host,a,b,color,c=_fixture()
        base=_pixels(a)
        color.par.Fromcolorr=1.; color.par.Fromcolorg=0.; color.par.Fromcolorb=0.
        color.par.Tocolorr=0.; color.par.Tocolorg=1.; color.par.Tocolorb=0.
        checks['selected_red_becomes_green']=np.allclose(_pixels(color)[0,0],[0,1,0,1],atol=.01)
        b.outputConnectors[0].connect(color.inputConnectors[0])
        checks['unselected_blue_unchanged']=np.allclose(_pixels(color),_pixels(b),atol=.001)
        a.outputConnectors[0].connect(color.inputConnectors[0])
        color.par.Mix=0
        checks['color_zero_amount_bypass']=np.array_equal(_pixels(color),base)
        color.par.Mix=1; color.par.Enabled=False
        checks['color_disabled_bypass']=np.array_equal(_pixels(color),base)
        color.par.Enabled=True; color.par.Showmask=True
        checks['selection_mask_white']=np.allclose(_pixels(color)[0,0],[1,1,1,1],atol=.01)
        color.par.Showmask=False; a.par.alpha=.4
        checks['color_alpha_preserved']=np.allclose(_pixels(color)[:,:,3],.4,atol=.01)
        a.par.alpha=1.; a.par.colorr=.4; color.par.Matchmode='hue'
        checks['hue_across_shades']=np.allclose(_pixels(color)[0,0],[0,.4,0,1],atol=.01)
        color.par.Preserveshading=0
        checks['flat_replacement']=np.allclose(_pixels(color)[0,0],[0,1,0,1],atol=.01)
        color.par.Matchmode='rgb'; color.par.Preserveshading=1.
        color.par.Fromcolorr=0.; a.par.colorr=0.
        checks['black_can_be_replaced_with_shading_on']=np.allclose(_pixels(color)[0,0],[0,1,0,1],atol=.01)
        color.par.Fromcolorr=1.
        a.par.colorr=1
        image=_pixels(c)
        checks['split_red_left_blue_right']=np.allclose(image[45,20],[1,0,0,1],atol=.01) and np.allclose(image[45,140],[0,0,1,1],atol=.01)
        c.par.Swap=True
        swapped=_pixels(c)
        checks['swap_positions']=np.allclose(swapped[45,20],[0,0,1,1],atol=.01) and np.allclose(swapped[45,140],[1,0,0,1],atol=.01)
        c.par.Swap=False; c.par.Layout='vertical'
        vertical=_pixels(c)
        checks['top_bottom_orientation']=np.allclose(vertical[70,80],[1,0,0,1],atol=.01) and np.allclose(vertical[20,80],[0,0,1,1],atol=.01)
        c.par.Layout='horizontal'; c.par.Ratio='custom'; c.par.Split=.25
        custom=_pixels(c)
        checks['manual_split']=np.allclose(custom[45,30],[1,0,0,1],atol=.01) and np.allclose(custom[45,50],[0,0,1,1],atol=.01)
        c.par.Ratio='equal'
        a_branch=c.op('a_effects'); b_branch=c.op('b_effects')
        a_branch.par.Coloradjustmentenabled=True; a_branch.op('color_adjustment').par.Invert=1.
        independent=_pixels(c)
        checks['a_effect_does_not_change_b']=np.allclose(independent[45,20],[0,1,1,1],atol=.02) and np.allclose(independent[45,140],[0,0,1,1],atol=.02)
        a_branch.par.Coloradjustmentenabled=False
        b_branch.par.Colorswitchenabled=True
        bs=b_branch.op('color_switch')
        for key,value in dict(Fromcolorr=0.,Fromcolorg=0.,Fromcolorb=1.,Tocolorr=0.,Tocolorg=1.,Tocolorb=0.).items(): bs.par[key]=value
        independent=_pixels(c)
        checks['b_color_switch_does_not_change_a']=np.allclose(independent[45,20],[1,0,0,1],atol=.02) and np.allclose(independent[45,140],[0,1,0,1],atol=.02)
        b_branch.par.Colorswitchenabled=False
        c.par.Aaspect='1x1'; c.par.Aleft=10; c.par.Aright=10
        _pixels(c)
        checks['a_crop_independent']=c.op('a_crop').op('out1_image').width==90 and c.op('b_crop').op('out1_image').width==160
        c.par.Aleft=0; c.par.Aright=0; c.par.Aaspect='free'
        c.par.Afit='contain'
        contain=_pixels(c)
        checks['fit_letterboxes']=np.allclose(contain[2,20],[0,0,0,1],atol=.01) and np.allclose(contain[45,20],[1,0,0,1],atol=.01)
        c.par.Afit='cover'; c.par.Layout='overlay'; c.par.Bopacity=.5
        checks['over_straight_alpha']=np.allclose(_pixels(c)[45,80],[.5,0,.5,1],atol=.02)
        c.par.Ontop='a'
        checks['overlap_order']=np.allclose(_pixels(c)[45,80],[1,0,0,1],atol=.01)
        c.par.Ontop='b'; c.par.Bopacity=1.; c.par.Layout='horizontal'
        c.par.Enabled=False
        checks['composition_disabled_exact_bypass']=np.array_equal(_pixels(c),_pixels(a))
        c.par.Enabled=True
        for prefix in ('a','b'):
            branch=c.op(prefix+'_effects'); flow=branch.op('workflow').module
            checks[prefix+'_independent_workflow']=len(flow.current(branch))==15 and 'image_composition' not in flow.current(branch)
            c.par.Manualtime=2.75
            checks[prefix+'_clock_follows_composition']=abs(branch.op('calligraphic_shadow').par.Time.eval()-2.75)<1e-6
            checks[prefix+'_viewer_self']=branch.par.opviewer.eval()==branch.op('out1_image')
        for component in (color,c):
            checks[component.name+'_viewer_self']=component.par.opviewer.eval()==component.op('out1_image')
            for par in component.customPars:
                if par.readOnly or par.isPulse or par.isString: continue
                old=par.eval()
                try:
                    if par.isMenu: values=list(par.menuNames)
                    elif par.isToggle: values=[False,True]
                    elif par.isNumber:
                        values=[par.min,par.max]
                        checks[component.name+'_'+par.name+'_range']=par.min<par.max and par.normMin<par.normMax
                    else: continue
                    for value in values:
                        par.val=value
                        actual=par.eval()
                        checks[component.name+'_'+par.name+'_'+str(value)]=actual==value or (isinstance(value,(float,int)) and abs(actual-value)<1e-5)
                        _pixels(component)
                finally: par.val=old
        for width,height in ((1920,1080),(3840,2160)):
            a.par.resolutionw=width; a.par.resolutionh=height
            checks['canvas_'+str(width)]=_pixels(c).shape==(height,width,4)
        a.par.resolutionw=160; a.par.resolutionh=90
        _pixels(c); _pixels(color)
        report['operator_errors']={'composition':str(c.errors(recurse=True)), 'color':str(color.errors(recurse=True))}
        checks['no_recursive_errors']=not c.errors(recurse=True) and not color.errors(recurse=True)
        report['ok']=all(bool(v) for v in checks.values())
    except Exception: report['error']=traceback.format_exc()
    finally:
        if host is not None: host.destroy()
    report['checks']={k:bool(v) for k,v in checks.items()}
    if write_report:
        REPORT.parent.mkdir(parents=True,exist_ok=True)
        REPORT.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    return report


def validate_deferred():
    """Real pulse delivery and image decode, including cue capture round trip."""
    host,a,b,color,c=_fixture(); checks={}; report=dict(ok=False,checks=checks)
    folder=REPORT.parent; folder.mkdir(parents=True,exist_ok=True)
    paths=[folder/'composition-a.png',folder/'composition-b.png']
    a.save(str(paths[0])); b.save(str(paths[1]))
    def steps():
        color.par.Sampleposx=.25; color.par.Sampleposy=.75
        color.par.Fromcolorr=0; color.par.Fromcolorg=1
        color.par.Sample.pulse()
        yield; yield
        checks['sample_pulse']=np.allclose([color.par.Fromcolorr.eval(),color.par.Fromcolorg.eval(),color.par.Fromcolorb.eval()],[1,0,0],atol=.01)
        c.par.Afile=str(paths[0]); c.par.Bfile=str(paths[1])
        for _ in range(120):
            _pixels(c)
            if all(c.op(p+'_file').isOpen and c.op(p+'_file').isFullyPreRead for p in ('a','b')): break
            yield
        image=_pixels(c)
        checks['two_decoded_files']=np.allclose(image[45,20],[1,0,0,1],atol=.02) and np.allclose(image[45,140],[0,0,1,1],atol=.02)
        c.par.Layout='manual'; c.par.Apositionx=.2; c.par.Split=.3
        c.par.Resetlayout.pulse()
        yield; yield
        checks['reset_layout_pulse']=c.par.Layout.eval()=='horizontal' and c.par.Apositionx.eval()==0 and c.par.Split.eval()==.5
        checks['reset_keeps_media']=c.par.Afile.eval()==str(paths[0]) and c.par.Bfile.eval()==str(paths[1])
        for p in ('A','B'):
            c.par[p+'left']=25; c.par[p+'aspect']='1x1'; c.par[p+'resetcrop'].pulse()
            yield; yield
            checks[p+'_reset_crop_pulse']=c.par[p+'left'].eval()==0 and c.par[p+'aspect'].eval()=='free'
            c.par[p+'reload'].pulse(); c.par[p+'restart'].pulse()
            yield; yield
            checks[p+'_reload_clean']=not c.op(p.lower()+'_file').isInvalid
        for branch_name in ('a_effects','b_effects'):
            branch=c.op(branch_name)
            branch.par.Stageselection='color_switch'; branch.par.Stagefirst.pulse()
            yield; yield
            checks[branch_name+'_move_pulse']=branch.op('workflow').module.current(branch)[0]=='color_switch'
            rack=branch.op('fx_rack')
            rack.par.Slot1effect='tdimagefx.stylize.pixelate'
            yield; yield
            checks[branch_name+'_rack_selection_event']=rack.SlotState(1)['package']['id']=='tdimagefx.stylize.pixelate'
        video=folder/'show-av-fixture.mp4'
        if not video.is_file(): raise RuntimeError('Generate the standard show-av-fixture.mp4 before deferred media QA')
        c.par.Afile=str(video); c.par.Bfile=str(video)
        readers=[c.op('a_file'),c.op('b_file')]
        for _ in range(120):
            if all(r.isOpen and r.isFullyPreRead for r in readers): break
            yield
        for _ in range(3): yield
        snapshot=lambda: [_pixels(r) for r in readers]
        same=lambda x,y: all(np.allclose(a,b,atol=.002) for a,b in zip(x,y))
        changed=lambda x,y: all(float(np.mean(np.abs(a-b)))>1e-4 for a,b in zip(x,y))
        zero=snapshot(); c.par.Manualtime=.7
        for _ in range(4): yield
        later=snapshot(); checks['both_videos_manual_seek']=changed(zero,later)
        for _ in range(4): yield
        checks['both_videos_manual_pause']=same(later,snapshot())
        c.par.Manualtime=3.7
        for _ in range(4): yield
        checks['both_videos_loop']=same(later,snapshot())
        c.par.Manualtime=.3; c.par.Ain=1.; c.par.Bin=1.; c.par.Aspeed=-1.; c.par.Bspeed=-1.
        for _ in range(4): yield
        checks['reverse_and_offset']=same(later,snapshot())
        c.par.Manualtime=10000.; c.par.Aloop=False; c.par.Bloop=False
        c.par.Ain=0.; c.par.Bin=0.; c.par.Aspeed=1.; c.par.Bspeed=1.
        for _ in range(4): yield
        end=snapshot(); c.par.Manualtime=20000.
        for _ in range(4): yield
        checks['loop_off_holds_end']=same(end,snapshot()) and changed(zero,end)
        c.par.Manualtime=0.; c.par.Aloop=True; c.par.Bloop=True
        for _ in range(4): yield
        c.par.Autotime=True; c.par.Arestart.pulse(); c.par.Brestart.pulse()
        for _ in range(3): yield
        before=snapshot()
        for _ in range(6): yield
        checks['both_videos_play']=changed(before,snapshot())
        c.par.Aplay=False; c.par.Bplay=False
        for _ in range(3): yield
        before=snapshot()
        for _ in range(6): yield
        checks['both_videos_pause']=same(before,snapshot())
        c.par.Arestart.pulse(); c.par.Brestart.pulse()
        for _ in range(4): yield
        checks['both_restart_buttons']=same(zero,snapshot())
        c.par.Bplay=True
        before=snapshot()
        for _ in range(6): yield
        after=snapshot()
        checks['b_play_independent']=same(before[:1],after[:1]) and changed(before[1:],after[1:])
        c.par.Bplay=False; c.par.Aplay=True
        for _ in range(3): yield
        before=snapshot()
        for _ in range(6): yield
        after=snapshot()
        checks['a_play_independent']=changed(before[:1],after[:1]) and same(before[1:],after[1:])
        c.par.Aplay=False; c.par.Ain=.7; c.par.Bin=.7
        for _ in range(4): yield
        checks['seek_controls_while_paused']=same(later,snapshot())
        c.par.Afile=str(paths[0])
        for _ in range(5): yield
        checks['image_and_video_together']=readers[0].width==160 and readers[1].width==320 and not c.errors(recurse=True)
        # Exercise real copied cue decks, not only dictionaries of defaults.
        # The show copy and all media readers remain inside our disposable host.
        show=host.copy(op('/project1/imagefx_demo/show_control'),name='show_qa')
        show.initializeExtensions(); show.op('show_tick').par.active=False
        ext=show.ext.ShowControlExt
        deck=ext._new_deck('look_qa')
        ext._apply_look(deck,{})
        deck.par.Imagecompositionenabled=True
        comp=deck.op('image_composition')
        comp.par.Afile=str(paths[0]); comp.par.Bfile=str(paths[1])
        comp.par.Ratio='two_one'; comp.par.Bopacity=.7; comp.par.Aleft=12
        ab=comp.op('a_effects'); bb=comp.op('b_effects')
        ab.par.Coloradjustmentenabled=True; ab.op('color_adjustment').par.Invert=.65
        bb.par.Colorswitchenabled=True; bb.op('color_switch').par.Tocolorr=.25
        flow=ab.op('workflow').module
        flow.apply_order(ab,list(reversed(flow.BRANCH_ORDER)))
        deck.allowCooking=True
        yield; yield
        captured=ext._capture_look(deck)
        deck.allowCooking=False
        ext._apply_look(deck,captured)
        deck.allowCooking=True
        yield; yield
        checks['cue_both_branches_all_values_roundtrip']=ext._capture_look(deck)==captured
        checks['cue_both_file_readers_preflighted']=set(r.path for r in ext._look_readers(deck))=={comp.op('a_file').path,comp.op('b_file').path}
        checks['cue_independent_values']=abs(ab.op('color_adjustment').par.Invert.eval()-.65)<1e-6 and abs(bb.op('color_switch').par.Tocolorr.eval()-.25)<1e-6
        comp.par.Manualtime=3.25
        checks['cue_branch_clock_bound']=abs(ab.op('calligraphic_shadow').par.Time.eval()-3.25)<1e-6
        checks['capture_ignores_inherited_playhead']=ext._capture_look(deck)==captured
        ext.tracks[1]={'deck':deck}
        target,previous=ext._target({'track':1,'target':'image_composition/b_effects/color_switch/Tocolorr','value':.75})
        target.val=.75
        checks['cue_nested_parameter_target']=abs(bb.op('color_switch').par.Tocolorr.eval()-.75)<1e-6 and abs(ab.op('color_switch').par.Tocolorr.eval()-.75)>.01
        ext.tracks.clear()
        deck.allowCooking=False
        ext._apply_look(deck,{})
        checks['old_look_clears_branches_and_files']=not deck.par.Imagecompositionenabled and not ab.par.Coloradjustmentenabled and not bb.par.Colorswitchenabled and not comp.par.Afile.eval() and not comp.par.Bfile.eval()
    sequence=steps()
    def finish():
        report['ok']=bool(checks) and all(bool(v) for v in checks.values()) and 'error' not in report
        report['checks']={k:bool(v) for k,v in checks.items()}
        REPORT.with_name('color-composition-deferred.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        host.destroy(); print('Color / Composition deferred:',report)
    def advance():
        try:
            _pixels(c)
            next(sequence)
        except StopIteration: finish()
        except Exception: report['error']=traceback.format_exc(); finish()
        else: run('args[0]()',advance,delayFrames=1)
    run('args[0]()',advance,delayFrames=1)


if __name__=='__main__': print(validate())
