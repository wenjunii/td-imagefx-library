"""Native control/pixel/file/flicker coverage in a temporary copy; never saves TOE."""
from datetime import datetime, timezone
from pathlib import Path
import json
import traceback
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
REPORT_PATH = ROOT / "build/envoy-validation/layer-composite.json"


def validate(write_report=True):
    scope = {}
    path = ROOT / "touchdesigner/scripts/layer_composite.py"
    exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), scope)
    module = op("/project1/imagefx_demo/layer_composite")
    if module is None:
        raise RuntimeError("Build Layer Composite first")
    host = op("/project1").create(baseCOMP, "layer_composite_qa")
    checks, controls = {}, {}
    report = dict(validator="layer-composite", generated_at=datetime.now(timezone.utc).isoformat(), ok=False)
    try:
        test = host.copy(module, name="test")
        def fixture(name, width, height, expression):
            code = host.create(textDAT, name + "_code")
            code.text = "layout(location=0) out vec4 fragColor; void main(){vec2 uv=vUV.st; fragColor=TDOutputSwizzle("+expression+");}"
            node = host.create(glslTOP, name)
            node.par.pixeldat = node.relativePath(code)
            node.par.outputresolution = "custom"
            node.par.resolutionw, node.par.resolutionh = width, height
            node.par.compilebehavior = "stalluntildone"
            return node
        back = fixture("back", 160, 90, "vec4(.1+uv.x*.3,.2+uv.y*.2,.65,.8)")
        top = fixture("top", 80, 80, "vec4(.25+uv.x*.5,.1+uv.y*.3,.2,.65)")
        back.outputConnectors[0].connect(test.inputConnectors[0])
        top.outputConnectors[0].connect(test.inputConnectors[1])

        folder=REPORT_PATH.parent; folder.mkdir(parents=True,exist_ok=True)
        top_path=folder/"layer-top-fixture.png"; back_path=folder/"layer-backdrop-fixture.png"
        top.save(str(top_path)); back.save(str(back_path))
        output = test.op("out1_image")
        shader = test.op("effect_glsl_layer_composite")
        resolution_exprs=(shader.par.resolutionw.expr,shader.par.resolutionh.expr)
        shader.par.resolutionw=160; shader.par.resolutionh=90
        defaults = {}
        for d in scope["PARAMETERS"]:
            if d.get("read_only") or d["type"] == "pulse":
                continue
            if d["type"] in ("rgb", "xy"):
                defaults.update({d["name"]+suffix:value for suffix,value in zip(d["type"],d["default"])})
            else:
                defaults[d["name"]] = d["default"]
        defaults.update(Enabled=True, Autotime=False, Manualtime=.25)
        def reset(**values):
            for name,value in dict(defaults, **values).items():
                test.par[name].val = value
        def capture(node=output):
            node.cook(force=True)
            pixels = node.numpyArray(delayed=False)
            if pixels is None:
                pixels = node.numpyArray(delayed=False)
            if pixels is None or not np.isfinite(pixels).all() or shader.errors():
                raise AssertionError("Invalid layer pixels / shader: " + str(shader.errors()))
            return np.array(pixels, dtype=np.float32, copy=True)
        def diff(a,b):
            return float(np.mean(np.abs(a-b)))

        reset(Topfit="stretch")
        default = capture()
        b = capture(back)
        checks["two_inputs_visible"] = diff(default,b) > .01
        # A constant foreground gives an analytic check of straight-alpha Over.
        constant = fixture("constant",160,90,"vec4(.7,.3,.1,.5)")
        constant.outputConnectors[0].connect(test.inputConnectors[1])
        expected_alpha=.5+b[:,:,3]*.5
        expected_rgb=(np.array([.7,.3,.1])*.5+b[:,:,:3]*b[:,:,3:4]*.5)/expected_alpha[:,:,None]
        actual=capture()
        checks["straight_alpha_over"] = bool(np.allclose(actual[:,:,:3],expected_rgb,atol=.015) and np.allclose(actual[:,:,3],expected_alpha,atol=.01))
        test.par.Invert=True
        expected_rgb=(np.array([.3,.7,.9])*.5+b[:,:,:3]*b[:,:,3:4]*.5)/expected_alpha[:,:,None]
        checks["inversion_foreground_only"] = bool(np.allclose(capture()[:,:,:3],expected_rgb,atol=.015))
        top.outputConnectors[0].connect(test.inputConnectors[1])

        ranges = {"Hue":(-50.,70.), "Rotation":(-30.,40.), "Positionx":(-.2,.2),
                  "Positiony":(-.2,.2), "Scale":(.55,1.4), "Phase":(0.,.6),
                  "Manualtime":(.1,.8), "Seed":(2,81)}
        flicker_names={"Flickerenabled","Flickermode","Flickerrate","Flickerduty","Flickermin",
                       "Flickersoftness","Phase","Seed","Autotime","Timescale","Manualtime"}
        transport_names={prefix+suffix for prefix in ("Backdrop","Top") for suffix in ("play","loop","speed","in")}
        checks["viewer_targets_own_output"] = module.par.opviewer.eval()==module.op("out1_image")
        checks["copied_viewer_targets_own_output"] = test.par.opviewer.eval()==output
        checks["viewer_enabled"] = module.viewer
        for par in test.customPars:
            if par.readOnly:
                checks[par.name+"_readonly"] = par.name in ("Time","Routingstatus","Backdropstatus","Topstatus") and bool(par.expr)
                checks[par.name+"_evaluates"] = isinstance(par.eval(), (str,float,int))
                continue
            if par.isPulse or par.name in transport_names:
                continue
            if par.name in ("Backdropfile","Topfile","Backdropsource","Topsource"):
                continue
            reset(Flickerenabled=par.name in flicker_names)
            back.par.resolutionw,back.par.resolutionh=160,90
            if par.name=="Backdropfit":
                # Decouple source aspect from canvas in this temporary test.
                back.par.resolutionw,back.par.resolutionh=80,80
            if par.name=="Seed": test.par.Flickermode="random"
            if par.name=="Flickersoftness": test.par.Flickermode="soft"
            if par.name=="Autotime":
                test.par.Timescale=0.; test.par.Manualtime=.8
            if par.name=="Timescale": test.par.Autotime=True
            if par.isMenu: values=list(par.menuNames)
            elif par.isToggle: values=[False,True]
            else:
                values=list(ranges.get(par.name,(par.min,par.max)))
                if par.name=="Timescale": values=[0.,.8/max(absTime.seconds,1.)]
                if par.name=="Seed": values=[int(v) for v in values]
                checks[par.name+"_range"] = par.min<par.max and par.normMin<par.normMax and par.clampMin and par.clampMax
                for endpoint in (par.min,par.max):
                    par.val=int(endpoint) if par.name=="Seed" else endpoint
                    checks[par.name+"_endpoint_"+str(endpoint)] = abs(par.eval()-endpoint)<1e-5
                    capture()
            images=[]; accepted=[]
            for value in values:
                par.val=value
                accepted.append(par.eval()==value if isinstance(value,(str,bool,int)) else abs(par.eval()-value)<1e-5)
                sequence=[]
                times=(.07,.33,.66,1.02,2.14,3.39,6.28,7.87) if par.name in flicker_names-{"Manualtime","Autotime","Timescale"} else (None,)
                if par.name=="Seed": times=tuple(i+.25 for i in range(32))
                for time in times:
                    if time is not None: test.par.Manualtime=time
                    sequence.append(capture())
                images.append(np.stack(sequence))
            changes=[diff(images[i],images[j]) for i in range(len(images)) for j in range(i+1,len(images))]
            controls[par.name]=dict(values=values,accepted=accepted,differences=changes)
            checks[par.name+"_accepts"] = all(accepted)
            checks[par.name+"_visible"] = all(v>1e-7 for v in changes)

        reset(Enabled=False)
        checks["disabled_exact_bypass"] = diff(capture(),capture(back))<1e-7
        reset(Opacity=0.)
        checks["zero_opacity_preserves_backdrop"] = diff(capture(),capture(back))<1e-7
        reset(Flickerenabled=False)
        first=capture(); test.par.Manualtime=9.7
        checks["flicker_off_is_steady"] = np.array_equal(first,capture())
        reset(Flickerenabled=True,Flickerrate=1.,Manualtime=.1)
        on=capture(); test.par.Manualtime=.8
        checks["flicker_off_phase_is_backdrop"] = diff(capture(),capture(back))<1e-7
        test.par.Manualtime=1.1
        checks["regular_period_repeat"] = np.array_equal(on,capture())
        reset(Flickerenabled=True,Flickermode="random",Manualtime=2.3)
        first=capture(); test.par.Manualtime=7.8; capture(); test.par.Manualtime=2.3
        checks["random_seek_repeatable"] = np.array_equal(first,capture())
        reset(Flickerenabled=True,Flickerrate=0.)
        first=capture(); test.par.Manualtime=99.
        checks["zero_rate_freezes"] = np.array_equal(first,capture())
        for mode in ("regular","soft","random"):
            reset(Flickerenabled=True,Flickermode=mode,Flickerduty=0.)
            checks[mode+"_zero_duty"] = diff(capture(),capture(back))<1e-7
            test.par.Flickerduty=1.; first=capture(); test.par.Flickerenabled=False
            checks[mode+"_full_duty"] = np.array_equal(first,capture())
        reset(Topfit="contain")
        checks["contain_preserves_backdrop_edges"] = bool(np.allclose(capture()[:,0],b[:,0],atol=1e-7))
        test.inputConnectors[1].disconnect()
        reset()
        checks["missing_top_is_transparent"] = diff(capture(),capture(back))<1e-7

        # File-picker values and routing are synchronous. Actual decoded pixels
        # are tested separately by validate_files() on real TD frames.
        reset(Topfile=str(top_path),Backdropfile=str(back_path))
        checks["file_picker_bindings"] = all(test.op(node).par.file.eval()==str(path) for node,path in (("top_file",top_path),("backdrop_file",back_path)))
        checks["file_priority"] = test.op("top_source").par.index.eval()==2 and test.op("backdrop_source").par.index.eval()==2
        controls["Topfile"]={"path_bound":True}; controls["Backdropfile"]={"path_bound":True}
        for prefix in ("Backdrop","Top"):
            values=list(test.par[prefix+"source"].menuNames)
            indices=[]
            for value in values:
                test.par[prefix+"source"]=value
                indices.append(test.op(prefix.lower()+"_source").par.index.eval())
            controls[prefix+"source"]={"values":values,"indices":indices}
            checks[prefix+"_sources_route"] = indices==[2,3,0,2,0]
        # The processed result can be used as foreground while the backdrop is
        # transparent, even if an unused file field still contains a path.
        reset(Backdropsource="transparent",Topsource="effects",Topfile="unused.png",Topfit="stretch")
        checks["effects_result_as_foreground"] = diff(capture(),b)<.005
        checks["unused_top_file_not_loaded"] = test.op("top_file").par.file.eval()==""
        reset(Backdropsource="effects",Topsource="transparent",Backdropfile="unused.png")
        checks["effects_result_as_backdrop"] = diff(capture(),b)<.005
        checks["unused_backdrop_file_not_loaded"] = test.op("backdrop_file").par.file.eval()==""
        reset()
        checks["clear_file_restores_input"] = diff(capture(),b)<1e-7
        for prefix in ("Backdrop","Top"):
            reader=test.op(prefix.lower()+"_file")
            for suffix,field,values in (("play","play",[False,True]),("loop","textendright",[False,True]),
                                        ("speed","speed",[-4.,4.]),("in","cuepoint",[0.,86400.])):
                reset(Autotime=True)
                par=test.par[prefix+suffix]
                accepted=[]
                if suffix in ("speed","in"):
                    checks[par.name+"_range"]=par.min<par.max and par.normMin<par.normMax and par.clampMin and par.clampMax
                for value in values:
                    par.val=value
                    expected=("cycle" if value else "hold") if suffix=="loop" else value
                    accepted.append(reader.par[field].eval()==expected)
                checks[par.name+"_binding"] = all(accepted)
                controls[par.name] = dict(values=values,accepted=accepted)
            reset(Autotime=False,Manualtime=2.)
            test.par[prefix+"in"]=3.; test.par[prefix+"speed"]=-.5
            checks[prefix+"_manual_index"] = reader.par.index.eval()==2. and reader.par.playmode.eval()=="specify" and bool(reader.par.play)
            checks[prefix+"_manual_transport_disabled"] = not test.par[prefix+"play"].enable and not test.par[prefix+"restart"].enable
        reset()
        pulses=[p.name for p in test.customPars if p.isPulse]
        callback=test.op("media_callbacks")
        checks["pulse_dispatch_configured"] = callback.par.onpulse.eval() and all(name in callback.par.pars.eval().split() for name in pulses)
        checks["all_controls_covered"] = set(controls)=={p.name for p in test.customPars if not p.readOnly and not p.isPulse}
        checks["demo_binding"] = module.par.Enabled.expr=="parent().par.Layercompositeenabled"
        checks["demo_chain"] = module.inputs[0]==op("/project1/imagefx_demo/video_fx_router") and op("/project1/imagefx_demo/final_crop").inputs[0]==module.op("out1_image")
        top.outputConnectors[0].connect(test.inputConnectors[1])
        shader.par.resolutionw.expr,shader.par.resolutionh.expr=resolution_exprs
        back.par.resolutionw,back.par.resolutionh=640,360
        reset()
        capture(); output.save(str(folder/"layer-composite-preview.png"))
        test.par.Invert=True
        capture(); output.save(str(folder/"layer-composite-inverted-preview.png"))
        reset()
        for width,height in ((1920,1080),(3840,2160)):
            back.par.resolutionw,back.par.resolutionh=width,height
            checks[str(width)+"x"+str(height)] = capture().shape[:2]==(height,width)
        report.update(checks=checks,controls=controls,control_count=len(controls),pulse_count=len(pulses),ok=all(checks.values()))
    except Exception:
        report.update(checks=checks,controls=controls,error=traceback.format_exc())
    finally:
        host.destroy()
    if write_report:
        REPORT_PATH.parent.mkdir(parents=True,exist_ok=True)
        REPORT_PATH.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    return report


