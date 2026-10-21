"""Off-air pixel and UI wiring checks for the complete 2x2 wall preview."""
import copy
import json
import traceback
from datetime import datetime, timezone
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[2]


def validate(write_report=True):
    original = op('/project1/imagefx_demo/show_control')
    document = copy.deepcopy(original.ext.ShowControlExt.document)
    host = op('/project1').create(baseCOMP, 'projector_review_qa')
    wall = host.copy(original.parent().op('wall_output'), name='wall_output')
    show = host.copy(original, name='show_control')
    show.op('show_tick').par.active = False
    runtime = show.op('show_review_export').module
    checks = {}
    report = dict(ok=False, generated_at=datetime.now(timezone.utc).isoformat(), hardware_output_tested=False)
    try:
        wall.par.Sourcemode, wall.par.Blackout, wall.par.Enabled = 'independent', False, True
        wall.par.Testpattern, wall.par.Monitorenabled = False, True
        for i, color in enumerate(((1, 0, 0), (0, 1, 0), (0, 0, 1)), 1):
            source = host.create(constantTOP, 'source{}'.format(i))
            source.par.colorr, source.par.colorg, source.par.colorb = color
            source.par.outputresolution = 'custom'
            source.par.resolutionw, source.par.resolutionh = 1920, 1080
            wall.par['Projector{}top'.format(i)] = '../source{}'.format(i)
        def pixels():
            node = show.op('review_selected')
            node.cook(force=True)
            return np.array(node.numpyArray(delayed=False), copy=True)
        show.par.Outputmode, show.par.Reviewprojector = 'wall', 'wall'
        checks['full_canvas_target'] = runtime.review_target(show) == wall.op('out1_wall_4k')
        a = pixels()
        h, w = a.shape[:2]
        checks['aspect_16_by_9'] = abs(w / h - 16 / 9) < .01
        checks['bounded_thumbnail'] = w <= 880 and h <= 165
        for name, x, y, color in (
            ('top_left_p1', w//4, 3*h//4, (1, 0, 0)),
            ('top_right_p2', 3*w//4, 3*h//4, (0, 1, 0)),
            ('bottom_left_p3', w//4, h//4, (0, 0, 1)),
        ):
            checks[name] = bool(np.allclose(a[y, x, :3], color, atol=.01))
        checks['bottom_right_confidence_visible'] = bool(np.any(a[:h//2, w//2:, :3] > .1))
        wall.par.Monitorenabled = False
        a = pixels()
        checks['confidence_toggle_in_actual_canvas'] = bool(np.max(a[:h//2-2, w//2+2:, :3]) == 0)
        wall.par.Monitorenabled = True
        wall.par.Blackout = True
        a = pixels()
        checks['projector_blackout_visible'] = all(np.max(a[y, x, :3]) == 0 for x, y in ((w//4,3*h//4),(3*w//4,3*h//4),(w//4,h//4)))
        checks['confidence_survives_projector_blackout'] = bool(np.any(a[:h//2,w//2:,:3] > .1))
        for view in ('auto', 'all', 'wall', '1', '2', '3', 'confidence'):
            show.par.Reviewprojector = view
            a = pixels()
            checks['menu_' + view] = bool(np.isfinite(a).all()) and not show.op('review_selected').errors()
            checks['panel_' + view] = (int(show.op('projector_review_panel').par.w) == a.shape[1]
                                        and int(show.op('projector_review_panel').par.h) == a.shape[0])
        show.par.Reviewprojector = 'confidence'
        checks['confidence_target'] = runtime.review_target(show) == wall.op('comp_monitor_out')
        show.par.Reviewprojector = 'auto'
        show.par.Outputmode = 'direct'
        checks['auto_direct_three_up'] = runtime.review_target(show) == show.op('projector_review')
        show.par.Outputmode = 'wall'
        checks['auto_wall_complete_canvas'] = runtime.review_target(show) == wall.op('out1_wall_4k')
        show.par.Reviewprojector = 'wall'
        before = copy.deepcopy(show.ext.ShowControlExt.document)
        path = ROOT / 'touchdesigner/scripts/show_review_export.py'
        scope = dict(globals(), __file__=str(path), __name__='_review_reinstall')
        exec(compile(path.read_text(encoding='utf-8'), str(path), 'exec'), scope)
        count = len(show.customPars)
        scope['install'](show)
        checks['reinstall_preserves_view'] = show.par.Reviewprojector == 'wall'
        checks['reinstall_updates_menu'] = show.par.Reviewprojector.menuNames == [x[0] for x in runtime.REVIEW_VIEWS]
        checks['no_duplicate_parameters'] = len(show.customPars) == count
        checks['reinstall_keeps_mapping_tab'] = "'Projection Mapping'" in show.op('cue_inspector').par.pagescope.eval()
        checks['cues_unchanged'] = show.ext.ShowControlExt.document == before and original.ext.ShowControlExt.document == document
        checks['no_output_windows_opened'] = not any(n is not None and n.isOpen for n in runtime._export_windows(show))
        checks['no_operator_errors'] = not show.errors(recurse=True)
        report['ok'] = all(checks.values())
    except Exception:
        report['error'] = traceback.format_exc()
    finally:
        report['checks'] = checks
        host.destroy()
    if write_report:
        path = ROOT / 'build/envoy-validation/projector-review.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report


if __name__ == '__main__':
    print(validate())
