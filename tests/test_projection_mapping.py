from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import tempfile
import unittest

from touchdesigner.scripts import projection_mapping as mapping
from touchdesigner.scripts.build_show_control import MAPPING_SHADER


class Parameter:
    def __init__(self, value, default=None):
        self.val = value
        self.default = value if default is None else default
    def eval(self): return self.val
    def __bool__(self): return bool(self.val)
    def __float__(self): return float(self.val)
    def __eq__(self, other): return self.val == other


class Parameters(dict):
    def __getattr__(self, name): return self[name]


class ProjectionMappingTests(unittest.TestCase):
    def show(self, **changes):
        values = dict(Output1maskenabled=True, Output1maskshape='image',
                      Output1maskfile='', Libraryroot='.', Mappingstatus='Mapping valid')
        values.update(changes)
        return SimpleNamespace(par=Parameters({k:Parameter(v) for k,v in values.items()}), op=Mock(return_value=None))

    def test_shader_has_one_entrypoint(self):
        source = mapping.enhanced_shader(MAPPING_SHADER)
        self.assertEqual(source.count('void main()'), 1)
        self.assertIn('projectionMask(local)', source)

    def test_shader_keeps_legacy_crop_transform_and_safety(self):
        source = mapping.enhanced_shader(MAPPING_SHADER)
        for token in ('uRow2', 'uCrop.xy', 'uGrade.z', 'uTransform.y', 'uTransform.z'):
            self.assertIn(token, source)

    def test_mask_disabled_is_exact_unity(self):
        self.assertIn('if(uMask.x<.5) return 1.', mapping.SHADER_MASK)

    def test_missing_mask_rejects_before_inversion(self):
        self.assertLess(mapping.SHADER_MASK.index('if(uMaskstyle.w<.5) return 0.'),
                        mapping.SHADER_MASK.index('if(uMask.z>.5)'))

    def test_image_paths_are_strings_only(self):
        for value in (None, 2, True, {}, [], 'x\0.png', 'https://example.com/mask.png', 'x'*4097):
            with self.subTest(value=str(value)[:30]), self.assertRaises(ValueError):
                mapping.mask_file_value(value)

    def test_local_mask_path_is_preserved(self):
        for path in ('', 'assets/mask.png', 'C:/show/mask.png'):
            self.assertEqual(mapping.mask_file_value(path), path)

    def test_disabled_mask_does_not_load_file(self):
        self.assertEqual(mapping.mask_file(self.show(Output1maskenabled=False), 1), '')
        self.assertEqual(mapping.mask_file(self.show(Output1maskshape='rectangle'), 1), '')

    def test_relative_mask_resolves_against_library(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'mask.PNG'; path.touch()
            show=self.show(Libraryroot=folder, Output1maskfile='mask.PNG')
            self.assertEqual(mapping.mask_file(show, 1), str(path))

    def test_missing_or_unsupported_mask_is_unavailable(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'mask.mp4'; path.touch()
            for filename in ('missing.png', 'mask.mp4'):
                self.assertEqual(mapping.mask_file(self.show(Libraryroot=folder, Output1maskfile=filename), 1), '')

    def test_unavailable_mask_status_is_explicit(self):
        self.assertIn('MASK UNAVAILABLE', mapping.status(self.show(), 1))
        self.assertEqual(mapping.mask_source(self.show(),1),'black')

    def test_mask_status_off(self):
        self.assertEqual(mapping.status(self.show(Output1maskenabled=False),1),'Mapping valid | Mask off')

    def test_standalone_wall_has_identity_defaults(self):
        wall=SimpleNamespace(parent=lambda:SimpleNamespace(op=lambda path:None))
        self.assertEqual([mapping.wall_uniform(wall,1,3,i) for i in range(4)], [0,0,1,1])
        self.assertEqual(mapping.wall_uniform(wall,1,4,0),1)
        self.assertEqual(mapping.wall_uniform(wall,1,7,0),0)

    def test_unknown_action_does_nothing(self):
        self.assertFalse(mapping.on_pulse(None,'Gocue'))

    def test_preview_uses_final_route_without_opening_physical_output(self):
        runtime=SimpleNamespace(review_path=Mock(return_value='/mapped/projector2'))
        viewer=SimpleNamespace(openViewer=Mock())
        show=SimpleNamespace(par=Parameters(Mappingprojector=Parameter('2')),
                             op=lambda path:SimpleNamespace(module=runtime) if path=='show_review_export' else viewer)
        self.assertTrue(mapping.on_pulse(show,'Previewmapping'))
        runtime.review_path.assert_called_once_with(show,2)
        viewer.openViewer.assert_called_once_with()


class MappingResetTests(unittest.TestCase):
    def show(self):
        pars=Parameters(Mappingprojector=Parameter('2'),Showfile=Parameter('show.json'))
        for i in (1,2,3):
            for suffix in mapping.reset_suffixes('all'):
                pars['Output'+str(i)+suffix]=Parameter('edited',default='default')
            for suffix in ('track','blackout'):
                pars['Output'+str(i)+suffix]=Parameter('keep')
        show=SimpleNamespace(par=pars,UpdateMapping=Mock(),SaveShow=Mock(),op=Mock(return_value=None))
        return show

    def test_reset_groups_cover_all_calibration_without_routing_or_blackout(self):
        suffixes=mapping.reset_suffixes('all')
        self.assertEqual(set(suffixes),set(mapping.MASK_SUFFIXES)|{
            'blx','bly','brx','bry','trx','try','tlx','tly',
            'cropleft','cropright','cropbottom','croptop','rotate','flipx','flipy',
            'edgeleft','edgeright','edgebottom','edgetop','brightness','gamma','width','height'})

    def test_reset_groups_do_not_overlap(self):
        self.assertEqual(len(mapping.reset_suffixes('all')),len(set(mapping.reset_suffixes('all'))))

    def test_each_section_only_changes_its_selected_projector_values(self):
        for section,suffixes in mapping.RESET_GROUPS.items():
            with self.subTest(section=section):
                show=self.show();mapping.reset_mapping(show,(2,),section)
                for i in (1,2,3):
                    for suffix in mapping.reset_suffixes('all'):
                        self.assertEqual(show.par['Output'+str(i)+suffix].eval(),
                                         'default' if i==2 and suffix in suffixes else 'edited')
                    self.assertEqual(show.par['Output'+str(i)+'track'].eval(),'keep')
                    self.assertEqual(show.par['Output'+str(i)+'blackout'].eval(),'keep')
                show.UpdateMapping.assert_called_once_with()

    def test_all_projectors_reset(self):
        show=self.show();mapping.on_pulse(show,'Resetallprojectors')
        self.assertTrue(all(show.par['Output'+str(i)+s].eval()=='default'
                            for i in (1,2,3) for s in mapping.reset_suffixes('all')))

    def test_legacy_helper_preserves_output_grade_and_resolution(self):
        show=self.show();mapping.reset_selected(show)
        for suffix in ('width','height','brightness','gamma'):
            self.assertEqual(show.par['Output2'+suffix].eval(),'edited')

    def test_unknown_section_rejected_before_changes(self):
        show=self.show()
        with self.assertRaises(ValueError):mapping.reset_mapping(show,(2,),'unknown')
        show.UpdateMapping.assert_not_called()
        self.assertEqual(show.par.Output2maskenabled.eval(),'edited')

    def test_invalid_projector_rejected_before_changes(self):
        for indices in ((),(0,),(4,),(1,4),(True,)):
            show=self.show()
            with self.assertRaises(ValueError):mapping.reset_mapping(show,indices)
            show.UpdateMapping.assert_not_called()

    def test_mask_reset_refreshes_matching_open_draft_without_new_window(self):
        show=self.show();editor=object()
        runtime=SimpleNamespace(state_for=Mock(return_value={'target':2}),open_editor=Mock())
        show.op=lambda name:editor if name=='polygon_editor' else SimpleNamespace(module=runtime)
        mapping.reset_mapping(show,(2,),'mask')
        runtime.open_editor.assert_called_once_with(show,2,open_window=False)

    def test_other_projector_mask_reset_preserves_draft(self):
        show=self.show();runtime=SimpleNamespace(state_for=Mock(return_value={'target':1}),open_editor=Mock())
        show.op=lambda name:object() if name=='polygon_editor' else SimpleNamespace(module=runtime)
        mapping.reset_mapping(show,(2,),'mask')
        runtime.open_editor.assert_not_called()

    def test_editor_reset_targets_its_own_projector_not_selector(self):
        show=self.show();editor=SimpleNamespace(parent=lambda:show,fetch=Mock(return_value=3))
        self.assertTrue(mapping.on_editor_pulse(editor,'Resetgrade'))
        self.assertEqual(show.par.Output3brightness.eval(),'default')
        self.assertEqual(show.par.Output2brightness.eval(),'edited')

    def test_save_mapping_uses_existing_full_show_saver(self):
        show=self.show()
        self.assertTrue(mapping.on_pulse(show,'Savemapping'))
        show.SaveShow.assert_called_once_with()
        self.assertIn('Unapplied mask drafts are not saved',show.par.Mappinghelp)

    def test_save_mapping_errors_are_visible(self):
        show=self.show();show.SaveShow.side_effect=ValueError('Stop All first')
        self.assertFalse(mapping.on_pulse(show,'Savemapping'))
        self.assertEqual(show.par.Mappinghelp,'Stop All first')

    def test_selected_full_reset_includes_grade_and_resolution(self):
        show=self.show()
        self.assertTrue(mapping.on_pulse(show,'Resetmapping'))
        self.assertTrue(all(show.par['Output2'+s].eval()=='default' for s in mapping.reset_suffixes('all')))
        self.assertEqual(show.par.Output1maskenabled.eval(),'edited')


if __name__ == '__main__':
    unittest.main()
