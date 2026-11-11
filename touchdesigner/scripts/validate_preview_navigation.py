"""Focused native UI regression; keeps cues, live draft, and outputs untouched.

Run as a Text DAT module with start(project_root). Complete the visible window
resize/dropdown smoke test separately: parameter values cannot prove UI redraw.
"""
import json
from pathlib import Path
import traceback

RUN = {}


def start(root):
    if RUN:
        raise ValueError('Validation already running')
    RUN.update(root=Path(root), generator=validate())
    advance()


def advance():
    try:
        next(RUN['generator'])
        run("op({!r}).module.advance()".format(me.path), delayFrames=2)
    except StopIteration:
        RUN.clear()


def validate():
    show = op('/project1/imagefx_demo/show_control')
    ext = show.ext.ShowControlExt
    nav, inspector = show.op('inspector_navigation'), show.op('cue_inspector')
    selected = nav.par.Section.eval()
    before = show.op('show_data').text
    main_look = ext._capture_look(show.parent())
    draft = ext._look_edit
    draft_look = ext._capture_look(draft['deck']) if draft else None
    state = ext.engine.state
    outputs = show.op('show_output_mode').module.windows(show)
    output_states = [bool(w.isOpen) for w in outputs if w is not None]
    checks, error = {}, None

    def check(name, value):
        checks[name] = bool(value)
        assert value, name

    try:
        callback = show.op('inspector_navigation_callbacks')
        check('native_valuechange_callback', callback is not None and callback.par.active
              and callback.par.valuechange and callback.par.pars.eval() == 'Section')
        check('callback_watches_navigation', callback.par.op.eval() == nav)
        for section in nav.par.Section.menuNames:
            nav.par.Section = section
            yield
            check('scope/' + section, inspector.par.pagescope.eval() == repr(section))
            check('refresh/' + section, inspector.par.op.eval() == show
                  and inspector.par.pagescope.mode == ParMode.CONSTANT)
            check('defined/' + section, any(p.name == section and p.pars for p in show.customPages))
        check('tabs_hidden', not inspector.par.pagenames)
        check('not_synced_to_unrelated_parameter_windows', not inspector.par.syncpage)

        window = show.op('look_preview_window')
        display, preview = show.op('look_preview_display'), show.op('look_preview')
        display.cook(force=True); preview.cook(force=True)
        check('stable_preview_source', display.par.top.eval() == preview)
        check('dedicated_window_source', window.par.winop.eval() == display)
        check('aspect_fit', display.par.fillmode.eval() == 'best')
        check('inline_preview_aspect_fit', show.op('look_preview_panel').par.topfill.eval() == 'best')
        check('preview_stays_in_front', bool(window.par.alwaysontop))
        check('no_pan_zoom', not window.par.interact)
        check('borders_for_resizing', bool(window.par.borders))
        check('operator_display_only', window.par.justifyoffsetto.eval() == 'primarydisplay')
        check('not_an_audience_output', window not in outputs)
        check('not_perform_window', not window.par.includedialog)
        check('preview_keeps_render_resolution', (display.width, display.height) == (preview.width, preview.height))
        check('native_pixel_passthrough', (display.numpyArray(delayed=False) == preview.numpyArray(delayed=False)).all())
        check('no_native_errors', not show.errors(recurse=True))
    except Exception:
        error = traceback.format_exc()
    finally:
        nav.par.Section = selected
        yield
    checks['show_document_preserved'] = before == show.op('show_data').text
    checks['main_look_preserved'] = main_look == ext._capture_look(show.parent())
    checks['draft_preserved'] = draft is ext._look_edit and (draft is None or draft_look == ext._capture_look(draft['deck']))
    checks['playback_preserved'] = state == ext.engine.state
    checks['audience_windows_preserved'] = output_states == [bool(w.isOpen) for w in outputs if w is not None]
    report = dict(ok=error is None and all(checks.values()), checks=checks, error=error)
    path = RUN['root'] / 'build/envoy-validation/preview-navigation.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print('PREVIEW / NAVIGATION:', report['ok'], len(checks), error)
