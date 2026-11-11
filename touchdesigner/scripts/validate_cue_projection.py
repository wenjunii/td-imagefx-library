"""Off-air renderer and cue-editor regression checks in a disposable copy."""
import copy
import json
from pathlib import Path
import runpy
import traceback

ROOT = Path(__file__).resolve().parents[2]


def validate():
    import td
    import numpy as np
    original = td.op('/project1/imagefx_demo/show_control')
    before = copy.deepcopy(original.ext.ShowControlExt.document)
    if original.ext.ShowControlExt.engine.state != 'stopped':
        raise RuntimeError('Stop All before validation')
    sandbox=td.op('/project1').create(td.baseCOMP,'imagefx_channel_validation')
    wall=sandbox.copy(original.parent().op('wall_output'),name='wall_output')
    host=sandbox.copy(original,name='show_control')
    checks = {}
    report = dict(ok=False, checks=checks, hardware_outputs_opened=False)
    try:
        upgrade = runpy.run_path(str(ROOT / 'touchdesigner/scripts/cue_projection.py'))['upgrade'](host)
        checks['upgrade_preserves_cues'] = upgrade['cues_preserved'] == len(before['cues'])
        host.op('show_tick').par.active = False
        ext = host.ext.ShowControlExt
        require_connections = all(host.op('output_source'+str(i)).par.top.expr == repr('cue_projection'+str(i))
                                  for i in (1,2,3))
        checks['cue_output_expressions_replace_global_routes'] = require_connections
        if not require_connections: raise AssertionError('Old global output expression remains')
        host.par.Renderwidth, host.par.Renderheight = 320, 180
        host.par.Routingmode, host.par.Sharedtrack = 'identical', 1
        host.par.Masterblackout = False  # QA copy only; no windows are opened.
        wall.par.Enabled,wall.par.Blackout,wall.par.Testpattern=True,False,False
        for i in (1,2,3):
            host.par['Output{}track'.format(i)]=i
            host.par['Output{}width'.format(i)], host.par['Output{}height'.format(i)] = 320,180
            host.par['Output{}blackout'.format(i)] = False
            host.par['Track{}visible'.format(i)] = True
            host.par['Track{}blend'.format(i)], host.par['Track{}level'.format(i)] = 1,1
        # Use deterministic full-color sources to measure destinations, not art.
        sources = []
        for i, color in enumerate(((1,0,0),(0,1,0),(0,0,1)),1):
            node = host.create(td.constantTOP, 'route_fixture'+str(i))
            node.par.colorr, node.par.colorg, node.par.colorb = color
            node.par.outputresolution = 'custom'; node.par.resolutionw, node.par.resolutionh = 320,180
            sources.append(node)
            for side in (0,1):
                selected = host.op('track{}_source{}'.format(i,side))
                selected.lock = False; selected.par.top = node.name
        def require(value, name):
            checks[name] = bool(value)
            if not value: raise AssertionError(name)
        def pixels(i):
            ext.UpdateCueRouting()
            for side in (0,1): host.op('cue_projection{}_source{}'.format(i,side)).cook(force=True)
            host.op('cue_projection'+str(i)).cook(force=True)
            host.op('output_source'+str(i)).cook(force=True)
            host.op('mapped'+str(i)).cook(force=True)
            node=host.op('out{}_projector'.format(i)); node.cook(force=True)
            a=node.numpyArray(delayed=False)
            require(a is not None and np.isfinite(a).all(), 'finite_pixels_'+str(i))
            return a[a.shape[0]//2, a.shape[1]//2, :3]
        def wall_pixels():
            for i in (1,2,3):
                pixels(i)
                for name in ('source'+str(i),'projector'+str(i),'projection_map'+str(i),'p'+str(i)+'_out'):
                    if wall.op(name) is not None: wall.op(name).cook(force=True)
            node=wall.op('out1_wall_4k'); node.cook(force=True)
            a=node.numpyArray(delayed=False)
            require(a is not None and a.shape[:2]==(2160,3840),'wall_4k_frame')
            return [float(a[y,x,0]) for x,y in ((960,1620),(2880,1620),(960,540))]
        for layout in ('identical','panoramic','independent','cue'):
            host.par.Routingmode=layout
            for i in (1,2,3): host.par['Track{}visible'.format(i)]=(i==1)
            for route, outputs in ext.model.PROJECTION_ROUTES.items():
                cue=dict(ext.model.new_cue(),projection=route)
                ext.tracks={1:dict(cue=cue,side=1,route_order=1)}
                ext._mapping_key=None; ext.UpdateMapping()
                expected=outputs if outputs is not None else ((1,) if layout in {'independent','cue'} else (1,2,3))
                for i in (1,2,3):
                    require(np.allclose(pixels(i), (1,0,0) if i in expected else (0,0,0),atol=.02), layout+'_'+route+'_p'+str(i))
        host.par.Routingmode='identical'
        for i in (1,2,3): host.par['Track{}visible'.format(i)]=True
        ext.tracks={1:dict(cue=dict(ext.model.new_cue(),projection='inherit'),side=1,route_order=100),
                    2:dict(cue=dict(ext.model.new_cue(),track=2,projection='p2'),side=1,route_order=1)}
        require(np.allclose(pixels(2),(0,1,0),atol=.02),'explicit_route_beats_newer_inherited_track')
        ext.tracks={i:dict(cue=dict(ext.model.new_cue(),track=i,projection='p'+str(i)),side=1,route_order=i) for i in (1,2,3)}
        for i,color in enumerate(((1,0,0),(0,1,0),(0,0,1)),1):
            require(np.allclose(pixels(i),color,atol=.02),'simultaneous_track_'+str(i))
        for channels,outputs in ext.model.OUTPUT_CHANNELS.items():
            if outputs is None: continue
            ext.tracks={1:dict(cue=dict(ext.model.new_cue(),projection='all',channels=channels),side=1)}
            for i in (1,2,3):
                require(np.allclose(pixels(i),(1,0,0) if i in outputs else (0,0,0),atol=.02),'channels_'+channels+'_p'+str(i))
        gradient_code=host.create(td.textDAT,'route_gradient_code')
        gradient_code.text='layout(location=0) out vec4 fragColor; void main(){fragColor=TDOutputSwizzle(vec4(vUV.x,0,0,1));}'
        gradient=host.create(td.glslTOP,'route_gradient')
        gradient.par.pixeldat=gradient_code.name
        gradient.par.outputresolution='custom'; gradient.par.resolutionw,gradient.par.resolutionh=960,180
        host.op('track1_source1').par.top=gradient.name
        ext.tracks={1:dict(cue=dict(ext.model.new_cue(),projection='panoramic'),side=1)}
        for i in (1,2,3):
            require(abs(float(pixels(i)[0])-(i-.5)/3)<.01,'panorama_distinct_slice_'+str(i))
        ext.tracks[1]['cue']['channels']='1_3'
        require(abs(float(pixels(1)[0])-.25)<.01 and abs(float(pixels(3)[0])-.75)<.01
                and np.allclose(pixels(2),(0,0,0),atol=.02),'panorama_pair_channels_1_3')
        require(ext.TrackCanvasWidth(1)==640,'pair_panorama_two_panel_resolution')
        # An explicit panel cue must not inherit the global panorama's crop.
        host.par.Routingmode='panoramic'
        ext.tracks={1:dict(cue=dict(ext.model.new_cue(),projection='p2'),side=1)}
        ext._mapping_key=None; ext.UpdateMapping()
        require(abs(float(pixels(2)[0])-.5)<.01,'panel_cue_not_double_cropped')
        host.par.Routingmode='identical'
        ext._mapping_key=None; ext.UpdateMapping()
        host.op('track1_source0').par.top=sources[0].name
        # Route-change dissolve: red P1 -> green P2, no outgoing leak on P2.
        host.op('track1_source1').par.top=sources[1].name
        old=dict(cue=dict(ext.model.new_cue(),projection='p1'))
        ext.tracks={1:dict(cue=dict(ext.model.new_cue(),projection='p2'),old=old,side=1,fading=True)}
        host.par.Track1blend=.5
        require(np.allclose(pixels(1),(.5,0,0),atol=.02),'old_destination_fades_out')
        require(np.allclose(pixels(2),(0,.5,0),atol=.02),'new_destination_fades_in_without_leak')
        require(np.allclose(pixels(3),(0,0,0),atol=.02),'unused_destination_black')
        host.par.Masterblackout=True
        require(np.allclose(pixels(2),(0,0,0),atol=.02),'master_blackout_remains_authoritative')
        ext.tracks={}; ext.engine.state='stopped'
        # Editor commits and reloads each route; JSON is the persistence contract.
        ext._replace_cues([ext.model.new_cue()])
        for route in ext.model.PROJECTION_ROUTES:
            ext.SelectCue(1)
            previous_route=host.par.Cueprojection.eval()
            host.par.Cueprojection=route
            # Native parameter events are serviced at frame boundaries. Invoke
            # the actual callback here because this sweep runs in one TD call.
            host.op('cue_projection_parameters').module.onValueChange(host.par.Cueprojection,previous_route)
            require(ext.document['cues'][0]['projection']==route,'selector_immediately_commits_'+route)
            ext.ApplyCue(); ext.SelectCue(1)
            require(host.par.Cueprojection.eval()==route and ext.document['cues'][0]['projection']==route,'editor_'+route)
        for channels in ext.model.OUTPUT_CHANNELS:
            previous=host.par.Cuechannels.eval(); host.par.Cuechannels=channels
            host.op('cue_projection_parameters').module.onValueChange(host.par.Cuechannels,previous)
            require(ext.document['cues'][0]['channels']==channels,'channel_editor_'+channels)
            require(ext.document['cues'][0]['track']==1,'channel_does_not_duplicate_playback_'+channels)
        require(ext.model.validate_show(json.loads(json.dumps(ext.document)))==ext.document,'json_roundtrip')
        host.par.Routingmode='cue'
        host.par.Showfile=str(ROOT/'build/cue-projection/show-roundtrip.json')
        ext.SaveShow(); saved=copy.deepcopy(ext.document)
        ext.LoadShow()
        require(ext.document==saved,'save_and_load_show_preserves_routes')
        require(host.par.Routingmode.eval()=='cue','save_and_load_follow_show_mode')
        # Exercise the actual preparation path, including per-cue canvas size.
        for track in (1,2,3):
            ext._replace_cues([dict(ext.model.new_cue(),track=track,projection='panoramic',channels='all',duration=0,fade=0)])
            ext.prepare(ext.document['cues'][0])
            for _ in range(2000):
                loading=[v for v in ext.prepared.values() if v.get('loading')]
                if not loading: break
                for v in loading:
                    if 'warm_frame' in v: v['warm_frame']=td.absTime.frame-1
                ext._service_preloads()
            prepared=ext.prepared[ext.document['cues'][0]['id']]
            require(not prepared.get('loading') and not prepared.get('error'),'panoramic_preload_ready_track_'+str(track))
            require(int(prepared['deck'].par.Customwidth)==960 and int(prepared['deck'].par.Customheight)==180,'panoramic_deck_resolution_track_'+str(track))
            fixture=prepared['deck'].create(td.selectTOP,'panorama_go_fixture')
            fixture.par.top=gradient.path
            fixture.outputConnectors[0].connect(prepared['deck'].op('source_image').inputConnectors[0])
            prepared['deck'].op('source_image').par.index=0
            host.par.Masterblackout=False
            ext.engine.go(0); ext.engine.tick(); ext.UpdateCueRouting()
            require(not ext.engine.errors and ext.tracks[track]['cue']['projection']=='panoramic','go_applies_route_track_'+str(track))
            for i in (1,2,3):
                require(abs(float(pixels(i)[0])-(i-.5)/3)<.02,'go_track_'+str(track)+'_channel_'+str(i))
            if track==2:
                for mode in ('show','identical','panoramic','independent'):
                    wall.par.Sourcemode=mode
                    require(np.allclose(wall_pixels(),(1/6,.5,5/6),atol=.02),'wall_go_channels_under_'+mode)
            ext.engine.stop()
        legacy_path=ROOT/'.imagefx/shows/current.json'
        if legacy_path.is_file():
            legacy=ext.model.validate_show(json.loads(legacy_path.read_text(encoding='utf-8')))
            first=next((i for i,c in enumerate(legacy['cues']) if c['kind']=='visual'),None)
            if first is not None:
                ext._replace_cues(legacy['cues']); ext.SelectCue(first+1)
                old_cue=copy.deepcopy(ext.document['cues'][first])
                previous=host.par.Cuechannels.eval(); host.par.Cuechannels='all'
                host.op('cue_projection_parameters').module.onValueChange(host.par.Cuechannels,previous)
                require(ext.document['cues'][first]==dict(old_cue,channels='all'),'older_show_channel_edit_preserves_look_and_timing')
                require(len(ext.document['cues'])==len(legacy['cues']),'older_show_cue_count_preserved')
                report['older_show_cues_checked']=len(legacy['cues'])
        require(not host.errors(recurse=True) and not host.warnings(recurse=True),'no_native_errors_or_warnings')
        require(original.ext.ShowControlExt.document==before,'original_cues_untouched')
        report['ok']=True
    except Exception:
        report['error']=traceback.format_exc()
    finally:
        sandbox.destroy()
        target=ROOT/'build/cue-projection/native-validation.json'
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(json.dumps(report,indent=2),encoding='utf-8')
    return report


if __name__=='__main__':
    print(json.dumps(validate(),indent=2))
