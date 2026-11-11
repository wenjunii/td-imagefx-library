"""One geometry contract for Show Control; no cue/transport mutations."""
import inspect

SECTIONS = ('Transport', 'Pre-Show Check', 'Output Mode', 'Wall Output', 'Projection Mapping',
            'Cue Editor', 'Cue Notes', 'Look Editor', 'Projector Review',
            'Export Video', 'Routing', 'Output 1', 'Output 2', 'Output 3')


def select_section(show):
    """Refresh the native control list, not just its Page Scope expression.

    Parameter COMP caches its list when page names are hidden. Changing the
    expression's result alone leaves the previously displayed controls in place.
    Rebind the same operator after selecting the quoted page name. This only
    changes the inspector; it never changes cues, playback, or effect values.
    """
    nav = show.op('inspector_navigation')
    inspector = show.op('cue_inspector')
    if nav is None or inspector is None:
        return
    section = nav.par.Section.eval()
    if section not in SECTIONS:
        raise ValueError('Unknown Show Control section: ' + str(section))
    if section not in [p.name for p in show.customPages]:
        raise ValueError('Show Control page is missing: ' + section)
    inspector.par.pagescope = repr(section)
    inspector.par.pageindex = 0
    inspector.par.pagenames = False
    inspector.par.syncpage = False
    inspector.par.op = ''
    inspector.cook(force=True)
    inspector.par.op = '..'
    inspector.cook(force=True)


def rectangles():
    boxes = {
        'cue_column_heading': (20, 676, 490, 20),
        'notes_column_heading': (520, 676, 380, 20),
        'help': (20, 282, 684, 24),
        'look_help_0': (20, 254, 684, 24),
        'look_help_1': (20, 230, 684, 22),
        'look_preview_panel': (724, 198, 176, 99),
        'review_heading': (20, 174, 880, 22),
        'button_openprojectorreview': (20, 198, 282, 28),
        'button_startexport': (322, 198, 282, 28),
        'inspector_selector': (920, 746, 720, 40),
        'cue_inspector': (920, 20, 720, 716),
    }
    for row in range(12):
        boxes['cue_row_'+str(row)] = (20, 651-row*23, 490, 21)
        boxes['cue_notes_'+str(row)] = (520, 651-row*23, 380, 21)
    for row, actions in enumerate((('Gocue','Goback','Pause','Resume','Stopall'),
                                   ('Preload','Addcue','Addblackout','Applycue','Capturelook'))):
        for col, action in enumerate(actions): boxes['action:'+action]=(20+col*178,746-row*46,170,40)
    for col, action in enumerate(('Recalllook','Updatelook','Savelookasnew','Cancellook')):
        boxes['action:'+action]=(20+col*224,348,216,38)
    for action,x,w in (('Showlooklive',20,214),('Stoplooklive',244,188),
                       ('Opencuenotes',442,182),('Editrunninglook',634,266)):
        boxes['action:'+action]=(x,310,w,30)
    return boxes


def configure(show):
    for name, box in rectangles().items():
        if name.startswith('action:'):
            item=next((n for n in show.children if n.fetch('show_action',None,search=False)==name[7:]),None)
        else: item=show.op(name)
        if item is not None:
            for axis,value in zip('xywh',box): item.par[axis]=value
    for i in (2,3):
        if show.op('look_help_'+str(i)) is not None: show.op('look_help_'+str(i)).par.display=False
    help_node=show.op('help')
    if help_node is not None:
        help_node.par.fontsize=12; help_node.par.wordwrap=False
        help_node.par.text.expr="parent().LiveLookStatus()[:110]"
    for name in ('look_help_0','look_help_1'):
        item=show.op(name)
        if item is not None: item.par.fontsize=12; item.par.wordwrap=False
    panel=show.op('projector_review_panel')
    if panel is not None: panel.par.y=8
    inspector=show.op('cue_inspector')
    if inspector is not None and show.op('inspector_navigation') is not None:
        select_section(show)


def install(show):
    import td
    nav=show.op('inspector_navigation') or show.create(td.baseCOMP,'inspector_navigation')
    nav.name='inspector_navigation'
    if nav.par['Section'] is None:
        page=nav.appendCustomPage('Navigation')
        parameter=page.appendMenu('Section',label='Show Control Section')[0]
        parameter.menuNames=list(SECTIONS); parameter.menuLabels=list(SECTIONS)
        parameter.default=parameter.val='Transport'
    selected=nav.par.Section.eval()
    nav.par.Section.menuNames=list(SECTIONS); nav.par.Section.menuLabels=list(SECTIONS)
    nav.par.Section.val=selected if selected in SECTIONS else 'Transport'
    picker=show.op('inspector_selector') or show.create(td.parameterCOMP,'inspector_selector')
    picker.name='inspector_selector'
    picker.par.op='inspector_navigation'; picker.par.builtin=False; picker.par.custom=True
    picker.par.parscope='Section'; picker.par.pagenames=False; picker.par.header=False
    runtime=show.op('show_panel_layout') or show.create(td.textDAT,'show_panel_layout')
    runtime.name='show_panel_layout'
    runtime.text='SECTIONS = {!r}\n\n'.format(SECTIONS)+'\n\n'.join(
        inspect.getsource(fn) for fn in (select_section,rectangles,configure))
    callback=show.op('inspector_navigation_callbacks') or show.create(td.parameterexecuteDAT,'inspector_navigation_callbacks')
    callback.par.active=False
    callback.par.op='inspector_navigation'
    callback.par.pars='Section'
    callback.par.custom=True; callback.par.builtin=False
    callback.par.valuechange=True; callback.par.onpulse=False
    callback.text="def onValueChange(par, prev):\n    parent().op('show_panel_layout').module.select_section(parent())\n"
    callback.par.active=True
    configure(show)
    return runtime
