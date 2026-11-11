"""Off-air large-show load/save round trip; never writes the user's show JSON."""
import copy
import hashlib
import json
from pathlib import Path
import runpy
import traceback
import uuid

ROOT = Path(__file__).resolve().parents[2]


def validate(patch=False):
    import td
    from tdimagefx.jsonutil import atomic_write_json, load_json
    original = td.op('/project1/imagefx_demo/show_control')
    current = original.ext.ShowControlExt
    if current.engine.state != 'stopped' or current._look_edit is not None:
        raise RuntimeError('Stop All and finish Look Editor before validation')
    if td.op('/project1/imagefx_sandbox') is not None:
        raise RuntimeError('Sandbox already exists')
    source = ROOT / '.imagefx/shows/current.json'
    before_hash = hashlib.sha256(source.read_bytes()).hexdigest() if source.is_file() else None
    before = copy.deepcopy(current.document)
    folder = ROOT / 'build/show-file-limits'
    folder.mkdir(parents=True, exist_ok=True)
    task = 'show-file-limits-' + uuid.uuid4().hex[:8]
    fixture = ROOT / 'build/task-artifacts' / task / 'fixtures/large-show.json'
    fixture.parent.mkdir(parents=True, exist_ok=True)
    base = td.op('/project1').create(td.baseCOMP, 'imagefx_sandbox')
    report = dict(ok=False, checks={}, task=task, hardware_outputs_opened=False)

    def check(name, value):
        report['checks'][name] = bool(value)
        if not value:
            raise AssertionError(name)

    try:
        base.copy(original.parent().op('wall_output'), name='wall_output')
        host = base.copy(original, name='show_control')
        if patch:
            runpy.run_path(str(ROOT / 'touchdesigner/scripts/install_show_file_limits.py'))['install'](host)
        host.op('show_tick').par.active = False
        ext = host.ext.ShowControlExt
        check('show_budget_64_mib', ext.model.MAX_SHOW_BYTES == 64 * 1024 * 1024)
        # A clean checkout must not need the operator's private show to run QA.
        cue = dict(ext.model.new_cue(), name='Synthetic large-show fixture',
                   look=ext._capture_look(original.parent()))
        document = ext.model.validate_show(dict(kind=ext.model.SHOW_KIND,
                                               schema_version=1, cues=[cue], mapping={}))
        largest = max(document['cues'], key=lambda cue: len(json.dumps(cue)))
        # Real complete cue looks, not embedded media or an unvalidated filler field.
        while len(json.dumps(document, indent=2).encode('utf-8')) < 9 * 1024 * 1024:
            cue = copy.deepcopy(largest)
            cue['id'] = ext.model.new_cue()['id']
            document['cues'].append(cue)
            if len(document['cues']) > ext.model.MAX_CUES:
                raise RuntimeError('Fixture exceeded cue budget')
        document = ext.model.validate_show(document)
        atomic_write_json(fixture, document)
        report.update(test_bytes=fixture.stat().st_size, test_cues=len(document['cues']), patched=patch)
        check('fixture_exceeds_old_8_mib_limit', fixture.stat().st_size > 8 * 1024 * 1024)
        fixture_hash = hashlib.sha256(fixture.read_bytes()).hexdigest()
        host.par.Showfile = str(fixture)
        ext.LoadShow()
        check('large_show_loads', ext.document == document)
        check('load_does_not_rewrite_source', hashlib.sha256(fixture.read_bytes()).hexdigest() == fixture_hash)
        check('load_keeps_blackout_on_and_audio_off', bool(host.par.Masterblackout) and not bool(host.par.Audioenabled))
        previous_backups = set(fixture.parent.glob('large-show.backup-*.json'))
        ext.SaveShow()
        backups = list(set(fixture.parent.glob('large-show.backup-*.json')) - previous_backups)
        check('large_show_saves_and_creates_backup', len(backups) == 1)
        check('backup_preserves_all_cues', load_json(backups[0], max_bytes=ext.model.MAX_SHOW_BYTES) == document)
        saved = copy.deepcopy(ext.document)
        check('saved_file_stays_larger_than_old_limit', fixture.stat().st_size > 8 * 1024 * 1024)
        ext.LoadShow()
        check('saved_large_show_reloads_without_data_loss', ext.document == saved)
        check('no_native_errors_or_warnings', not host.errors(recurse=True) and not host.warnings(recurse=True))
    except Exception:
        report['error'] = traceback.format_exc()
    finally:
        base.destroy()
        check('main_cues_unchanged', original.ext.ShowControlExt.document == before)
        after_hash = hashlib.sha256(source.read_bytes()).hexdigest() if source.is_file() else None
        check('user_show_json_unchanged', after_hash == before_hash)
        check('sandbox_removed', td.op('/project1/imagefx_sandbox') is None)
        report['ok'] = not report.get('error') and all(report['checks'].values())
        (folder / 'native-validation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report
