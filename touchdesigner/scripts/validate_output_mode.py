"""Off-air native Output Mode checks. Never opens any physical output."""
import copy
import json
import traceback
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _panorama_checks(show, wall, checks):
    """Check shared-cue slicing on the actual mapped and packed output graph."""
    import numpy as np
    ext = show.ext.ShowControlExt
    for alias, target in (('Outputlayout','Routingmode'), ('Outputsharedtrack','Sharedtrack'),
                          ('Outputpanelwidth','Renderwidth'), ('Outputpanelheight','Renderheight'),
                          ('Outputoverlap','Panoramaoverlap'), ('Outputmediafit','Cuemediafit')):
        checks['canvas_binding_' + alias] = show.par[alias].bindMaster == show.par[target]
    show.par.Outputlayout = 'panoramic'
    show.par.Outputsharedtrack = 2
    show.par.Outputpanelwidth, show.par.Outputpanelheight = 1920, 1080
    show.par.Outputoverlap = 0
    show.par.Masterblackout = False
    for i in (1, 2, 3):
        show.par['Output{}width'.format(i)], show.par['Output{}height'.format(i)] = 1920, 1080
    code = show.create(textDAT, 'panorama_test_code')
    code.text = ('layout(location=0) out vec4 fragColor; void main(){'
                 'vec3 c=vUV.x<1./3.?vec3(1,0,0):vUV.x<2./3.?vec3(0,1,0):vec3(0,0,1);'
                 'fragColor=TDOutputSwizzle(vec4(c,1));}')
    source = show.create(glslTOP, 'panorama_test')
    source.par.pixeldat, source.par.outputresolution = 'panorama_test_code', 'custom'
    source.par.resolutionw, source.par.resolutionh = 5760, 1080
    show.op('track2_source0').par.top = source.path
    show.par.Track2visible, show.par.Track2blend, show.par.Track2level = True, 0, 1
    wall.par.Sourcemode, wall.par.Blackout, wall.par.Enabled = 'show', False, True
    wall.par.Testpattern, wall.par.Monitorenabled = False, True
    ext.UpdateMapping()

    def pixels(top):
        top.cook(force=True)
        result = top.numpyArray(delayed=False)
        assert result is not None and np.isfinite(result).all() and not top.errors(), top.path
        return result.copy()

    colors = np.eye(3)
    for delivery in ('direct', 'wall'):
        show.par.Outputmode = delivery
        checks['panorama_summary_' + delivery] = '5760 x 1080 panorama | Track 2' in show.par.Outputcanvas.eval()
        feeds = [pixels(show.op('out{}_projector'.format(i))) for i in (1, 2, 3)]
        checks['panorama_mapped_dimensions_' + delivery] = all(a.shape == (1080,1920,4) for a in feeds)
        for i, a in enumerate(feeds):
            checks['panorama_slice_{}_{}'.format(delivery,i+1)] = bool(np.allclose(a[:,:,:3], colors[i], atol=.005))
        packed = pixels(wall.op('out1_wall_4k'))
        checks['panorama_4k_pack_' + delivery] = packed.shape == (2160,3840,4)
        for i, tile in enumerate((packed[1080:,:1920], packed[1080:,1920:], packed[:1080,:1920])):
            checks['panorama_wall_tile_{}_{}'.format(delivery,i+1)] = bool(np.allclose(tile[:,:,:3], feeds[i][:,:,:3], atol=.005))
        checks['panorama_confidence_' + delivery] = np.array_equal(packed[:1080,1920:], pixels(wall.op('comp_monitor_out')))
    for track in (1, 3):
        show.par.Sharedtrack = track
        checks['panorama_shared_track_' + str(track)] = all(ext.OutputTrack(i) == track for i in (1,2,3))
    show.par.Sharedtrack = 2
    show.par.Panoramaoverlap = .25
    ext.UpdateMapping()
    checks['panorama_overlap_width'] = '4800 x 1080' in show.par.Outputcanvas.eval()
    checks['panorama_overlap_intervals'] = all(
        abs(float(show.op('mapped%d' % i).par.vec3valuex) - (i-1)*.3) < 1e-6
        and abs(float(show.op('mapped%d' % i).par.vec3valuez) - ((i-1)*.3+.4)) < 1e-6 for i in (1,2,3))
    show.par.Routingmode = 'identical'
    ext.UpdateMapping()
    checks['identical_remains_available'] = np.array_equal(pixels(show.op('mapped1')), pixels(show.op('mapped3')))
    show.par.Routingmode = 'independent'
    checks['independent_remains_available'] = [ext.OutputTrack(i) for i in (1,2,3)] == [1,2,3]

    # Exercise a genuine cue, not just synthetic inputs. Preload at panel size,
    # switch layout before GO, then resize a playing deck without replacing it.
    ext.Stopall()
    show.par.Renderwidth, show.par.Renderheight = 320, 180
    show.par.Panoramaoverlap = 0
    cue = dict(ext.model.new_cue(), name='Panorama QA', track=2, fade=0, duration=0)
    ext._replace_cues([cue])
    ext.prepare(cue)
    for _ in range(500):
        for item in ext.prepared.values():
            if 'warm_frame' in item: item['warm_frame'] = absTime.frame - 1
        ext._service_preloads()
        if not any(item.get('loading') for item in ext.prepared.values()): break
    item = ext.prepared[cue['id']]
    checks['panorama_real_cue_prepared'] = not item.get('loading') and not item.get('error')
    show.par.Routingmode = 'panoramic'
    ext.UpdateMapping()
    deck = item['deck']
    checks['panorama_standby_resize'] = int(deck.par.Customwidth) == 960
    ext.engine.go(0)
    ext.engine.tick()
    current = ext.tracks[2]
    before = (current['deck'].id, current.get('started'), copy.deepcopy(current['cue']))
    show.par.Renderwidth = 640
    ext.UpdateMapping()
    checks['panorama_live_resize'] = int(deck.par.Customwidth) == 1920
    checks['panorama_live_identity_and_time_preserved'] = before == (current['deck'].id, current.get('started'), current['cue'])
    checks['panorama_cue_errors_empty'] = not ext.engine.errors
    # A circle must remain circular when a 16:9 source fills the wide canvas.
    # This exercises the actual cue-media shader, not just the portable formula.
    show.par.Renderwidth = 320
    ext.UpdateMapping()
    media_code = deck.create(textDAT, 'aspect_test_code')
    media_code.text = ('layout(location=0) out vec4 fragColor; void main(){'
        'vec2 p=(vUV.xy-.5)*vec2(320,180); float d=length(p);'
        'fragColor=TDOutputSwizzle(d<20.?vec4(1,1,1,.65):vec4(.1,.2,.3,1));}')
    media = deck.create(glslTOP, 'aspect_test_source')
    media.par.pixeldat, media.par.outputresolution = 'aspect_test_code', 'custom'
    media.par.resolutionw, media.par.resolutionh = 320,180
    fitted = show.op('show_output_mode').module.fit_cue_media(show,deck,media)
    deck.op('source_image').par.index = 1
    for mode, expected in (('auto',(120,120)), ('cover',(120,120)), ('contain',(40,40)), ('stretch',(120,40))):
        show.par.Outputmediafit = mode
        a = pixels(fitted)
        ys,xs = np.where(a[:,:,0] > .8)
        bounds = (int(xs.max()-xs.min()+1), int(ys.max()-ys.min()+1))
        checks['cue_media_shape_' + mode] = all(abs(v-e)<=3 for v,e in zip(bounds,expected))
        checks['cue_media_dimensions_' + mode] = a.shape == (180,960,4)
        checks['cue_media_alpha_' + mode] = abs(float(a[90,480,3])-.65)<.01
        if mode in ('auto','cover'):
            checks['cue_media_fill_no_bars_' + mode] = bool(np.allclose(a[0,0,:3], [.1,.2,.3], atol=.01))
        checks['cue_media_switch_' + mode] = np.allclose(pixels(deck.op('source_image')),a,atol=.005)
    show.par.Outputmediafit = 'auto'
    reader_id, fitted_id = media.id, fitted.id
    show.par.Routingmode = 'independent'
    ext.UpdateMapping()
    a = pixels(fitted)
    checks['cue_media_auto_normal_canvas'] = a.shape == (180,320,4) and fitted.par.vec0valuex.eval() == 0
    show.par.Routingmode = 'panoramic'
    ext.UpdateMapping()
    checks['cue_media_resize_preserves_nodes'] = media.id == reader_id and fitted.id == fitted_id
    checks['cue_media_auto_panorama_restored'] = pixels(fitted).shape == (180,960,4) and fitted.par.vec0valuex.eval() == 1
    ext.Stopall()
    ext.SelectCue(1)
    ext.RecallLook()
    checks['panorama_recall_wide'] = int(ext._look_edit['deck'].par.Customwidth) == 960
    show.par.Renderwidth = 320
    ext.UpdateMapping()
    checks['panorama_draft_resize'] = int(ext._look_edit['deck'].par.Customwidth) == 960
    ext.CancelLook()
    show.par.Outputmediafit = 'cover'
    path = (ROOT / 'build/envoy-validation/panorama-show.json').resolve()
    show.par.Showfile = str(path)
    ext.SaveShow()
    saved = json.loads(path.read_text(encoding='utf-8'))
    checks['panorama_show_saved'] = saved['mapping']['Routingmode'] == 'panoramic' and saved['mapping']['Sharedtrack'] == 2
    checks['canvas_media_fit_saved'] = saved['mapping']['Cuemediafit'] == 'cover'
    show.par.Routingmode, show.par.Sharedtrack = 'independent', 1
    show.par.Outputmediafit = 'stretch'
    ext.LoadShow()
    checks['panorama_show_loaded'] = show.par.Routingmode == 'panoramic' and int(show.par.Sharedtrack) == 2
    checks['canvas_media_fit_loaded'] = show.par.Cuemediafit == 'cover' and show.par.Outputmediafit == 'cover'
    checks['panorama_load_safe'] = bool(show.par.Masterblackout) and not show.par.Audioenabled
    checks['panorama_no_physical_windows'] = not any(w.isOpen for w in show.op('show_output_mode').module.windows(show) if w)
    wall.par.Blackout = True


