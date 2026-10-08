"""Portable Source Media contracts; pixel/transport QA runs in TouchDesigner."""
import inspect
import unittest
from pathlib import Path

from touchdesigner.scripts import source_media as media


class SourceMediaTests(unittest.TestCase):
    def test_auto_uses_selected_file(self):
        self.assertEqual(media.source_index('auto', 'movie.mp4'), 2)

    def test_auto_empty_uses_test_pattern(self):
        self.assertEqual(media.source_index('auto', '  '), 0)

    def test_file_empty_uses_background(self):
        self.assertEqual(media.source_index('file', ''), 1)

    def test_demo_does_not_read_a_selected_file(self):
        self.assertEqual(media.source_index('demo', 'movie.mp4'), 0)

    def test_show_cues_never_inherit_designer_media(self):
        for mode in ('auto', 'file', 'demo'):
            self.assertEqual(media.source_index(mode, 'private-preview.mp4', True), 0)

    def test_contain_preserves_aspect(self):
        self.assertEqual(media.fit_extent((100, 100), (200, 100), 'contain'), (.5, 1.))
        self.assertEqual(media.fit_extent((200, 100), (100, 100), 'contain'), (1., .5))

    def test_cover_fills_canvas(self):
        self.assertEqual(media.fit_extent((100, 100), (200, 100), 'cover'), (1., 2.))
        self.assertEqual(media.fit_extent((200, 100), (100, 100), 'cover'), (2., 1.))

    def test_stretch_uses_full_canvas(self):
        self.assertEqual(media.fit_extent((100, 300), (800, 100), 'stretch'), (1., 1.))

    def test_empty_dimensions_cannot_divide_by_zero(self):
        self.assertEqual(media.fit_extent((0, 0), (0, 0), 'contain'), (1., 1.))

    def test_wrap_retains_test_shader_and_fixture_marker(self):
        original = 'void main() { fragColor = TDOutputSwizzle(vec4(color, alpha)); }'
        wrapped = media.wrap_shader(original)
        self.assertIn('void imagefxTestPattern()', wrapped)
        self.assertEqual(wrapped.count('void main()'), 1)
        self.assertIn('fragColor = TDOutputSwizzle(vec4(color, alpha));', wrapped)
        self.assertIn('uTDOutputInfo.res.zw', wrapped)

    def test_wrap_refuses_double_install_or_invalid_shader(self):
        for text in ('', 'void main() {} void main() {}', media.wrap_shader('void main() {}')):
            with self.assertRaises(ValueError): media.wrap_shader(text)

    def test_safe_defaults_and_bounded_controls(self):
        params = {p['name']: p for p in media.PARAMETERS}
        self.assertEqual(len(params), len(media.PARAMETERS))
        self.assertEqual(params['Sourcefile']['default'], '')
        self.assertEqual(params['Sourcemode']['default'], 'auto')
        self.assertEqual(params['Sourcefit']['default'], 'contain')
        self.assertEqual(params['Sourcespeed']['min'], -4.)
        self.assertEqual(params['Sourcespeed']['max'], 4.)
        self.assertTrue(params['Sourcestatus']['read_only'])

    def test_embedded_runtime_compiles_and_keeps_transport_scoped(self):
        text = inspect.getsource(media.source_index) + media.RUNTIME
        scope = {}
        exec(compile(text, 'source-media-runtime', 'exec'), scope)
        self.assertTrue(callable(scope['onPulse']))
        self.assertIn("reader.par.cuepulse.pulse()", text)
        self.assertIn("imagefx_show_runtime", text)
        self.assertNotIn('Audioenabled', text)

    def test_main_and_harness_use_the_same_installer(self):
        root = Path(__file__).resolve().parents[1]
        build = (root/'touchdesigner/scripts/build_project.py').read_text(encoding='utf-8')
        harness = (root/'touchdesigner/scripts/install_dev_harness.py').read_text(encoding='utf-8')
        self.assertIn('build_source_media(demo)', build)
        self.assertIn('context["build_source_media"](demo)', harness)


if __name__ == '__main__': unittest.main()
