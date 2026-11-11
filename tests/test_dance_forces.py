import importlib.util
import json
from pathlib import Path
import runpy
import tempfile
import threading
import unittest
from types import SimpleNamespace
import numpy as np
from tdimagefx import show

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('dance_forces_math',ROOT/'touchdesigner/scripts/dance_forces_math.py')
M = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(M)
MODULE = runpy.run_path(str(ROOT/'touchdesigner/scripts/dance_forces.py'))


def document(moving=True):
    a = np.zeros((120,2,6,3)); a[...,:2] = .5; a[...,2] = .9
    if moving:
        a[...,0] += (np.sin(np.arange(120)/10)*.08)[:,None,None]
    return dict(kind=M.KIND,schema_version=1,fps=30,frames=a.tolist(),camera_motion={'removed':True})


class DanceForcesTests(unittest.TestCase):
    def test_fade_in_is_smooth_bounded_and_optional(self):
        self.assertEqual(M.fade_in(0,1.5),0)
        self.assertEqual(M.fade_in(.75,1.5),.5)
        self.assertEqual(M.fade_in(3,1.5),1)
        self.assertEqual(M.fade_in(0,0),1)
        self.assertEqual(M.fade_in(-1,1.5),0)

    def test_stationary_observations_have_zero_force(self):
        clip = M.Clip(document(False))
        self.assertTrue(np.array_equal(clip.sample(2)[1],np.zeros((2,6,2))))

    def test_motion_produces_bounded_seekable_force(self):
        clip = M.Clip(document())
        first = clip.sample(1)[1].copy()
        self.assertGreater(np.abs(first).max(),.001)
        self.assertLessEqual(np.linalg.norm(first,axis=-1).max(),.22)
        clip.sample(3)
        np.testing.assert_array_equal(first,clip.sample(1)[1])

    def test_pause_loop_and_end_decay(self):
        clip = M.Clip(document())
        np.testing.assert_allclose(clip.sample(.8)[1],clip.sample(4.8)[1])
        self.assertEqual(np.abs(clip.sample(4)[1]).sum(),0)
        self.assertLess(np.abs(clip.sample(10,loop=False)[1]).sum(),1e-4)

    def test_tracking_loss_and_reacquisition_no_impulse(self):
        f = M.Filter(); p = np.ones((2,6,3))*.5; p[...,2]=1
        f.step(p,1/30)
        p[...,2]=0; p[...,:2]=.9
        self.assertEqual(np.abs(f.step(p,1/30)).sum(),0)
        p[...,2]=1
        self.assertEqual(np.abs(f.step(p,1/30)).sum(),0)

    def test_jump_rejected(self):
        f=M.Filter(); p=np.ones((2,6,3))*.5; p[...,2]=1
        f.step(p,1/30); p[...,:2]+=.4
        self.assertEqual(np.abs(f.step(p,1/30)).sum(),0)

    def test_camera_bad_observation_is_zero_confidence(self):
        pose=[[.5,.5,0.,1.] for _ in range(33)]
        self.assertEqual(M.observations([pose,pose],False)[...,2].sum(),0)

    def test_mapping_actor_controls_and_mirror(self):
        p,f=M.Clip(document()).sample(1)
        none=M.map_forces(p,f,actor1=0,actor2=0)
        self.assertEqual(np.abs(none[:,2:]).sum(),0)
        normal=M.map_forces(p,f); mirrored=M.map_forces(p,f,mirror=True)
        np.testing.assert_allclose(normal[:,2],-mirrored[:,2])

    def test_release_returns_to_original(self):
        f=M.Filter(); p=np.ones((2,6,3))*.5; p[...,2]=1
        f.step(p,.033); p[...,0]+=.02
        force=f.step(p,.033)
        self.assertGreater(np.abs(force).sum(),0)
        for _ in range(300): force=f.step(p,.033)
        self.assertLess(np.abs(force).sum(),1e-5)

    def test_rejects_unstabilized_malformed_and_nonfinite(self):
        for mutate in (lambda d:d.update(kind='bad'),lambda d:d.update(fps=float('nan')),
                       lambda d:d.update(frames=[]),lambda d:d.update(camera_motion={})):
            doc=document(); mutate(doc)
            with self.assertRaises(ValueError): M.Clip(doc)
        doc=document(); doc['frames'][1][0][0][0]=float('nan')
        with self.assertRaises(ValueError): M.Clip(doc)

    def test_read_cache(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'motion.json'; path.write_text(json.dumps(document()))
            self.assertEqual(M.Clip.read(path).duration,4.)

    def test_control_defaults_and_clamps(self):
        pars=MODULE['PARAMETERS']; names=[p[1] for p in pars]
        self.assertEqual(len(names),len(set(names)))
        self.assertFalse(next(p[3] for p in pars if p[1]=='Danceenabled'))
        for _,name,kind,default,lo,hi,_ in pars:
            if kind in {'int','float'}:
                self.assertTrue(lo<=default<=hi,name)
            if kind=='menu': self.assertIn(default,lo)
        self.assertIn('c.par.Mix > 0',Path(ROOT/'touchdesigner/scripts/dance_forces_runtime.py').read_text())

    def test_every_control_is_wired(self):
        source=(ROOT/'touchdesigner/scripts/dance_forces_runtime.py').read_text()+(ROOT/'touchdesigner/scripts/dance_forces.py').read_text().split('def install')[1]
        for _,name,kind,*_ in MODULE['PARAMETERS']:
            self.assertIn(name,source,name)

    def test_passive_file_whitelist(self):
        for bad in ({'bad':{}},{'ink_dream_flow':{'Script':'bad.py'}},
                    {'ink_dream_flow':{'Dancecache':'https://remote/file'}},
                    {'ink_dream_flow':{'Dancecache':'bad\x00.json'}}):
            with self.assertRaises(ValueError): show.resolve_force_files(bad,'.')

    def test_enabled_cue_requires_cache_not_video(self):
        modules={'ink_dream_flow':{'Danceenabled':True}}
        toggles={'Inkdreamenabled':True}
        with self.assertRaises(ValueError): show.resolve_force_files({},'.',modules=modules,toggles=toggles)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'motion.json'; path.write_text(json.dumps(document()))
            got=show.resolve_force_files({'ink_dream_flow':{'Dancecache':'motion.json','Dancevideo':'removed.mp4'}},folder,modules=modules,toggles=toggles)
            # Compare canonical paths, not the platform's temporary-dir alias.
            self.assertEqual(got['ink_dream_flow']['Dancecache'],str(path.resolve()))
        modules['ink_dream_flow']['Dancesource']='live'
        show.resolve_force_files({},'.',modules=modules,toggles=toggles)

    def test_old_shows_and_inactive_branches_remain_valid(self):
        show.validate_look_media({},'.')
        show.validate_look_media({'modules':{'ink_dream_flow':{'Danceenabled':True}},'toggles':{'Inkdreamenabled':True}},'.',active=False)

    def test_shader_has_soft_fields_and_no_pose_rendering(self):
        shader=MODULE['SHADER']
        self.assertIn('exp(-dot(q,q)',shader)
        self.assertIn('uForce11',shader)
        self.assertIn('v.xy*dt',shader)
        self.assertIn('previous.z+v.z*dt',shader)
        self.assertNotIn('vec4 color',shader)
        self.assertNotIn('Feedback',shader)

    def test_motion_is_integrated_inside_all_three_renderers(self):
        flow=runpy.run_path(str(ROOT/'touchdesigner/scripts/ink_dream_flow.py'))
        for source in (flow['SHADER'],flow['brush_variant']()[1],flow['radial_variant']()[1]):
            shader=MODULE['integrate_shader'](source)
            self.assertEqual(MODULE['integrate_shader'](shader),shader)
            self.assertIn('vec2 flowP=p-danceLocalTravel(dance.xy)',shader)
            self.assertIn('float t=uTime*uFlowSpeed+dance.z',shader)
            self.assertIn('fieldGrains(screen-dance.xy,seed)',shader)
            self.assertIn('uDanceOutput.x<.5',shader)
            # The input picture and paper coordinates are not displaced.
            self.assertIn('texture(sTD2DInputs[0],uv)',shader)
            for line in source.splitlines():
                if 'paper' in line.lower() or 'envelope=' in line or 'ambient=' in line:
                    self.assertIn(line,shader)
            a=source[source.index('vec3 staticGlitter'):source.index('void main()')]
            b=shader[shader.index('vec3 staticGlitter'):shader.index('void main()')]
            self.assertEqual(a,b)

    def test_response_delay_default_and_range(self):
        p = next(p for p in MODULE['PARAMETERS'] if p[1] == 'Danceresponse')
        self.assertEqual(p[3:6], (.75, 0, 5))
        self.assertIn('seconds', p[-1])

    def test_pattern_force_space_default_and_legacy_choice(self):
        p = next(p for p in MODULE['PARAMETERS'] if p[1] == 'Dancespace')
        self.assertEqual(p[3], 'pattern')
        self.assertEqual(p[4], ['canvas', 'pattern'])
        self.assertIn('Follow Pattern Composition', p[5])

    def test_pattern_force_uses_inverse_composition_and_soft_bounds(self):
        helper = MODULE['FLOW_HELPER']
        self.assertIn('((uv-.5)*metric-uCenter)*scale', helper)
        self.assertIn('local.x/=stretch', helper)
        self.assertIn('radians(uRotation)', helper)
        self.assertIn('transpose(toPattern)*(material.xy*vec2(stretch,1.))/scale', helper)
        self.assertIn('if(edge<=0.) return vec3(0.)', helper)
        self.assertIn('smoothstep(0.,.06,edge)', helper)
        self.assertIn('if(uDanceOutput.y<.5)', helper)
        self.assertIn('texture(sTD2DInputs[1],clamp(uv,0.,1.)).xyz', helper)

    def test_pattern_force_upgrade_keeps_existing_renderer(self):
        flow=runpy.run_path(str(ROOT/'touchdesigner/scripts/ink_dream_flow.py'))
        for source in (flow['SHADER'],flow['brush_variant']()[1],flow['radial_variant']()[1]):
            current=MODULE['integrate_shader'](source)
            legacy=current.replace(MODULE['FLOW_HELPER'], MODULE['LEGACY_FLOW_HELPER'])
            self.assertEqual(MODULE['integrate_shader'](legacy),current)
            self.assertEqual(MODULE['integrate_shader'](current),current)
        with self.assertRaises(ValueError):
            MODULE['integrate_shader']('// DANCE_MATERIAL_ADVECTION_V2 but no recognized helper')

    def test_pattern_composition_edits_do_not_reset_motion(self):
        spec=importlib.util.spec_from_file_location('dance_pattern_runtime',ROOT/'touchdesigner/scripts/dance_forces_runtime.py')
        runtime=importlib.util.module_from_spec(spec); spec.loader.exec_module(runtime)
        calls=[]
        runtime.reset=lambda c:calls.append('reset')
        runtime.reset_flow=lambda c:calls.append('reset_flow')
        for name in ('Dancespace','Scale','Centerx','Centery','Rotation','Stretch'):
            runtime.changed(SimpleNamespace(),name,0.)
        self.assertEqual(calls,[])

    def test_response_smooths_velocity_not_the_finished_image(self):
        shader = MODULE['RESPONSE_SHADER']
        self.assertIn('target=velocityAt(uv)', shader)
        self.assertIn('1.-exp(-dt/max(uResponse,.0001))', shader)
        self.assertIn('mix(previous.xyz,target,blend)', shader)
        self.assertNotIn('sTD2DInputs[1]', shader)
        self.assertIn('if(uResponse<=0.) return velocityAt(uv)', MODULE['SHADER'])
        self.assertIn('v=responseAt(uv-.5*dt*v.xy/metric)', MODULE['SHADER'])

    def test_response_pauses_and_resets_with_material_history(self):
        shader = MODULE['RESPONSE_SHADER']
        self.assertIn('if(uMotion.y>.5){fragColor=vec4(0.);return;}', shader)
        self.assertIn('if(uMotion.x<=0.){fragColor=TDOutputSwizzle(previous);return;}', shader)
        for file in ('touchdesigner/scripts/dance_forces_runtime.py', 'touchdesigner/extensions/ShowControlExt.py'):
            text = (ROOT/file).read_text()
            self.assertIn("'dance_motion_history'", text)
            self.assertIn("'dance_response_history'", text)

    def test_response_edit_does_not_restart_source_or_material(self):
        spec=importlib.util.spec_from_file_location('dance_response_runtime',ROOT/'touchdesigner/scripts/dance_forces_runtime.py')
        runtime=importlib.util.module_from_spec(spec); spec.loader.exec_module(runtime)
        calls=[]
        runtime.reset = lambda c:calls.append('reset')
        runtime.reset_flow = lambda c:calls.append('reset_flow')
        runtime._sample_key = 'old'
        runtime.changed(SimpleNamespace(), 'Danceresponse', .75)
        self.assertEqual(calls, [])
        self.assertIsNone(runtime._sample_key)

    def test_reset_clears_both_gpu_histories(self):
        spec=importlib.util.spec_from_file_location('dance_response_reset',ROOT/'touchdesigner/scripts/dance_forces_runtime.py')
        runtime=importlib.util.module_from_spec(spec); spec.loader.exec_module(runtime)
        calls=[]
        c=SimpleNamespace(store=lambda *a:None, storeStartupValue=lambda *a:None,
            op=lambda name:SimpleNamespace(par=SimpleNamespace(resetpulse=SimpleNamespace(pulse=lambda:calls.append(name)))))
        runtime.reset_flow(c)
        self.assertEqual(calls, ['dance_motion_history','dance_response_history'])

    def test_field_clock_pause_resume_seek_and_resolution(self):
        spec=importlib.util.spec_from_file_location('dance_forces_runtime',ROOT/'touchdesigner/scripts/dance_forces_runtime.py')
        runtime=importlib.util.module_from_spec(spec); spec.loader.exec_module(runtime)
        clock=SimpleNamespace(frame=10); runtime.absTime=clock
        storage={}; image=SimpleNamespace(width=1920,height=1080)
        c=SimpleNamespace(par=SimpleNamespace(Time=1.),
            fetch=lambda k,default=None,**kw:storage.get(k,default),
            store=lambda k,v:storage.update({k:v}),storeStartupValue=lambda *a:None,
            op=lambda name:image if name=='in1_image' else None)
        self.assertEqual(runtime.flow_step(c)['reset'],1)
        clock.frame+=1; c.par.Time+=1/30
        step=runtime.flow_step(c)
        self.assertAlmostEqual(step['dt'],1/30)
        self.assertIs(runtime.flow_step(c),step)
        clock.frame+=1
        self.assertEqual(runtime.flow_step(c)['dt'],0)
        clock.frame+=1; c.par.Time+=1/30
        self.assertAlmostEqual(runtime.flow_step(c)['dt'],1/30)
        clock.frame+=1; c.par.Time-=1
        self.assertEqual(runtime.flow_step(c)['reset'],1)
        clock.frame+=1; c.par.Time+=5
        self.assertEqual(runtime.flow_step(c)['reset'],1)
        clock.frame+=1; image.width=5760
        self.assertEqual(runtime.flow_step(c)['reset'],1)
        runtime.reset_flow(c)
        self.assertIsNone(storage['dance_flow_clock'])

    def test_preparation_is_nonblocking_and_shared(self):
        entered, release = threading.Event(), threading.Event()
        threads = []
        def loader(path):
            threads.append(threading.get_ident()); entered.set()
            if not release.wait(2): raise RuntimeError('test timed out')
            return M.Clip(document())
        cache = M.PreparedClips(loader=loader)
        try:
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder)/'clip.json'; path.write_text('{}')
                settings = (.12,.65,.3,.015)
                key, clip = cache.request(path, settings)
                self.assertIsNone(clip)
                self.assertTrue(entered.wait(1))
                self.assertNotEqual(threads, [threading.get_ident()])
                self.assertIsNone(cache.request(path,settings)[1])
                self.assertEqual(len(cache.pending),1)
                release.set(); next(iter(cache.pending.values())).result(timeout=2)
                prepared = cache.request(path,settings)[1]
                self.assertIs(cache.request(path,settings)[1],prepared)
                self.assertEqual(prepared.settings,settings)
                np.testing.assert_array_equal(prepared.sample(1)[1],M.Clip(document()).sample(1)[1])
        finally:
            release.set(); cache.close()

    def test_cooperative_motion_decode_matches_json_and_rejects_invalid_data(self):
        doc=document()
        parsed=M._cooperative_document(json.dumps(doc,indent=2))
        np.testing.assert_array_equal(parsed['frames'],doc['frames'])
        np.testing.assert_array_equal(M.Clip(parsed).sample(1)[1],M.Clip(doc).sample(1)[1])
        for invalid in ('[]','{"frames": [1,]}','{"frames": []} trailing','{"a": 1,}',
                        '{"frames": [[1]]}', '{"frames": [] "a":1}'):
            with self.assertRaises((ValueError,TypeError)):
                M._cooperative_document(invalid)

    def test_preparation_queue_and_cache_are_bounded(self):
        release = threading.Event()
        def loader(path):
            if not release.wait(2): raise RuntimeError('test timed out')
            return M.Clip(document())
        cache = M.PreparedClips(capacity=1,loader=loader)
        try:
            with tempfile.TemporaryDirectory() as folder:
                path=Path(folder)/'clip.json'; path.write_text('{}')
                for value in (.1,.2,.3,.4,.5): cache.request(path,(value,.65,.3,.015))
                self.assertEqual(len(cache.pending),2)
                release.set()
                for future in list(cache.pending.values()): future.result(timeout=2)
                cache.request(path,(.2,.65,.3,.015))
                self.assertEqual(len(cache.ready),1)
        finally:
            release.set(); cache.close()

    def test_preparation_error_is_reported_without_repeated_work(self):
        cache = M.PreparedClips(check_interval=0.)
        try:
            with tempfile.TemporaryDirectory() as folder:
                path=Path(folder)/'bad.json'; path.write_text('{}')
                key,_=cache.request(path,(.12,.65,.3,.015))
                with self.assertRaises(ValueError): next(iter(cache.pending.values())).result(timeout=2)
                cache.check_interval=10.
                for _ in range(2):
                    with self.assertRaises(ValueError): cache.request(path,(.12,.65,.3,.015))
                self.assertFalse(cache.pending)
                path.write_text(json.dumps(document()))
                cache.check_interval=0.
                with self.assertRaises(ValueError): cache.request(path,(.12,.65,.3,.015))
                next(iter(cache.pending.values())).result(timeout=2)
                self.assertIsNotNone(cache.request(path,(.12,.65,.3,.015))[1])
        finally:
            cache.close()

    def test_activation_zero_frame_and_single_history_reset(self):
        spec=importlib.util.spec_from_file_location('activation_runtime',ROOT/'touchdesigner/scripts/dance_forces_runtime.py')
        runtime=importlib.util.module_from_spec(spec); spec.loader.exec_module(runtime)
        runtime.absTime=SimpleNamespace(frame=10)
        data={}; resets=[]
        c=SimpleNamespace(par=SimpleNamespace(Enabled=True,Mix=1.,Danceenabled=False,Danceamount=1.,Time=5.,Dancespeed=1.),
            fetch=lambda k,d=None,**kw:data.get(k,d),store=lambda k,v:data.update({k:v}),storeStartupValue=lambda *a:None)
        runtime.reset_flow=lambda c:resets.append(runtime.absTime.frame)
        self.assertEqual(runtime.output_enabled(c),0)
        c.par.Danceenabled=True
        self.assertEqual(runtime.output_enabled(c),0)
        runtime.changed(c,'Danceenabled',False)
        self.assertEqual(runtime.output_enabled(c),0)
        self.assertEqual(resets,[10])
        runtime.absTime.frame+=1
        self.assertEqual(runtime.output_enabled(c),1)
        c.par.Danceenabled=False; self.assertEqual(runtime.output_enabled(c),0)
        c.par.Danceenabled=True; self.assertEqual(runtime.output_enabled(c),0)
        self.assertEqual(resets,[10,11])

    def test_zero_mix_rearms_but_ordinary_force_edits_do_not(self):
        spec=importlib.util.spec_from_file_location('mix_runtime',ROOT/'touchdesigner/scripts/dance_forces_runtime.py')
        runtime=importlib.util.module_from_spec(spec); spec.loader.exec_module(runtime)
        runtime.absTime=SimpleNamespace(frame=10)
        data={}; resets=[]
        c=SimpleNamespace(par=SimpleNamespace(Enabled=True,Mix=1.,Danceenabled=True,Danceamount=1.,Time=5.,Dancespeed=1.),
            fetch=lambda k,d=None,**kw:data.get(k,d),store=lambda k,v:data.update({k:v}),storeStartupValue=lambda *a:None)
        runtime.reset_flow=lambda c:resets.append(runtime.absTime.frame)
        runtime.output_enabled(c); runtime.absTime.frame+=1
        for name in ('Dancestrength','Danceresponse','Dancefadein','Dancespace'):
            runtime.changed(c,name,0.)
        self.assertEqual(runtime.output_enabled(c),1)
        self.assertEqual(len(resets),1)
        c.par.Danceamount=0; runtime.changed(c,'Danceamount',1.)
        self.assertEqual(runtime.output_enabled(c),0)
        c.par.Danceamount=1; runtime.changed(c,'Danceamount',0.)
        self.assertEqual(runtime.output_enabled(c),0)
        self.assertEqual(len(resets),2)

    def test_runtime_never_synchronously_loads_or_filters_recording(self):
        text=(ROOT/'touchdesigner/scripts/dance_forces_runtime.py').read_text()
        sample=text[text.index('def sample(c):'):text.index('def active(c):')]
        self.assertNotIn('Clip.read',sample)
        self.assertIn('prepared_clips().request',sample)
        self.assertIn('_clip.settings',sample)
        self.assertIn("not c.fetch('dance_force_ready'",sample)
        self.assertNotIn('fade_in(abs(',sample)

    def test_cue_retrigger_rearms_activation_without_starting_workers(self):
        text=(ROOT/'touchdesigner/extensions/ShowControlExt.py').read_text()
        self.assertIn("module.store('dance_force_gate',None)",text)
        self.assertIn("module.store('dance_force_ready',False)",text)
        self.assertNotIn('Dancestartcamera.pulse()',text)

    def test_no_auto_worker_start_or_camera_in_show(self):
        ext=(ROOT/'touchdesigner/extensions/ShowControlExt.py').read_text()
        self.assertIn("look['force_files']",ext)
        self.assertIn("module.store('dance_force_clock'",ext)
        self.assertNotIn('Dancestartcamera.pulse()',ext)
        self.assertNotIn('Danceanalyze.pulse()',ext)

    def test_puppet_fade_after_trails_and_explicit_cue_reset(self):
        puppet=runpy.run_path(str(ROOT/'touchdesigner/scripts/dance_puppet.py'))
        self.assertIn('Fadein',[p[1] for p in puppet['PARAMETERS']])
        self.assertIn('c.a*=clamp(uFinish.w',puppet['FINISH'])
        self.assertNotIn('Fadein',puppet['TRAIL'])
        self.assertIn("module.store('puppet_fade_start'",(ROOT/'touchdesigner/extensions/ShowControlExt.py').read_text())


if __name__=='__main__': unittest.main()
