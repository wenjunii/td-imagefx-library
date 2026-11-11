"""Older show looks may adopt local prepared media without changing saved looks."""
import copy
import unittest
from tdimagefx import show


class LegacyMotionMediaTests(unittest.TestCase):
    def setUp(self):
        self.force = {name: {'Dancecache': '/local/'+name+'.json', 'Dancevideo': ''}
                      for name in show.FLOW_MODULES}
        self.puppet = {'Renderfile': '/local/puppet.mov', 'Fanrenderfile': '/local/fan.mov'}

    def expand(self, look, **kw):
        return show.with_legacy_motion_media(look, force_files=kw.get('force', self.force),
                                            puppet_files=kw.get('puppet', self.puppet))

    def test_pre_feature_look_gets_passive_media_without_enabling_anything(self):
        look = {'modules': {name: {'Mix': .7} for name in show.FLOW_MODULES},
                'toggles': {'Inkdreamenabled': True}}
        before = copy.deepcopy(look)
        result = self.expand(look)
        self.assertEqual(result['force_files'], self.force)
        self.assertEqual(result['puppet_files'], self.puppet)
        self.assertEqual(result['modules'], look['modules'])
        self.assertEqual(result['toggles'], look['toggles'])
        self.assertEqual(look, before)

    def test_explicit_blank_files_are_not_overwritten(self):
        look = {'force_files': {'ink_dream_flow': {'Dancecache': '', 'Dancevideo': ''}},
                'puppet_files': {}}
        result = self.expand(look)
        self.assertEqual(result['force_files']['ink_dream_flow'], look['force_files']['ink_dream_flow'])
        self.assertEqual(result['puppet_files'], {})

    def test_saved_motion_controls_without_files_are_not_treated_as_legacy(self):
        for enabled in (True, False):
            look = {'modules': {'ink_dream_flow': {'Danceenabled': enabled}}}
            self.assertNotIn('ink_dream_flow', self.expand(look)['force_files'])

    def test_existing_puppet_cue_cannot_silently_switch_characters(self):
        for look in ({'modules': {'dance_puppet': {'Zoom': 1.2}}},
                     {'toggles': {'Dancepuppetenabled': True}}):
            self.assertNotIn('puppet_files', self.expand(look))

    def test_saved_media_wins_over_current_designer_files(self):
        look = {'force_files': {'ink_brush_flow': {'Dancecache': '/show/custom.json'}},
                'puppet_files': {'Renderfile': '/show/other-characters.mov'}}
        result = self.expand(look)
        self.assertEqual(result['force_files']['ink_brush_flow'], look['force_files']['ink_brush_flow'])
        self.assertEqual(result['puppet_files'], look['puppet_files'])

    def test_drafts_do_not_alias_designer_defaults(self):
        result = self.expand({})
        result['force_files']['ink_radial_flow']['Dancecache'] = 'changed'
        result['puppet_files']['Renderfile'] = 'changed'
        self.assertNotEqual(self.force['ink_radial_flow']['Dancecache'], 'changed')
        self.assertNotEqual(self.puppet['Renderfile'], 'changed')

    def test_each_branch_uses_its_own_defaults(self):
        branch = {'ink_dream_flow': {'Dancecache': '/branch/motion.json'}}
        result = self.expand({}, force=branch, puppet={'Renderfile': '/branch/puppet.mov'})
        self.assertEqual(result['force_files'], branch)
        self.assertEqual(result['puppet_files']['Renderfile'], '/branch/puppet.mov')

    def test_no_available_defaults_does_not_fabricate_media(self):
        self.assertEqual(show.with_legacy_motion_media({}), {})

    def test_missing_enabled_media_still_fails_validation(self):
        for look in ({'modules': {'ink_dream_flow': {'Danceenabled': True}},
                      'toggles': {'Inkdreamenabled': True}},
                     {'toggles': {'Dancepuppetenabled': True}}):
            with self.assertRaises(ValueError):
                show.validate_look_media(self.expand(look), '.')

    def test_captured_media_stays_pinned_after_designer_changes(self):
        first = self.expand({})
        self.force['ink_dream_flow']['Dancecache'] = '/different.json'
        self.puppet['Renderfile'] = '/different.mov'
        self.assertEqual(self.expand(first), first)


if __name__ == '__main__':
    unittest.main()
