"""State-isolated main-source pixel tests and real-frame image/video checks."""
from pathlib import Path
from datetime import datetime, timezone
import json
import traceback
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT/'build/envoy-validation/source-media.json'


def _fixture():
    host = op('/project1').create(baseCOMP, 'source_media_qa')
    demo = host.copy(op('/project1/imagefx_demo'), name='designer')
    for name in ('show_control', 'wall_output'):
        node = demo.op(name)
        if node is not None: node.destroy()
    demo.par.Resolutionpreset = 'custom'
    demo.par.Customwidth, demo.par.Customheight = 160, 90
    demo.par.Sourcefile = ''
    demo.par.Sourcemode = 'auto'
    for par in demo.customPars:
        if par.isToggle: par.val = False
    demo.op('source_image').par.vec0valuex = 0
    # TOP wires cannot cross a COMP boundary: keep the injected fixture beside
    # source_media_select rather than in the enclosing disposable QA host.
    shader = demo.create(textDAT, 'fixture_shader')
    shader.text = 'layout(location=0) out vec4 fragColor; void main(){ fragColor=TDOutputSwizzle(vec4(vUV.st, .25, .4)); }'
    fixture = demo.create(glslTOP, 'fixture')
    fixture.par.pixeldat = fixture.relativePath(shader)
    fixture.par.outputresolution = 'custom'
    fixture.par.resolutionw = fixture.par.resolutionh = 180
    return host, demo, fixture


def _pixels(node):
    node.cook(force=True)
    pixels = node.numpyArray(delayed=False)
    if pixels is None: pixels = node.numpyArray(delayed=False)
    if pixels is None or not np.isfinite(pixels).all(): raise AssertionError('Invalid pixels: '+node.path)
    return np.array(pixels, copy=True)


def _finish_report(report, path):
    report['generated_at'] = datetime.now(timezone.utc).isoformat()
    report['checks'] = {k: bool(v) for k, v in report['checks'].items()}
    report['ok'] = bool(report['checks']) and all(report['checks'].values()) and 'error' not in report
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    return report


def validate(write_report=True):
    host = None
    report = dict(ok=False, checks={})
    checks = report['checks']
    try:
        host, demo, fixture = _fixture()
        source = demo.op('source_image')
        checks['auto_empty_test_pattern'] = demo.op('source_media_runtime').module.selected(demo) == 0 and _pixels(source).std() > .05
        checks['stable_workflow_entry'] = demo.op('reference_particle_field').inputs[0] == source
        checks['all_source_controls_present'] = len([p for p in demo.customPars if p.page.name == 'Source Media']) == 17
        checks['callback_wiring'] = demo.op('source_media_callbacks').par.op.eval() == demo and bool(demo.op('source_media_callbacks').par.onpulse)
        checks['preview_route'] = "c.op('source_image').openViewer()" in demo.op('source_media_runtime').text
        demo.par.Sourcemode = 'file'
        empty = _pixels(source)
        checks['explicit_empty_file_background'] = np.allclose(empty[:,:,:3], 0) and np.allclose(empty[:,:,3], 1)
        # Inject a known square gradient to test fitting without waiting for disk.
        fixture.outputConnectors[0].connect(demo.op('source_media_select').inputConnectors[1])
        checks['fixture_connected'] = demo.op('source_media_select').inputs[1] == fixture
        demo.op('source_media_select').par.index = 1
        source.par.vec1valuex = 2
        demo.par.Sourcefit = 'contain'
        fit = _pixels(source)
        checks['fit_has_letterbox'] = np.allclose(fit[45,5],[0,0,0,1],atol=.01)
        checks['image_alpha_preserved'] = abs(float(fit[45,80,3])-.4) < .01
        demo.par.Sourcebackgroundr=.1; demo.par.Sourcebackgroundg=.2; demo.par.Sourcebackgroundb=.3; demo.par.Sourcebackgrounda=.7
        checks['letterbox_rgba'] = np.allclose(_pixels(source)[45,5],[.1,.2,.3,.7],atol=.01)
        demo.par.Sourceanchorx=0
        left = _pixels(source)
        demo.par.Sourceanchorx=1
        right = _pixels(source)
        checks['horizontal_anchor_endpoints'] = abs(float(left[45,5,3])-.4)<.01 and abs(float(right[45,5,3])-.7)<.01
        demo.par.Sourcefit='cover'; demo.par.Sourceanchory=0
        bottom = _pixels(source)
        demo.par.Sourceanchory=1
        top = _pixels(source)
        checks['fill_has_no_letterbox'] = np.allclose(top[:,:,3], .4, atol=.01)
        checks['vertical_crop_anchor_endpoints'] = float(top[45,80,1]-bottom[45,80,1])>.3
        demo.par.Sourcefit='stretch'
        stretch=_pixels(source)
        checks['stretch_covers_canvas'] = np.allclose(stretch[:,:,3],.4,atol=.01) and float(stretch[-1,-1,0])>.98
        reader=demo.op('source_media_file')
        for value in (-4.,0.,4.):
            demo.par.Sourcespeed=value
            checks['speed_'+str(value)] = abs(reader.par.speed.eval()-value)<1e-6
        for value in (0.,.7,86400.):
            demo.par.Sourcein=value
            checks['seek_'+str(value)] = abs(reader.par.cuepoint.eval()-value)<1e-6
        for value in (False,True):
            demo.par.Sourceloop=value
            checks['loop_'+str(value)] = reader.par.textendright.eval()==('cycle' if value else 'hold') and reader.par.textendleft.eval()==('cycle' if value else 'hold')
        demo.par.Resolutionpreset='hd'
        checks['hd_dimensions'] = _pixels(source).shape[:2] == (1080,1920)
        demo.par.Resolutionpreset='uhd4k'
        checks['4k_dimensions'] = _pixels(source).shape[:2] == (2160,3840)
        demo.par.Resolutionpreset='custom'; demo.par.Customwidth=173; demo.par.Customheight=91
        checks['custom_dimensions'] = _pixels(source).shape[:2] == (91,173)
        checks['shader_errors_absent'] = not source.errors()
    except Exception: report['error']=traceback.format_exc()
    finally:
        if host is not None: host.destroy()
    if write_report: return _finish_report(report, REPORT)
    report['ok']=bool(checks) and all(checks.values()) and 'error' not in report
    return report


