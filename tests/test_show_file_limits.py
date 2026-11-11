"""Large cue shows retain strict validation, backups and a bounded file budget."""
import copy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from tdimagefx import show
from tdimagefx.errors import ValidationError
from tdimagefx.jsonutil import load_json
from touchdesigner.extensions.ShowControlExt import ShowControlExt


class ShowFileLimitTests(unittest.TestCase):
    def extension(self, path):
        ext = ShowControlExt.__new__(ShowControlExt)
        ext.model = show
        ext.document = show.validate_show(dict(kind=show.SHOW_KIND, schema_version=1,
                                                cues=[show.new_cue()], mapping={}))
        ext.ownerComp = SimpleNamespace(customPars=[], par=SimpleNamespace(), op=lambda name: None)
        ext._p = lambda name: str(path)
        ext._guard_edit = Mock()
        ext._guard_no_look_edit = Mock()
        ext._mapping_matrices = Mock()
        ext._replace_cues = Mock()
        ext._save_document_dat = Mock()
        ext.SelectCue = Mock()
        ext.UpdateMapping = Mock()
        ext._status = Mock()
        return ext

    def test_show_budget_is_64_mib_and_boundary_is_inclusive(self):
        self.assertEqual(show.MAX_SHOW_BYTES, 64 * 1024 * 1024)
        show.check_show_size(show.MAX_SHOW_BYTES)
        with self.assertRaisesRegex(ValueError, 'exceeds 64 MiB'):
            show.check_show_size(show.MAX_SHOW_BYTES + 1)

    def test_serialized_budget_matches_saved_utf8_format(self):
        ext = self.extension('unused.json')
        ext.document['cues'][0]['notes'] = '舞台'
        payload = (json.dumps(ext.document, indent=2, sort_keys=True, ensure_ascii=False) + '\n').encode('utf-8')
        before = copy.deepcopy(ext.document)
        with patch.object(show, 'MAX_SHOW_BYTES', len(payload)):
            self.assertEqual(ext._validated_cues(ext.document['cues']), before)
        with patch.object(show, 'MAX_SHOW_BYTES', len(payload) - 1):
            with self.assertRaises(ValueError):
                ext._validated_cues(ext.document['cues'])
        self.assertEqual(ext.document, before)

    def test_load_show_larger_than_old_limit_preserves_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).resolve() / 'large.json'
            ext = self.extension(path)
            payload = json.dumps(ext.document).encode() + b' ' * (8 * 1024 * 1024)
            path.write_bytes(payload)
            ext.LoadShow()
            self.assertEqual(path.read_bytes(), payload)
            self.assertEqual(ext.document['cues'][0]['id'], ext._replace_cues.call_args.args[0][0]['id'])
            self.assertTrue(ext.ownerComp.par.Masterblackout)
            self.assertFalse(ext.ownerComp.par.Audioenabled)

    def test_save_over_large_old_show_creates_valid_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).resolve() / 'large.json'
            ext = self.extension(path)
            original = copy.deepcopy(ext.document)
            path.write_bytes(json.dumps(original).encode() + b' ' * (8 * 1024 * 1024))
            ext.document['cues'][0]['name'] = 'Updated'
            ext.SaveShow()
            backups = list(path.parent.glob('large.backup-*.json'))
            self.assertEqual(len(backups), 1)
            self.assertEqual(load_json(backups[0]), original)
            self.assertEqual(load_json(path)['cues'][0]['name'], 'Updated')

    def test_oversized_load_does_not_replace_current_cues(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).resolve() / 'oversized.json'
            path.write_bytes(b' ' * 1025)
            ext = self.extension(path)
            before = copy.deepcopy(ext.document)
            with patch.object(show, 'MAX_SHOW_BYTES', 1024):
                with self.assertRaisesRegex(ValueError, 'Show file exceeds'):
                    ext.LoadShow()
            self.assertEqual(ext.document, before)
            ext._replace_cues.assert_not_called()

    def test_rejected_save_leaves_existing_file_and_no_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).resolve() / 'show.json'
            ext = self.extension(path)
            original = json.dumps(ext.document).encode()
            path.write_bytes(original)
            with patch.object(show, 'MAX_SHOW_BYTES', len(original)):
                with self.assertRaises(ValueError):
                    ext.SaveShow()
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(list(path.parent.glob('*.backup-*.json')), [])

    def test_large_show_still_rejects_duplicate_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).resolve() / 'invalid.json'
            path.write_bytes(b'{"kind":"tdimagefx.show","kind":"duplicate"}' + b' ' * (8 * 1024 * 1024))
            ext = self.extension(path)
            with self.assertRaisesRegex(ValidationError, 'duplicate JSON object key'):
                ext.LoadShow()
            ext._replace_cues.assert_not_called()

    def test_generic_json_budget_is_not_relaxed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory).resolve() / 'other.json'
            path.write_bytes(b'{}' + b' ' * (8 * 1024 * 1024))
            with self.assertRaisesRegex(ValidationError, 'byte limit'):
                load_json(path)


if __name__ == '__main__':
    unittest.main()
