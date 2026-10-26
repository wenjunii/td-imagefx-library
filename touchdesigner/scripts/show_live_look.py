"""Idempotent live-draft audition and cue-notes controls; no cue data mutations."""


def install_cue_notes_column(show):
    """Keep notes beside their cue, inside the existing 880-unit list area."""
    import td
    for name, label, x, width in (
            ('cue_column_heading', 'CUE / TYPE / TRACK / STATE', 20, 490),
            ('notes_column_heading', 'NOTES (edit in Cue Notes)', 520, 380)):
        heading = show.op(name) or show.create(td.textCOMP, name)
        heading.par.x, heading.par.y, heading.par.w, heading.par.h = x, 676, width, 20
        heading.par.text, heading.par.fontsize = label, 12
        heading.par.alignx = 'left'
    for row in range(12):
        cue = show.op('cue_row_{}'.format(row))
        cue.par.x, cue.par.y, cue.par.w, cue.par.h = 20, 651 - row * 23, 490, 21
        cue.par.fontsize = 13
        cue.par.label.expr = 'parent().CueLabel({}, compact=True)'.format(row)
        notes = show.op('cue_notes_{}'.format(row))
        if notes is None:
            notes = show.create(td.buttonCOMP, 'cue_notes_{}'.format(row))
        notes.par.x, notes.par.y, notes.par.w, notes.par.h = 520, cue.par.y, 380, 21
        notes.par.fontsize = 12
        notes.par.label.expr = 'parent().CueRowNotes({})'.format(row)
        notes.store('cue_row', row)
        callback = notes.op('clicked') or notes.create(td.panelexecuteDAT, 'clicked')
        callback.par.panels, callback.par.panelvalue, callback.par.offtoon = '..', 'lselect', True
        callback.text = "def onOffToOn(panelValue):\n    parent().parent().SelectRow(parent().fetch('cue_row'))\n"


def install(show):
    import td

    def page(name):
        return next((p for p in show.customPages if p.name == name), None) or show.appendCustomPage(name)

    def parameter(page_name, style, name, label, default=None):
        item = getattr(show.par, name, None)
        if item is None:
            item = getattr(page(page_name), 'append' + style)(name, label=label)[0]
            if default is not None:
                item.default, item.val = default, default
        item.label = label
        return item

    running = parameter('Look Editor', 'Pulse', 'Editrunninglook', 'Edit Running Cue')
    running.enableExpr = "not bool(me.par.Lookediting) and me.ext.ShowControlExt.engine.state == 'running'"
    offair = 'bool(me.par.Lookediting) and not me.IsRunningLookEdit()'
    live = parameter('Look Editor', 'Toggle', 'Looklive', 'Send Live Look to Projection', False)
    live.enableExpr = offair
    target = parameter('Look Editor', 'Int', 'Looklivetrack', 'Live Look Target Track', 1)
    target.min, target.max, target.normMin, target.normMax = 1, 3, 1, 3
    target.clampMin, target.clampMax = True, True
    target.enableExpr = offair
    for name, label in (('Showlooklive', 'Show Live Look'), ('Stoplooklive', 'Stop Live Look')):
        item = parameter('Look Editor', 'Pulse', name, label)
        item.enableExpr = offair if name == 'Showlooklive' else 'bool(me.par.Looklive)'
    show.par.Savelookasnew.enableExpr = offair
    status = parameter('Look Editor', 'Str', 'Looklivestatus', 'Live Projection Status')
    status.expr, status.readOnly = 'me.LiveLookStatus()', True

    title = parameter('Cue Notes', 'Str', 'Notescue', 'Selected Cue')
    title.expr, title.readOnly = 'me.CueNotesLabel()', True
    notes = parameter('Cue Notes', 'Str', 'Cuenotes', 'Notes (maximum 4000 characters)')
    # One backing value, not two independent note buffers. SelectCue updates
    # Notes; edits in either the legacy Cue Editor or this tab stay in sync.
    notes.bindExpr = 'me.par.Notes'
    notes.mode = type(notes.mode).BIND
    parameter('Cue Notes', 'Pulse', 'Savecuenotes', 'Save Cue Notes')
    parameter('Cue Notes', 'Pulse', 'Opencuenotes', 'Open Cue Notes')
    hint = parameter('Cue Notes', 'Str', 'Noteshelp', 'Notes Help')
    hint.val, hint.readOnly = 'Save Cue Notes applies metadata only. Save Show writes committed notes to JSON.', True
    install_cue_notes_column(show)

    for output in (1, 2, 3):
        source = show.op('output_source{}'.format(output))
        source.par.top.expr = "parent().ProjectionSource(int(parent().par.Output{0}track) if parent().par.Routingmode == 'independent' else 1)".format(output)

    for action, label, x, width in (('Showlooklive', 'Show Live Look', 20, 214),
                                    ('Stoplooklive', 'Stop Live Look', 244, 188),
                                    ('Opencuenotes', 'Cue Notes', 442, 182),
                                    ('Editrunninglook', 'Edit Running Cue', 634, 266)):
        button = next((node for node in show.children
                       if node.fetch('show_action', None, search=False) == action), None)
        if button is None:
            button = show.create(td.buttonCOMP, 'button_' + action.lower())
        button.store('show_action', action)
        button.par.x, button.par.y, button.par.w, button.par.h = x, 310, width, 30
        button.par.label, button.par.fontsize = label, 14
        callback = button.op('clicked')
        if callback is None:
            callback = button.create(td.panelexecuteDAT, 'clicked')
        callback.par.panels, callback.par.panelvalue, callback.par.offtoon = '..', 'lselect', True
        callback.text = "def onOffToOn(panelValue):\n    parent().parent().Action(parent().fetch('show_action'))\n"
    # The previous 256x144 preview reached y=340 and covered this new button
    # row. Keep a 16:9 preview fully below the controls and above the review.
    preview = show.op('look_preview_panel')
    preview.par.x, preview.par.y, preview.par.w, preview.par.h = 724, 198, 176, 99
    help_node = show.op('help')
    help_node.par.y, help_node.par.h, help_node.par.fontsize = 282, 24, 12
    help_node.par.text.expr = 'parent().LiveLookStatus()'
    show.op('look_help_0').par.y = 254
    show.op('look_help_0').par.text = 'Look Editor > Effect Module > Edit Controls'
    note_preview = show.op('look_help_1')
    note_preview.par.y, note_preview.par.h, note_preview.par.fontsize = 230, 22, 12
    note_preview.par.text.expr = "'NOTES / ' + parent().CueNotesLabel()[:32] + ': ' + parent().par.Notes.eval().replace('\\n', ' ')[:60]"
    for i in (2, 3):
        show.op('look_help_{}'.format(i)).par.display = False
    inspector = show.op('cue_inspector')
    if "'Cue Notes'" not in inspector.par.pagescope.eval():
        inspector.par.pagescope = inspector.par.pagescope.eval() + " 'Cue Notes'"
    inspector.par.op = ''
    inspector.cook(force=True)
    inspector.par.op = '..'
    inspector.cook(force=True)
    return show