def validate(write_report=True):
    original = op('/project1/imagefx_demo/show_control')
    document = copy.deepcopy(original.ext.ShowControlExt.document)
    host = op('/project1').create(baseCOMP, 'output_mode_qa')
    wall = host.copy(original.parent().op('wall_output'), name='wall_output')
    show = host.copy(original, name='show_control')
    show.op('show_tick').par.active = False
    runtime = show.op('show_output_mode').module
    checks = {}
    report = dict(ok=False, generated_at=datetime.now(timezone.utc).isoformat(), hardware_output_tested=False)
    try:
        checks['default_wall_mode'] = show.par.Outputmode.eval() == 'wall'
        checks['two_clear_mode_labels'] = list(show.par.Outputmode.menuNames) == ['direct', 'wall']
        checks['output_page_second'] = [p.name for p in show.customPages][:2] == ['Transport', 'Output Mode']
        nav=show.op('inspector_navigation')
        checks['output_page_visible'] = ('Output Mode' in nav.par.Section.menuNames if nav is not None else "'Output Mode'" in show.op('cue_inspector').par.pagescope.eval())
        checks['master_blackout_alias'] = show.par.Outputblackout.bindMaster == show.par.Masterblackout
        checks['processor_display_alias'] = show.par.Outputwalldisplay.bindMaster == wall.par.Displayindex
        checks['wall_blackout_alias'] = show.par.Outputwallblackout.bindMaster == wall.par.Blackout
        for selected in ('direct', 'wall'):
            show.par.Outputmode = selected
            checks['review_follows_' + selected] = show.par.Reviewroute.eval() == ('atlas' if selected == 'direct' else 'wall')
            checks['mode_description_' + selected] = bool(show.par.Outputsummary.eval())
            checks['direct_settings_enabled_' + selected] = bool(show.par.Directdisplay1.enable) == (selected == 'direct')
            checks['wall_settings_enabled_' + selected] = bool(show.par.Outputwalldisplay.enable) == (selected == 'wall')
        checks['review_route_readonly'] = show.par.Reviewroute.readOnly
        show.par.Outputmode = 'direct'
        for i in (1, 2, 3):
            w = show.op('direct_window{}'.format(i))
            checks['direct_feed_' + str(i)] = w.par.winop.eval() == show.op('out{}_projector'.format(i))
            checks['window_native_fill_' + str(i)] = w.par.size == 'fill' and w.par.dpiscaling == 'native' and not w.par.borders
            for value in (-1, 0, 31):
                show.par['Directdisplay{}'.format(i)] = value
                checks['display_{}_{}'.format(i, value)] = w.par.display.eval() == max(0, value)
            show.par['Directdisplay{}'.format(i)] = -1
            for width, height in ((1920, 1080), (3840, 2160), (1280, 720)):
                show.par['Output{}width'.format(i)] = width
                show.par['Output{}height'.format(i)] = height
                feed = show.op('out{}_projector'.format(i))
                feed.cook(force=True)
                checks['resolution_{}_{}'.format(i, width)] = (feed.width, feed.height) == (width, height)
        for action in ('Checkoutput', 'Openoutput'):
            checks['unassigned_direct_' + action] = runtime.on_pulse(show, action) is False
        show.par.Outputmode = 'wall'
        wall.par.Displayindex = -1
        for action in ('Checkoutput', 'Openoutput'):
            checks['unassigned_wall_' + action] = runtime.on_pulse(show, action) is False
        checks['close_all_dispatch'] = runtime.on_pulse(show, 'Closealloutputs') is True
        checks['all_windows_closed'] = not any(w is not None and w.isOpen for w in runtime.windows(show))
        checks['blackouts_preserved'] = bool(show.par.Masterblackout) and bool(wall.par.Blackout)
        before = copy.deepcopy(show.ext.ShowControlExt.document)
        path = ROOT / 'touchdesigner/scripts/show_output_mode.py'
        scope = dict(globals(), __file__=str(path), __name__='_output_reinstall')
        exec(compile(path.read_text(encoding='utf-8'), str(path), 'exec'), scope)
        count = len(show.customPars)
        scope['install'](show)
        checks['reinstall_no_duplicate_parameters'] = len(show.customPars) == count
        checks['reinstall_preserves_cues'] = show.ext.ShowControlExt.document == before
        _panorama_checks(show, wall, checks)
        checks['original_cues_untouched'] = original.ext.ShowControlExt.document == document
        checks['no_operator_errors'] = not show.errors(recurse=True)
        report['ok'] = all(checks.values())
    except Exception:
        report['error'] = traceback.format_exc()
    finally:
        report['checks'] = checks
        host.destroy()
    if write_report:
        target = ROOT / 'build/envoy-validation/output-mode.json'
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report


