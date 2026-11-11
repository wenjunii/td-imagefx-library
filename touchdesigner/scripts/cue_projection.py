"""Per-cue routing before projector calibration, independent of display delivery."""
from pathlib import Path

ROUTES = ('inherit', 'p1', 'p2', 'p3', 'p1_p2', 'p1_p3', 'p2_p3', 'all', 'panoramic')
LABELS = ('Follow Show Routing', 'Projector 1 (Left)', 'Projector 2 (Center)',
          'Projector 3 (Right)', 'Projectors 1 + 2', 'Projectors 1 + 3',
          'Projectors 2 + 3', 'All Three (Identical)', 'All Three (Panoramic)')
SHOW_MODES = ('cue', 'identical', 'panoramic', 'independent')
SHOW_LABELS = ('Follow Show Routing (Per Cue)', 'Identical (fallback)',
               'Panoramic (fallback)', 'Independent (fallback)')
CHANNELS = ('routing','1','2','3','1_2','1_3','2_3','all')
CHANNEL_LABELS = ('Use Projection Routing','Channel 1 (Left)','Channel 2 (Center)',
                  'Channel 3 (Right)','Channels 1 + 2','Channels 1 + 3',
                  'Channels 2 + 3','All Three Channels')


def routing_expression(value):
    # Merely returning a Par object in a discarded tuple element does not read
    # its value. TD can then retain the stopped-show fallback selector/uniform
    # across GO. Explicit eval registers the revision dependency for every path.
    return '(parent().par.Cueroutingrevision.eval(), {})[1]'.format(value)


SHADER = r'''
layout(location=0) out vec4 fragColor;
uniform vec4 uBlend, uSide0, uSide1;
void main() {
    vec2 a = vec2(mix(uSide0.y, uSide0.z, vUV.x), vUV.y);
    vec2 b = vec2(mix(uSide1.y, uSide1.z, vUV.x), vUV.y);
    vec4 c0 = texture(sTD2DInputs[0], a) * uSide0.x;
    vec4 c1 = texture(sTD2DInputs[1], b) * uSide1.x;
    fragColor = TDOutputSwizzle(mix(c0, c1, uBlend.x) * uBlend.y * uBlend.z);
}
'''


