"""Portable contracts. Pixel/control behavior is separately checked in TD."""
import math
from pathlib import Path
import random
import re
import runpy
import tempfile
import unittest

from tdimagefx.show import (MODULES, MODULE_TOGGLES, parse_target,
                            resolve_composition_files, validate_look_media)

ROOT=Path(__file__).resolve().parents[1]
COLOR=runpy.run_path(str(ROOT/'touchdesigner/scripts/color_switch.py'))
COMPOSE=runpy.run_path(str(ROOT/'touchdesigner/scripts/image_composition.py'))
FLOW=runpy.run_path(str(ROOT/'touchdesigner/scripts/workflow.py'))


class ColorCompositionTests(unittest.TestCase):
    def test_parameter_names_ranges_and_menus(self):
        for module in (COLOR,COMPOSE):
            definitions=module['PARAMETERS']
            self.assertEqual(len(definitions),len({d['name'] for d in definitions}))
            for d in definitions:
                self.assertRegex(d['name'],r'^[A-Z][a-z]+$')
                if 'min' in d:
                    self.assertLess(d['min'],d['max'])
                    values=d['default'] if isinstance(d['default'],list) else [d['default']]
                    self.assertTrue(all(d['min']<=v<=d['max'] for v in values))
                if d['type']=='menu':
                    self.assertEqual(len(d['menu_names']),len(d['menu_labels']))
                    self.assertIn(d['default'],d['menu_names'])

    def test_color_uniforms_bound_and_used(self):
        shader=COLOR['SHADER']
        declared={n.strip() for s in re.findall(r'uniform\s+(?:float|vec[234])\s+([^;]+);',shader) for n in s.split(',')}
        self.assertEqual(declared,{d['uniform'] for d in COLOR['PARAMETERS'] if d.get('uniform')})
        for name in declared: self.assertGreater(len(re.findall(r'\b'+name+r'\b',shader)),1)

    def test_sampling_only_on_explicit_pulse(self):
        source=COLOR['CALLBACKS']
        self.assertIn("par.name == 'Sample'",source)
        self.assertIn('numpyArray(delayed=False)',source)
        self.assertNotIn('onFrame',source)
        self.assertIn("Selected pixel is transparent",source)

    def test_color_preserves_alpha(self):
        self.assertIn('vec4(color,src.a)',COLOR['SHADER'])
        self.assertIn('float(distance<=uTolerance+1e-6)',COLOR['SHADER'])
        self.assertIn('min(dh,1.-dh)',COLOR['SHADER'])
        self.assertIn('targetValue>.001?',COLOR['SHADER'])

    def test_horizontal_splits(self):
        for name,ratio in COMPOSE['SPLITS'].items():
            a,b=COMPOSE['rectangles']('horizontal',name)
            self.assertAlmostEqual(a[2],ratio)
            self.assertAlmostEqual(b[0],ratio)
            self.assertAlmostEqual(b[2],1-ratio)
            self.assertEqual(a[3],1.)

    def test_vertical_a_is_top(self):
        a,b=COMPOSE['rectangles']('vertical','two_one')
        self.assertAlmostEqual(a[1],1/3)
        self.assertAlmostEqual(a[3],2/3)
        self.assertEqual(b[1],0)

    def test_custom_split_margin_and_gap(self):
        a,b=COMPOSE['rectangles']('horizontal','custom',.4,.1,.1)
        self.assertAlmostEqual(a[2],.28)
        self.assertAlmostEqual(b[0],.48)
        self.assertAlmostEqual(b[2],.42)
        self.assertAlmostEqual(b[0]+b[2],.9)

    def test_pip_and_overlay(self):
        a,b=COMPOSE['rectangles']('pip')
        self.assertEqual(a,(0.,0.,1.,1.))
        for actual,expected in zip(b,(.68,0.,.32,.32)): self.assertAlmostEqual(actual,expected)
        self.assertEqual(*COMPOSE['rectangles']('overlay'))

    def test_manual_positions_and_clipping(self):
        a,b=COMPOSE['rectangles']('manual',a=(-.1,.2,.3,.4),b=(.6,.7,.8,.9))
        self.assertEqual(a,(-.1,.2,.3,.4))
        self.assertEqual(b,(.6,.7,.8,.9))
        self.assertEqual(COMPOSE['rectangles']('manual',a=(99,-99,-1,20))[0],(1.,-1.,.01,2.))

    def test_layout_extremes_finite_and_positive(self):
        rng=random.Random(81)
        for _ in range(500):
            for mode in ('horizontal','vertical','pip','overlay'):
                boxes=COMPOSE['rectangles'](mode,'custom',rng.uniform(-1,2),rng.uniform(-1,2),rng.uniform(-1,2))
                for x,y,w,h in boxes:
                    self.assertTrue(all(math.isfinite(v) for v in (x,y,w,h)))
                    self.assertTrue(w>0 and h>0 and x>=0 and y>=0 and x+w<=1.00001 and y+h<=1.00001)

    def test_nonfinite_layout_values(self):
        self.assertEqual(COMPOSE['rectangles']('horizontal','custom',float('nan'),float('inf'),float('nan')),COMPOSE['rectangles']())

    def test_unknown_layout_rejected(self):
        with self.assertRaises(ValueError): COMPOSE['rectangles']('bad')

    def test_composition_source_selection(self):
        from types import SimpleNamespace
        scope={}; exec(COMPOSE['RUNTIME'],scope)
        class P:
            def __init__(self,v): self.v=v
            def eval(self): return self.v
            def __bool__(self): return bool(self.v)
        for prefix,port in (('A',0),('B',1)):
            for count in (0,1,2):
                for has_file in (False,True):
                    for mode in ('auto','file','input','transparent'):
                        pars={prefix+'source':P(mode),prefix+'file':P('file.png' if has_file else ''),prefix+'visible':P(True)}
                        c=SimpleNamespace(par=pars,inputs=list(range(count)))
                        expected=2 if has_file and mode in ('auto','file') else 1 if mode in ('auto','input') and count>port else 0
                        self.assertEqual(scope['selected'](c,prefix),expected)
                        pars[prefix+'visible']=P(False)
                        self.assertEqual(scope['selected'](c,prefix),0)

    def test_branches_have_every_nonrecursive_stage(self):
        self.assertEqual(set(COMPOSE['CORE_FILES']),set(FLOW['BRANCH_ORDER']))
        self.assertNotIn('image_composition',COMPOSE['CORE_FILES'])
        self.assertIn('calligraphic_shadow',COMPOSE['CORE_FILES'])
        self.assertIn('color_switch',COMPOSE['CORE_FILES'])

    def test_main_workflow_new_stages_and_legacy_migration(self):
        self.assertEqual(len(FLOW['DEFAULT_ORDER']),16)
        legacy=list(FLOW['LEGACY_ORDER'])
        upgraded=FLOW['validate_order'](legacy)
        self.assertEqual([n for n in upgraded if n in legacy],legacy)
        self.assertEqual(upgraded,list(FLOW['DEFAULT_ORDER']))
        self.assertEqual(set(upgraded),set(MODULES)|{'fx_rack'})

    def test_branch_reorder_and_nested_composition_rejected(self):
        order=FLOW['BRANCH_ORDER']
        self.assertEqual(FLOW['moved_order'](order,'color_switch','Stagefirst',True)[0],'color_switch')
        with self.assertRaises(ValueError): FLOW['validate_order'](FLOW['DEFAULT_ORDER'],True)

    def test_show_toggle_contract(self):
        self.assertEqual(MODULE_TOGGLES['color_switch'],'Colorswitchenabled')
        self.assertEqual(MODULE_TOGGLES['image_composition'],'Imagecompositionenabled')

    def test_safe_parameter_cue_targets(self):
        self.assertEqual(parse_target('color_switch/Tocolorr'),('color_switch','Tocolorr'))
        self.assertEqual(parse_target('image_composition/a_effects/color_switch/Mix'),('image_composition/a_effects/color_switch','Mix'))
        self.assertEqual(parse_target('image_composition/b_effects/slot3/Mix'),('image_composition/b_effects/fx_rack/slot3','Mix'))

    def test_unsafe_parameter_paths_rejected(self):
        for target in ('../x','image_composition/c_effects/color_switch/Mix','image_composition/a_effects/image_composition/Mix','image_composition/a_effects/slot9/Mix','image_composition/a_effects/../Mix','x/y/z','/project1/X'):
            with self.assertRaises(ValueError): parse_target(target)

    def test_media_paths_relative_and_blank_clear(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'a.png'; path.touch()
            self.assertEqual(resolve_composition_files({'Afile':'a.png'},d),{'Afile':str(path.resolve()),'Bfile':''})
            self.assertEqual(resolve_composition_files({},d),{'Afile':'','Bfile':''})

    def test_missing_unused_and_hidden_media(self):
        with tempfile.TemporaryDirectory() as d:
            values={'Afile':'missing.png'}
            with self.assertRaisesRegex(ValueError,'Missing composition'): resolve_composition_files(values,d)
            for selections in ({'Asource':'input'},{'Asource':'transparent'},{'Avisible':False}):
                self.assertTrue(resolve_composition_files(values,d,selections=selections)['Afile'])
            self.assertTrue(resolve_composition_files(values,d,enabled=False)['Afile'])

    def test_media_rejects_urls_unknown_types_and_fields(self):
        for values in ({'Afile':'https://example.com/a.png'},{'Afile':3},{'Afile':'a\x00b'},{'Afile':'x'*4097},{'Script':'x'},[]):
            with self.assertRaises(ValueError): resolve_composition_files(values,ROOT)

    def test_nested_media_preflight(self):
        look={'toggles':{'Imagecompositionenabled':True},'branches':{'a_effects':{'toggles':{'Layercompositeenabled':True},'layer_files':{'Topfile':'missing.png'}}}}
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,'Missing layer'): validate_look_media(look,d)
            look['toggles']['Imagecompositionenabled']=False
            validate_look_media(look,d)

    def test_recursive_and_unknown_branch_rejected(self):
        for look in ({'branches':{'other':{}}},{'branches':{'a_effects':{'branches':{'a_effects':{}}}}}):
            with self.assertRaises(ValueError): validate_look_media(look,ROOT)

    def test_no_experiment_sources_in_new_modules(self):
        sources='\n'.join((ROOT/'touchdesigner/scripts'/name).read_text(encoding='utf-8') for name in ('color_switch.py','image_composition.py'))
        for private in ('dance_backdrop','dance_puppet','wenju','Desktop'):
            self.assertNotIn(private,sources)

    def test_new_native_assets_and_source_binding_declared(self):
        from tools.record_native_validation import CORE_ASSETS,MODULE_SOURCES
        for name in ('ColorSwitch','ImageComposition'): self.assertIn('touchdesigner/core/'+name+'.tox',CORE_ASSETS)
        for name in ('color_switch','image_composition'): self.assertIn('touchdesigner/scripts/'+name+'.py',MODULE_SOURCES)