def validate_deferred():
    """Exercise real parameter/pulse events over TD frames, no window opens."""
    original = op('/project1/imagefx_demo/show_control')
    host = op('/project1').create(baseCOMP, 'output_mode_events_qa')
    wall = host.copy(original.parent().op('wall_output'), name='wall_output')
    show = host.copy(original, name='show_control')
    show.op('show_tick').par.active = False
    runtime = show.op('show_output_mode').module
    checks, closes, pulses = {}, [], []
    close = runtime.close_all
    dispatch = runtime.on_pulse
    def record_close(owner):
        closes.append(owner.path)
        return close(owner)
    def record_pulse(owner, name):
        pulses.append(name)
        return dispatch(owner, name)
    runtime.close_all, runtime.on_pulse = record_close, record_pulse
    report = dict(ok=False, generated_at=datetime.now(timezone.utc).isoformat(), hardware_output_tested=False)
    def events():
        yield
        yield
        closes.clear(); pulses.clear()
        show.par.Outputmode = 'direct'
        yield
        checks['mode_event_closes_once'] = len(closes) == 1
        checks['review_updates_on_mode_event'] = show.par.Reviewroute == 'atlas'
        closes.clear()
        show.par.Outputlayout = 'panoramic'
        yield
        checks['canvas_alias_updates_master'] = show.par.Routingmode == 'panoramic'
        checks['canvas_change_closes_once'] = len(closes) == 1
        closes.clear()
        show.par.Outputsharedtrack = 3
        yield
        checks['shared_alias_updates_master'] = int(show.par.Sharedtrack) == 3
        checks['shared_track_change_closes_once'] = len(closes) == 1
        closes.clear()
        show.par.Routingmode = 'identical'
        yield
        checks['master_updates_canvas_alias'] = show.par.Outputlayout == 'identical'
        checks['routing_change_closes_once'] = len(closes) == 1
        closes.clear()
        show.par.Outputmediafit = 'cover'
        yield
        checks['media_fit_alias_updates_master'] = show.par.Cuemediafit == 'cover'
        checks['media_fit_change_closes_once'] = len(closes) == 1
        closes.clear()
        show.par.Cuemediafit = 'contain'
        yield
        checks['media_fit_master_updates_alias'] = show.par.Outputmediafit == 'contain'
        checks['media_fit_master_closes_once'] = len(closes) == 1
        closes.clear()
        show.par.Directdisplay1 = 31
        yield
        checks['display_change_closes_once'] = len(closes) == 1
        show.par.Directdisplay1 = -1
        yield
        show.par.Openoutput.pulse()
        yield
        checks['direct_open_dispatched_once'] = pulses == ['Openoutput']
        checks['direct_invalid_stays_closed'] = show.par.Outputstatus.eval().startswith('NOT OPENED:')
        pulses.clear()
        show.par.Outputmode = 'wall'
        wall.par.Displayindex = -1
        yield
        show.par.Checkoutput.pulse()
        yield
        checks['check_dispatched_once'] = pulses == ['Checkoutput']
        pulses.clear()
        show.par.Openoutput.pulse()
        yield
        checks['wall_open_dispatched_once'] = pulses == ['Openoutput']
        checks['wall_invalid_stays_closed'] = show.par.Outputstatus.eval().startswith('NOT OPENED:')
        pulses.clear()
        show.par.Closealloutputs.pulse()
        yield
        checks['close_dispatched_once'] = pulses == ['Closealloutputs']
        checks['blackouts_unchanged'] = bool(show.par.Masterblackout) and bool(wall.par.Blackout)
        checks['no_window_opened'] = not any(w is not None and w.isOpen for w in runtime.windows(show))
        checks['no_callback_errors'] = not show.errors(recurse=True)
    sequence = events()
    def finish():
        report['checks'] = checks
        report['ok'] = not report.get('error') and all(checks.values())
        runtime.close_all, runtime.on_pulse = close, dispatch
        host.destroy()
        (ROOT / 'build/envoy-validation/output-mode-events.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print('OUTPUT MODE NATIVE EVENTS:', report)
    def advance():
        try:
            next(sequence)
        except StopIteration:
            finish()
        except Exception:
            report['error'] = traceback.format_exc()
            finish()
        else:
            run('args[0]()', advance, delayFrames=1)
    run('args[0]()', advance, delayFrames=1)


if __name__ == '__main__':
    print(validate())