def validate_files():
    """Schedule decoded image/alpha checks; writes layer-composite-files.json."""
    import time
    module=op("/project1/imagefx_demo/layer_composite")
    host=op("/project1").create(baseCOMP,"layer_files_qa")
    test=host.copy(module,name="test")
    test.par.Enabled=True; test.par.Autotime=False; test.par.Flickerenabled=False
    test.par.Topfit="stretch"; test.par.Backdropfit="stretch"
    canvas=host.create(constantTOP,"canvas")
    canvas.par.resolutionw=160; canvas.par.resolutionh=90
    canvas.outputConnectors[0].connect(test.inputConnectors[0])
    folder=REPORT_PATH.parent
    test.par.Topfile=str(folder/"layer-top-fixture.png")
    test.par.Backdropfile=str(folder/"layer-backdrop-fixture.png")
    for name in ("backdrop_file","top_file"): test.op(name).preload()
    test.op("out1_image").cook(force=True)
    started=time.monotonic()
    report={"ok":False,"checks":{},"generated_at":datetime.now(timezone.utc).isoformat()}
    def pixels(node):
        node.cook(force=True)
        return np.array(node.numpyArray(delayed=False),dtype=np.float32,copy=True)
    def advance():
        try:
            readers=[test.op(name) for name in ("backdrop_file","top_file")]
            test.op("out1_image").cook(force=True)
            for reader in readers: reader.cook(force=True)
            if any(reader.isInvalid for reader in readers): raise RuntimeError("Image decode failed")
            if not all(reader.isFullyPreRead for reader in readers):
                if time.monotonic()-started>15: raise RuntimeError("Image decode timed out")
                run("args[0]()",advance,delayFrames=1); return
            back=pixels(readers[0]); top=pixels(readers[1]); actual=pixels(test.op("out1_image"))
            # Check file colors/alpha, not merely whether a placeholder differs.
            expected_back=np.array([.1+.3*(80.5/160),.2+.2*(45.5/90),.65,.8])
            expected_top=np.array([.25+.5*(40.5/80),.1+.3*(40.5/80),.2,.65])
            report["checks"]["backdrop_file_color_alpha"]=bool(np.allclose(back[45,80],expected_back,atol=.015))
            report["checks"]["top_file_color_alpha"]=bool(np.allclose(top[40,40],expected_top,atol=.015))
            a=expected_top[3]; ba=expected_back[3]; alpha=a+ba*(1-a)
            rgb=(expected_top[:3]*a+expected_back[:3]*ba*(1-a))/alpha
            report["checks"]["transparent_png_over"]=bool(np.allclose(actual[45,80],np.r_[rgb,alpha],atol=.02))
            report["samples"]={"back":back[45,80].tolist(),"top":top[40,40].tolist(),"composite":actual[45,80].tolist()}
            test.par.Opacity=0
            report["checks"]["zero_opacity_preserves_file_backdrop"]=bool(np.allclose(pixels(test.op("out1_image")),back,atol=.005))
            report["ok"]=all(report["checks"].values())
        except Exception:
            report["error"]=traceback.format_exc()
        finally:
            if report.get("checks") or report.get("error"):
                (folder/"layer-composite-files.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
                host.destroy()
                print("Layer file QA:",report)
    run("args[0]()",advance,delayFrames=1)


def validate_videos():
    """Frame-based video transport checks; requires the local show AV fixture."""
    import time
    folder=REPORT_PATH.parent
    path=folder/"show-av-fixture.mp4"
    if not path.is_file():
        raise RuntimeError("Generate build/envoy-validation/show-av-fixture.mp4 first")
    host=op("/project1").create(baseCOMP,"layer_video_qa")
    test=host.copy(op("/project1/imagefx_demo/layer_composite"),name="test")
    test.par.Enabled=True; test.par.Autotime=False; test.par.Manualtime=0
    test.par.Topfile=str(path); test.par.Backdropfile=str(path)
    test.par.Flickerenabled=False; test.par.Opacity=.5
    test.op("effect_glsl_layer_composite").par.resolutionw=160
    test.op("effect_glsl_layer_composite").par.resolutionh=90
    readers=[test.op(name+"_file") for name in ("backdrop","top")]
    for reader in readers: reader.preload()
    report=dict(ok=False,checks={},generated_at=datetime.now(timezone.utc).isoformat())
    checks=report["checks"]
    def pixels(node):
        node.cook(force=True)
        return np.array(node.numpyArray(delayed=False),dtype=np.float32,copy=True)
    def snapshot(): return [pixels(r) for r in readers]
    def different(a,b): return all(float(np.mean(np.abs(x-y)))>1e-4 for x,y in zip(a,b))
    def equal(a,b): return all(np.allclose(x,y,atol=.002) for x,y in zip(a,b))
    def sequence():
        started=time.monotonic()
        while not all(r.isOpen and r.isFullyPreRead for r in readers):
            if any(r.isInvalid for r in readers) or time.monotonic()-started>20:
                raise RuntimeError("Video decode failed or timed out")
            yield
        for _ in range(3): yield
        zero=snapshot()
        checks["both_video_files_ready"]=all("Ready:" in test.par[p+"status"].eval() for p in ("Backdrop","Top"))
        test.par.Manualtime=.7
        for _ in range(3): yield
        later=snapshot(); checks["both_videos_seek"]=different(zero,later)
        for _ in range(3): yield
        checks["manual_clock_pauses_both"]=equal(later,snapshot())
        # The standard local show AV fixture has exactly 90 frames at 30 fps.
        test.par.Manualtime=3.7
        for _ in range(3): yield
        checks["loop_on_repeats_video_frames"]=equal(later,snapshot())
        test.par.Manualtime=.3
        test.par.Backdropin=1.; test.par.Topin=1.
        test.par.Backdropspeed=-1.; test.par.Topspeed=-1.
        for _ in range(3): yield
        checks["reverse_speed_and_start_offset"]=equal(later,snapshot())
        test.par.Manualtime=10000.; test.par.Backdroploop=False; test.par.Toploop=False
        test.par.Backdropin=0.; test.par.Topin=0.; test.par.Backdropspeed=1.; test.par.Topspeed=1.
        for _ in range(3): yield
        end=snapshot(); test.par.Manualtime=20000.
        for _ in range(3): yield
        checks["loop_off_holds_last_frame"]=equal(end,snapshot()) and different(zero,end)
        test.par.Backdroploop=True; test.par.Toploop=True; test.par.Manualtime=0
        for _ in range(3): yield
        test.par.Autotime=True
        test.par.Backdroprestart.pulse(); test.par.Toprestart.pulse()
        for _ in range(2): yield
        moving=snapshot()
        for _ in range(4): yield
        checks["sequential_both_play"]=different(moving,snapshot())
        test.par.Backdropplay=False; test.par.Topplay=False
        for _ in range(3): yield
        paused=snapshot()
        for _ in range(4): yield
        checks["sequential_both_pause"]=equal(paused,snapshot())
        test.par.Backdroprestart.pulse(); test.par.Toprestart.pulse()
        for _ in range(3): yield
        checks["both_restart_buttons"]=equal(zero,snapshot())
        # Change one transport at a time: a shared binding must not pass just
        # because both files happened to move or stop together.
        baseline=snapshot(); test.par.Topplay=True
        for _ in range(4): yield
        current=snapshot()
        checks["top_play_is_independent"]=equal(baseline[:1],current[:1]) and different(baseline[1:],current[1:])
        test.par.Topplay=False; test.par.Backdropplay=True
        for _ in range(3): yield
        baseline=snapshot()
        for _ in range(4): yield
        current=snapshot()
        checks["backdrop_play_is_independent"]=different(baseline[:1],current[:1]) and equal(baseline[1:],current[1:])
        test.par.Topplay=True; test.par.Topspeed=0.; test.par.Backdropspeed=0.
        for _ in range(3): yield
        baseline=snapshot()
        for _ in range(4): yield
        checks["zero_speed_holds_both"]=equal(baseline,snapshot())
        test.par.Topplay=False; test.par.Backdropplay=False
        test.par.Topspeed=1.; test.par.Backdropspeed=1.
        test.par.Topin=.7; test.par.Backdropin=.7
        for _ in range(3): yield
        checks["start_controls_seek_while_paused"]=equal(later,snapshot())
        test.par.Topin=0.; test.par.Backdropin=0.
        for _ in range(3): yield
        checks["start_controls_seek_back_to_zero"]=equal(zero,snapshot())
        test.par.Backdropreload.pulse(); test.par.Topreload.pulse()
        for _ in range(5): yield
        checks["both_reload_buttons"]=all(r.isOpen and r.isFullyPreRead and not r.isInvalid for r in readers)
        test.par.Topfile=str(folder/"layer-top-fixture.png")
        for _ in range(5): yield
        checks["mixed_image_and_video"]=readers[1].width==80 and readers[0].isOpen and float(np.std(pixels(test.op("out1_image"))[:,:,:3]))>.01
        checks["module_no_errors"]=not test.errors(recurse=True)
        test.par.Topfile=str(folder/"intentionally-missing-layer-file.mp4")
        for _ in range(5): yield
        checks["missing_file_status"]=test.par.Topstatus.eval().startswith("ERROR:")
        report["ok"]=all(checks.values())
    steps=sequence()
    def advance():
        try:
            test.op("out1_image").cook(force=True)
            next(steps)
        except StopIteration:
            finish()
        except Exception:
            report["error"]=traceback.format_exc(); finish()
        else:
            run("args[0]()",advance,delayMilliSeconds=200)
    def finish():
        (folder/"layer-composite-videos.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
        host.destroy()
        print("Layer video QA:",report)
    run("args[0]()",advance,delayFrames=1)


if __name__=="__main__":
    print(json.dumps(validate(),indent=2))