def validate_deferred():
    host, demo, fixture = _fixture()
    checks={}; report=dict(ok=False,checks=checks)
    folder=REPORT.parent; folder.mkdir(parents=True,exist_ok=True)
    image_path=folder/'source-media-fixture.png'
    _pixels(fixture)
    fixture.save(str(image_path))
    source=demo.op('source_image'); reader=demo.op('source_media_file')
    def steps():
        demo.par.Sourcefile=str(image_path)
        for _ in range(120):
            _pixels(source)
            if reader.isOpen and reader.isFullyPreRead: break
            yield
        image=_pixels(source)
        checks['image_file_decodes'] = reader.isOpen and reader.width==180 and abs(float(image[45,80,3])-.4)<.01
        checks['auto_file_selection'] = demo.op('source_media_runtime').module.selected(demo)==2
        checks['ready_status'] = demo.par.Sourcestatus.eval().startswith('Ready:')
        demo.par.Sourcereload.pulse()
        for _ in range(5): yield
        checks['reload_pulse'] = not reader.isInvalid and np.allclose(image,_pixels(source),atol=.01)
        demo.par.Sourcemode='demo'
        for _ in range(3): yield
        checks['test_pattern_override'] = demo.op('source_media_runtime').module.selected(demo)==0 and float(np.mean(np.abs(image-_pixels(source))))>.05
        demo.par.Sourcemode='auto'; demo.par.Sourcefile=str(folder/'missing-source-qa.mp4')
        for _ in range(8): yield
        checks['missing_media_reported'] = 'ERROR' in demo.par.Sourcestatus.eval()
        video=folder/'show-av-fixture.mp4'
        if not video.is_file(): raise RuntimeError('Standard AV fixture is missing')
        demo.par.Sourcefile=str(video); demo.par.Sourceloop=True; demo.par.Sourceplay=False
        for _ in range(120):
            _pixels(source)
            if reader.isOpen and reader.isFullyPreRead: break
            yield
        for _ in range(4): yield
        zero=_pixels(reader)
        checks['video_file_decodes'] = reader.isOpen and reader.width==320 and not reader.isInvalid
        demo.par.Sourcein=.7
        for _ in range(4): yield
        seek=_pixels(reader)
        checks['seek_while_paused'] = float(np.mean(np.abs(zero-seek)))>1e-4
        for _ in range(6): yield
        checks['pause_holds_frame'] = np.allclose(seek,_pixels(reader),atol=.002)
        demo.par.Sourceplay=True
        for _ in range(12): yield
        checks['play_advances'] = float(np.mean(np.abs(seek-_pixels(reader))))>1e-4
        demo.par.Sourceplay=False; demo.par.Sourcerestart.pulse()
        for _ in range(4): yield
        checks['restart_returns_to_seek'] = np.allclose(seek,_pixels(reader),atol=.002)
        demo.par.Sourcein=3.7
        for _ in range(4): yield
        checks['loop_wraps_seek'] = np.allclose(seek,_pixels(reader),atol=.002)
        demo.par.Sourceloop=False; demo.par.Sourcein=10000.
        for _ in range(4): yield
        end=_pixels(reader); demo.par.Sourcein=20000.
        for _ in range(4): yield
        checks['loop_off_holds_end'] = np.allclose(end,_pixels(reader),atol=.002) and not np.allclose(end,zero,atol=.002)
        demo.par.Sourceloop=True; demo.par.Sourcein=1.5; demo.par.Sourcespeed=-1.; demo.par.Sourcerestart.pulse()
        for _ in range(4): yield
        reverse_start=float(reader.index)
        demo.par.Sourceplay=True
        for _ in range(8): yield
        checks['reverse_moves_backward'] = float(reader.index)<reverse_start
        demo.par.Sourceplay=False; demo.par.Sourcefile=''
        for _ in range(3): yield
        checks['clear_returns_to_test_pattern'] = demo.op('source_media_runtime').module.selected(demo)==0
        # Confirm cue media cannot inherit this separate designer file.
        show=host.copy(op('/project1/imagefx_demo/show_control'),name='show_qa')
        show.initializeExtensions(); show.op('show_tick').par.active=False
        show.op('deck_template').par.Sourcefile=str(image_path)
        show.op('deck_template').par.Sourcemode='file'
        deck=show.ext.ShowControlExt._new_deck('cue_qa')
        checks['cue_isolation'] = not deck.par.Sourcefile.eval() and deck.par.Sourcemode.eval()=='demo' and deck.fetch('imagefx_show_runtime',False)
        checks['cue_controls_explain_routing'] = 'Cue Editor' in deck.par.Sourcestatus.eval() and not deck.par.Sourcefile.enable
    sequence=steps()
    def finish():
        _finish_report(report,REPORT.with_name('source-media-deferred.json'))
        host.destroy()
        print('Source Media deferred:',report)
    def advance():
        try:
            _pixels(source)
            next(sequence)
        except StopIteration: finish()
        except Exception: report['error']=traceback.format_exc(); finish()
        else: run('args[0]()',advance,delayFrames=1)
    run('args[0]()',advance,delayFrames=1)


if __name__=='__main__': print(validate())