def install(show):
    """Idempotent graph/UI patch. No cues, files, windows or safety gates changed."""
    import td
    selected_mode = show.par.Routingmode.eval()
    for name in ('Routingmode', 'Outputlayout'):
        p = show.par[name]
        if p is not None:
            p.menuNames, p.menuLabels = list(SHOW_MODES), list(SHOW_LABELS)
    show.par.Routingmode = selected_mode if selected_mode in SHOW_MODES else 'cue'
    show.par.Sharedtrack.enableExpr = "me.par.Routingmode in ('identical', 'panoramic')"
    show.par.Outputsharedtrack.enableExpr = show.par.Sharedtrack.enableExpr
    page = next(p for p in show.customPages if p.name == 'Cue Editor')
    show.par.Track.label = 'Playback / Audio Track (not output channel)'
    if show.par['Cuechannels'] is None:
        p=page.appendMenu('Cuechannels',label='Visual Output Channels')[0]
        p.menuNames,p.menuLabels=list(CHANNELS),list(CHANNEL_LABELS)
        p.default=p.val='routing'
    selected_channels=show.par.Cuechannels.eval()
    show.par.Cuechannels.menuNames,show.par.Cuechannels.menuLabels=list(CHANNELS),list(CHANNEL_LABELS)
    show.par.Cuechannels=selected_channels if selected_channels in CHANNELS else 'routing'
    show.par.Cuechannels.enableExpr="me.par.Cuekind == 'visual'"
    if show.par['Cueprojection'] is None:
        p = page.appendMenu('Cueprojection', label='Projection Routing')[0]
        p.menuNames, p.menuLabels = list(ROUTES), list(LABELS)
        p.default = p.val = 'inherit'
    selected = show.par.Cueprojection.eval()
    show.par.Cueprojection.menuNames, show.par.Cueprojection.menuLabels = list(ROUTES), list(LABELS)
    show.par.Cueprojection = selected if selected in ROUTES else 'inherit'
    show.par.Cueprojection.enableExpr = "me.par.Cuekind == 'visual'"
    if show.par['Cueprojectionhelp'] is None:
        p = page.appendStr('Cueprojectionhelp', label='Routing Help')[0]
        p.readOnly = True
    show.par.Cueprojectionhelp = 'Channels choose destinations, not playback tracks. Panorama spans those channels. Save Show writes to disk.'
    callback = show.op('cue_projection_parameters') or show.create(td.parameterexecuteDAT, 'cue_projection_parameters')
    callback.par.active = False
    callback.par.op = '..'
    callback.par.pars = 'Cueprojection Cuechannels'
    callback.par.custom, callback.par.builtin = True, False
    callback.par.valuechange, callback.par.onpulse = True, False
    callback.text = '''def onValueChange(par, prev):
    ext = parent().ext.ShowControlExt
    if ext._busy: return
    try:
        ext.SetCueProjection(par.name)
    except Exception as exc:
        ext._busy = True
        try: par.val = prev
        finally: ext._busy = False
        ext._status(str(exc))
'''
    names = [p.name for p in page.pars if p.name not in {'Cuechannels','Cueprojection', 'Cueprojectionhelp'}]
    position = names.index('Track') + 1
    names[position:position] = ['Cuechannels','Cueprojection', 'Cueprojectionhelp']
    page.sort(*names)
    if show.par['Cueroutingrevision'] is None:
        runtime_page = next(p for p in show.customPages if p.name == 'Runtime')
        p = runtime_page.appendInt('Cueroutingrevision', label='Cue Routing Revision')[0]
        p.default = p.val = 0
        p.readOnly = True
    code = show.op('cue_projection') or show.create(td.textDAT, 'cue_projection')
    code.text = SHADER
    for output in (1, 2, 3):
        shader = show.op('cue_projection' + str(output)) or show.create(td.glslTOP, 'cue_projection' + str(output))
        shader.par.pixeldat = 'cue_projection'
        shader.par.glslversion = 'glsl460'
        shader.par.outputresolution = 'custom'
        shader.par.resolutionw.expr = 'int(parent().par.Renderwidth)'
        shader.par.resolutionh.expr = 'int(parent().par.Renderheight)'
        shader.seq.vec.numBlocks = 3
        shader.par.vec0name = 'uBlend'
        for component, axis in enumerate('xyz'):
            shader.par['vec0value' + axis].expr = routing_expression('parent().ProjectionBlend({}, {})'.format(output, component))
        for side in (0, 1):
            source = show.op('cue_projection{}_source{}'.format(output, side)) or show.create(td.selectTOP, 'cue_projection{}_source{}'.format(output, side))
            source.par.top.expr = routing_expression('parent().ProjectionInput({}, {})'.format(output, side))
            source.outputConnectors[0].connect(shader.inputConnectors[side])
            shader.par['vec{}name'.format(side + 1)] = 'uSide' + str(side)
            for component, axis in enumerate('xyz'):
                shader.par['vec{}value{}'.format(side + 1, axis)].expr = routing_expression('parent().ProjectionSample({}, {})[{}]'.format(output, side, component))
        # Replace the old expression, not only its dormant constant value. The
        # old expression could return after saving/reopening or changing mode.
        destination = show.op('output_source' + str(output)).par.top
        destination.expr = repr(shader.name)
        destination.mode = type(destination.mode).EXPRESSION
        show.op('track' + str(output)).par.resolutionw.expr = routing_expression('parent().TrackCanvasWidth({})'.format(output))
    # Cue routing already slices panorama; mapping must apply calibration once.
    ext = show.ext.ShowControlExt
    ext.UpdateCueRouting()
    ext._mapping_key = None
    ext.UpdateMapping()
    wall=show.parent().op('wall_output')
    if wall is not None:
        root=Path(__file__).resolve().parents[2]
        wall.op('controller').text=(root/'touchdesigner/scripts/wall_output_controller.py').read_text(encoding='utf-8')
        for i in (1,2,3):
            wall.op('projector'+str(i)).par.vec0valuex.expr="int(parent().op('controller').module.effective_source_mode(parent()) == 'panoramic')"
            mapping=wall.op('projection_map'+str(i))
            if mapping is not None:
                mapping.par.vec11valuex.expr="int(parent().op('controller').module.effective_source_mode(parent()) == 'show' and not parent().par.Testpattern)"
    callback.par.active = True
    return {'routes': list(ROUTES), 'physical_outputs_unchanged': True}


def upgrade(show=None):
    """Upgrade a stopped show in-place without replacing its personal document."""
    import copy
    import importlib
    import td
    root = Path(__file__).resolve().parents[2]
    show = show or td.op('/project1/imagefx_demo/show_control')
    if show is None:
        raise RuntimeError('Open the main ImageFX project first')
    previous = show.ext.ShowControlExt
    if (previous.engine.state != 'stopped' or previous.tracks or previous.prepared
            or previous._look_edit is not None or show.fetch('imagefx_export_job', None, search=False)):
        raise RuntimeError('Stop All, finish export and finish/cancel Look Editor before upgrading cue routing')
    before = copy.deepcopy(previous.document)
    selected = int(show.par.Selectedcue)
    # Snapshot all pre-existing artist controls, including expression/bind modes.
    saved = {p.name: (p.eval(), p.expr, p.bindExpr, p.mode) for p in show.customPars
             if not p.isPulse and not p.readOnly and p.name not in {'Audioenabled', 'Masterblackout'}}
    importlib.reload(previous.model)
    # Add the selector before extension initialization calls SelectCue.
    page = next(p for p in show.customPages if p.name == 'Cue Editor')
    if show.par['Cueprojection'] is None:
        p = page.appendMenu('Cueprojection', label='Projection Routing')[0]
        p.menuNames, p.menuLabels = list(ROUTES), list(LABELS)
        p.default = p.val = 'inherit'
    if show.par['Cuechannels'] is None:
        p=page.appendMenu('Cuechannels',label='Visual Output Channels')[0]
        p.menuNames,p.menuLabels=list(CHANNELS),list(CHANNEL_LABELS)
        p.default=p.val='routing'
    show.op('ShowControlExt').text = (root / 'touchdesigner/extensions/ShowControlExt.py').read_text(encoding='utf-8')
    show.initializeExtensions()
    current = show.ext.ShowControlExt
    if current.document != current.model.validate_show(before):
        raise RuntimeError('Cue preservation check failed')
    install(show)
    output_mode = show.op('show_output_mode')
    if output_mode is not None:
        output_mode.text = (root / 'touchdesigner/scripts/show_output_mode.py').read_text(encoding='utf-8')
    review=show.op('show_review_export')
    if review is not None:
        review.text=(root/'touchdesigner/scripts/show_review_export.py').read_text(encoding='utf-8')
    for name, (value, expression, binding, mode) in saved.items():
        p = show.par[name]
        if p.eval() != value: p.val = value
        p.expr, p.bindExpr, p.mode = expression, binding, mode
    current.SelectCue(selected)
    current._save_document_dat()
    show.par.Masterblackout, show.par.Audioenabled = True, False
    layout = show.op('show_panel_layout')
    if layout is not None: layout.module.configure(show)
    current._status('Cue Editor > Visual Output Channels installed. Routing commits while stopped; Save Show writes to disk.')
    return {'ok': True, 'cues_preserved': len(before['cues']), 'default': 'inherit', 'toe_saved': False}
