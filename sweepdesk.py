#!/usr/bin/python3
"""SweepDesk: native software inventory for Debian, Ubuntu and their derivatives."""
import argparse
import json
import os
import threading
from dataclasses import asdict
from pathlib import Path

try:
    import gi
    gi.require_version('Gtk', '3.0')
    from gi.repository import Gtk, Gdk, GdkPixbuf, GLib, Pango
except (ImportError, ValueError) as exc:
    raise SystemExit('SweepDesk needs Python 3.9+, PyGObject and GTK 3.\n'
                     'Install: sudo apt install python3-gi gir1.2-gtk-3.0 librsvg2-common\n'+str(exc))
import backend

VERSION = '0.2.0'
SUPPORT_URL = 'https://tako.id/Zwart04'
REPOSITORY_URL = 'https://github.com/Zwart04/sweepdesk'
ROOT = Path(__file__).resolve().parent

CSS = b'''
window { background: #1c1c1e; color: #f5f5f7; }
headerbar { background: #242426; border-bottom: 1px solid #3a3a3c; box-shadow: none; }
headerbar label { color: #f5f5f7; }
headerbar .subtitle { color: #a1a1a6; opacity: 1; }
.title { font-size: 25px; font-weight: 700; }
.subtitle { color: #a1a1a6; font-size: 13px; }
.stat { color: #64a8ff; font-weight: 600; }
.detail { background: #242426; border-top: 1px solid #3a3a3c; padding: 18px 24px; }
.detail-title { font-size: 18px; font-weight: 600; }
.notice { color: #98989d; font-size: 12px; }
treeview { background: #1c1c1e; color: #e5e5e7; border-color: #38383a; }
treeview:selected { background: #0a64c8; color: #ffffff; }
treeview header button { background: #28282a; color: #aeaeb2; font-weight: 600; padding: 9px 6px; border-bottom: 1px solid #3a3a3c; }
button { background: #323234; color: #f5f5f7; border: 1px solid #48484a; border-radius: 7px; padding: 8px 13px; box-shadow: none; text-shadow: none; }
button:hover { background: #3a3a3c; }
button.suggested-action { background: #0a84ff; color: #ffffff; border-color: #0a84ff; font-weight: 600; }
button.suggested-action:hover { background: #409cff; }
button.destructive-action { background: #e43a49; color: white; border-color: #e43a49; }
button.support-button { background: #383236; color: #ff6482; border-color: #383236; font-weight: 700; }
button.support-button label { color: #ff6482; text-decoration: none; }
button.support-button:hover { background: #49353e; }
button:disabled { background: #2c2c2e; color: #636366; border-color: #3a3a3c; }
entry { border-radius: 7px; background: #2c2c2e; color: #f5f5f7; border: 1px solid #48484a; padding: 7px; }
entry:focus { border-color: #0a84ff; }
textview, textview text { background: #202022; color: #e5e5e7; }
checkbutton { color: #d1d1d6; }
check { background: #38383a; border-color: #636366; }
check:checked { background: #0a84ff; color: #ffffff; }
scrolledwindow { border-color: #3a3a3c; }
menu, menuitem, popover { background: #2c2c2e; color: #f5f5f7; }
selection { background: #0a64c8; color: #ffffff; }
'''


def size_label(size):
    if not size:
        return '—'
    n = float(size)
    for unit in ('B', 'KB', 'MB', 'GB'):
        if n < 1024 or unit == 'GB':
            return f'{n:.1f} {unit}'
        n /= 1024


def label(text='', cls=None, wrap=False):
    w = Gtk.Label(label=text, xalign=0)
    w.set_line_wrap(wrap)
    w.set_selectable(True)
    if cls:
        w.get_style_context().add_class(cls)
    return w


def icon_pixbuf(name, size):
    theme = Gtk.IconTheme.get_default()
    if os.path.isabs(name):
        try:
            return GdkPixbuf.Pixbuf.new_from_file_at_scale(name, size, size, True)
        except GLib.Error:
            pass
    for candidate in [name, name+'-symbolic', 'utilities-terminal-symbolic',
                      'application-x-executable-symbolic', 'image-missing']:
        try:
            info = theme.lookup_icon(candidate, size, Gtk.IconLookupFlags.FORCE_SIZE)
            if info and info.is_symbolic():
                foreground = Gdk.RGBA()
                foreground.parse('#d1d1d6')
                pixbuf, _ = info.load_symbolic(foreground, None, None, None)
                return pixbuf
            return theme.load_icon(candidate, size, Gtk.IconLookupFlags.FORCE_SIZE)
        except GLib.Error:
            pass
    blank = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, size, size)
    blank.fill(0x64748bff)
    return blank


def text_box(text, height=250):
    view = Gtk.TextView()
    view.set_editable(False)
    view.set_cursor_visible(False)
    view.set_monospace(True)
    view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
    view.set_left_margin(14)
    view.set_right_margin(14)
    view.set_top_margin(12)
    view.set_bottom_margin(12)
    view.get_buffer().set_text(text)
    scroller = Gtk.ScrolledWindow()
    scroller.set_min_content_height(height)
    scroller.add(view)
    return scroller, view


class Window(Gtk.Window):
    def __init__(self, screenshot=None, extra_python=(), extra_manual=()):
        super().__init__(title='SweepDesk')
        self.set_default_size(1110, 760)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_icon_from_file(str(ROOT/'assets/sweepdesk.svg'))
        self.connect('delete-event', self.on_close)
        self.apps = []
        self.warnings = []
        self.busy = False
        self.mutating = False
        self.screenshot = screenshot
        self.icons = {}
        self.extra_python = extra_python
        self.extra_manual = extra_manual
        css = Gtk.CssProvider()
        css.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), css,
                                                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        Gtk.Settings.get_default().set_property('gtk-application-prefer-dark-theme', True)
        header = Gtk.HeaderBar(title='SweepDesk', subtitle=backend.distro_info())
        header.set_show_close_button(True)
        self.set_titlebar(header)
        self.spinner = Gtk.Spinner()
        header.pack_start(self.spinner)
        header.pack_start(Gtk.Image.new_from_pixbuf(icon_pixbuf(str(ROOT/'assets/sweepdesk.svg'), 28)))
        self.support_link = Gtk.LinkButton.new_with_label(SUPPORT_URL, '♥ Support Zwart04')
        self.support_link.set_tooltip_text('Support SweepDesk on Tako · opens your browser')
        self.support_link.get_style_context().add_class('support-button')
        header.pack_end(self.support_link)
        self.refresh_button = Gtk.Button.new_from_icon_name('view-refresh-symbolic', Gtk.IconSize.BUTTON)
        self.refresh_button.set_tooltip_text('Refresh installed applications')
        self.refresh_button.connect('clicked', lambda _: self.refresh())
        header.pack_end(self.refresh_button)
        self.export_button = Gtk.Button(label='Export list')
        self.export_button.connect('clicked', self.export)
        header.pack_end(self.export_button)
        help_button = Gtk.Button.new_from_icon_name('help-about-symbolic', Gtk.IconSize.BUTTON)
        help_button.set_tooltip_text('About SweepDesk, scan coverage and cleanup limits')
        help_button.connect('clicked', self.about)
        header.pack_end(help_button)
        self.environment_button = Gtk.Button.new_from_icon_name('folder-open-symbolic', Gtk.IconSize.BUTTON)
        self.environment_button.set_tooltip_text('Add a Python virtual environment to this scan')
        self.environment_button.connect('clicked', self.add_environment)
        header.pack_end(self.environment_button)
        self.manual_button = Gtk.Button.new_from_icon_name('list-add-symbolic', Gtk.IconSize.BUTTON)
        self.manual_button.set_tooltip_text('Scan a custom folder for manual or script-installed executables')
        self.manual_button.connect('clicked', self.add_manual_folder)
        header.pack_end(self.manual_button)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(outer)
        top = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        top.set_border_width(24)
        outer.pack_start(top, False, False, 0)
        line = Gtk.Box(spacing=16)
        line.pack_start(label('Your software, in one place', 'title'), True, True, 0)
        self.counter = label('Scanning…', 'stat')
        line.pack_end(self.counter, False, False, 0)
        top.pack_start(line, False, False, 0)
        top.pack_start(label('Find an app. Understand its source. Review what goes.', 'subtitle'), False, False, 0)
        controls = Gtk.Box(spacing=12)
        top.pack_start(controls, False, False, 8)
        self.search = Gtk.SearchEntry(placeholder_text='Search apps, CLI tools, or package IDs…')
        self.search.connect('search-changed', lambda _: self.refilter())
        controls.pack_start(self.search, True, True, 0)
        self.source = Gtk.ComboBoxText()
        self.source.append_text('All sources')
        self.source.set_active(0)
        self.source.connect('changed', lambda _: self.refilter())
        controls.pack_start(self.source, False, False, 0)
        self.support = Gtk.CheckButton(label='Show system packages')
        self.support.connect('toggled', lambda _: self.refilter())
        controls.pack_start(self.support, False, False, 0)

        self.store = Gtk.ListStore(GdkPixbuf.Pixbuf, str, str, str, str, int)
        self.filtered = self.store.filter_new()
        self.filtered.set_visible_func(self.visible)
        self.tree = Gtk.TreeView(model=self.filtered)
        self.tree.set_headers_clickable(False)
        self.tree.set_enable_search(False)
        self.tree.set_grid_lines(Gtk.TreeViewGridLines.HORIZONTAL)
        self.tree.get_selection().connect('changed', self.selected)
        renderer = Gtk.CellRendererPixbuf()
        renderer.set_property('ypad', 10)
        renderer.set_property('xpad', 12)
        self.tree.append_column(Gtk.TreeViewColumn('', renderer, pixbuf=0))
        for name, col_id, width, expand in [('Application / package', 1, 340, True),
                                            ('Version', 2, 180, False),
                                            ('Source', 3, 140, False),
                                            ('Package size', 4, 120, False)]:
            r = Gtk.CellRendererText()
            r.set_property('ellipsize', Pango.EllipsizeMode.END)
            r.set_property('xpad', 8)
            c = Gtk.TreeViewColumn(name, r, text=col_id)
            c.set_min_width(width)
            c.set_expand(expand)
            c.set_resizable(True)
            self.tree.append_column(c)
        scroll = Gtk.ScrolledWindow()
        scroll.set_shadow_type(Gtk.ShadowType.IN)
        scroll.add(self.tree)
        outer.pack_start(scroll, True, True, 0)

        detail = Gtk.Box(spacing=16)
        detail.get_style_context().add_class('detail')
        outer.pack_start(detail, False, False, 0)
        self.detail_icon = Gtk.Image.new_from_icon_name('application-x-executable', Gtk.IconSize.DIALOG)
        self.detail_icon.set_valign(Gtk.Align.START)
        detail.pack_start(self.detail_icon, False, False, 0)
        dtext = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        detail.pack_start(dtext, True, True, 0)
        self.detail_title = label('Select an application', 'detail-title')
        self.detail_desc = label('Official app and CLI icons where available. Select an item to see its details.', 'subtitle', True)
        self.detail_id = label('', 'notice')
        self.detail_desc.set_max_width_chars(75)
        self.detail_id.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        for w in [self.detail_title, self.detail_desc, self.detail_id]:
            dtext.pack_start(w, False, False, 0)
        self.remove_button = Gtk.Button(label='Review uninstall…')
        self.remove_button.get_style_context().add_class('suggested-action')
        self.remove_button.set_valign(Gtk.Align.CENTER)
        self.remove_button.set_sensitive(False)
        self.remove_button.connect('clicked', self.review_options)
        detail.pack_end(self.remove_button, False, False, 0)
        self.status = label('Loading local inventory…', 'notice')
        self.status.set_margin_start(24)
        self.status.set_margin_end(24)
        self.status.set_margin_top(9)
        self.status.set_margin_bottom(12)
        self.status.set_ellipsize(Pango.EllipsizeMode.END)
        outer.pack_end(self.status, False, False, 0)
        self.show_all()
        self.refresh()

    def on_close(self, *_):
        if self.mutating:
            self.message('Operation in progress', 'Wait for the current operation to finish so you can review its result.')
            return True
        Gtk.main_quit()
        return False

    def async_work(self, fn, done):
        self.busy = True
        self.spinner.start()
        self.refresh_button.set_sensitive(False)
        self.remove_button.set_sensitive(False)
        def worker():
            try:
                value, error = fn(), None
            except Exception as exc:
                value, error = None, str(exc)
            GLib.idle_add(finish, value, error)
        def finish(value, error):
            self.busy = False
            self.spinner.stop()
            self.refresh_button.set_sensitive(True)
            self.selected(self.tree.get_selection())
            done(value, error)
            return False
        threading.Thread(target=worker, daemon=True).start()

    def refresh(self):
        if self.busy:
            return
        self.status.set_text('Scanning local packages and executables. No applications are being removed.')
        self.async_work(lambda: backend.scan(self.extra_python, self.extra_manual), self.loaded)

    def add_manual_folder(self, _):
        if self.busy:
            return
        dialog = Gtk.FileChooserDialog(title='Choose a manual installation folder',
                                       transient_for=self, action=Gtk.FileChooserAction.SELECT_FOLDER)
        dialog.add_buttons('Cancel', Gtk.ResponseType.CANCEL, 'Scan this folder', Gtk.ResponseType.OK)
        response = dialog.run()
        folder = dialog.get_filename() if response == Gtk.ResponseType.OK else None
        dialog.destroy()
        if folder:
            self.extra_manual = tuple(dict.fromkeys([*self.extra_manual, folder]))
            self.refresh()

    def add_environment(self, _):
        if self.busy:
            return
        dialog = Gtk.FileChooserDialog(title='Choose a Python virtual environment folder',
                                       transient_for=self, action=Gtk.FileChooserAction.SELECT_FOLDER)
        dialog.add_buttons('Cancel', Gtk.ResponseType.CANCEL, 'Add environment', Gtk.ResponseType.OK)
        response = dialog.run()
        folder = dialog.get_filename() if response == Gtk.ResponseType.OK else None
        dialog.destroy()
        if folder:
            interpreter = Path(folder)/'bin/python'
            if not interpreter.is_file():
                self.message('Python not found', 'Select an environment folder containing bin/python.')
                return
            self.extra_python = tuple(dict.fromkeys([*self.extra_python, str(interpreter)]))
            self.refresh()

    def loaded(self, result, error):
        if error:
            self.message('Scan failed', error)
            return
        self.store.clear()
        self.apps, self.warnings = result
        sources = sorted({a.source for a in self.apps})
        current = self.source.get_active_text()
        self.source.remove_all()
        for s in ['All sources', *sources]:
            self.source.append_text(s)
        self.source.set_active(sources.index(current)+1 if current in sources else 0)
        for i, a in enumerate(self.apps):
            if a.icon not in self.icons:
                self.icons[a.icon] = icon_pixbuf(a.icon, 32)
            self.store.append([self.icons[a.icon], a.name, a.version, a.source,
                               size_label(a.size), i])
        self.refilter()
        if self.warnings:
            self.status.set_text('Some sources could not be scanned. Open About for details. '+self.warnings[0][:130])
        else:
            self.status.set_text('Scan complete · '+', '.join(sources)+' · Package sizes exclude user data.')
        if self.screenshot:
            GLib.timeout_add(700, self.save_screenshot)

    def visible(self, model, it, *_):
        app = self.apps[model[it][5]]
        q = self.search.get_text().strip().casefold()
        source = self.source.get_active_text() or 'All sources'
        if source != 'All sources' and app.source != source:
            return False
        # Search includes support packages even when they are normally hidden.
        if not q and app.support and not self.support.get_active():
            return False
        return not q or q in (app.name+' '+app.package+' '+app.description).casefold()

    def refilter(self):
        self.filtered.refilter()
        self.counter.set_text(f'{len(self.filtered):,} shown / {len(self.apps):,} packages')

    def active_app(self):
        model, it = self.tree.get_selection().get_selected()
        return self.apps[model[it][5]] if it is not None else None

    def selected(self, selection):
        app = self.active_app()
        self.remove_button.set_sensitive(app is not None and not self.busy and not app.essential and not app.readonly_reason)
        self.remove_button.set_tooltip_text(app.readonly_reason if app and app.readonly_reason else 'Create a removal preview before making changes')
        if not app:
            return
        self.detail_icon.set_from_pixbuf(icon_pixbuf(app.icon, 48))
        self.detail_title.set_text(app.name)
        self.detail_desc.set_text(app.readonly_reason or app.description)
        suffix = ' · Core system component' if app.essential else ''
        self.detail_id.set_text(app.package+' · '+app.source+(' · '+app.scope if app.scope else '')+suffix)

    def message(self, title, text):
        dialog = Gtk.MessageDialog(transient_for=self, modal=True,
                                   message_type=Gtk.MessageType.INFO,
                                   buttons=Gtk.ButtonsType.CLOSE, text=title)
        dialog.format_secondary_text(text)
        dialog.run()
        dialog.destroy()

    def about(self, _):
        self.message('About SweepDesk '+VERSION,
            'A free, native software manager by Zwart04 for Debian, Ubuntu, and compatible Debian-based desktops.\n\n'
            'Sources: APT/DEB, npm global, pip, Cargo, Flatpak, Snap, pipx, uv tools, Bun, Homebrew, registered AppImages, and manual executables. '
            'Python scanning covers the current/system interpreter, active virtualenv/Conda prefix, pyenv versions, and environments added with --python. '
            'Project environments and arbitrary installer scripts are not exhaustively scanned.\n\n'
            'Official local launcher icons are preferred. Bundled official CLI assets identify supported tools offline.\n\n'
            'APT plans are simulated and rechecked. Core components are protected. Shared dependencies and caches are preserved. '
            'pip respects externally managed Python environments (PEP 668). Known user data is opt-in and goes to Trash. '
            'Complete cleanup of every installer cannot be guaranteed. See README for source-specific limits.\n\n'
            'Support the project: '+SUPPORT_URL+'\nSource and help: '+REPOSITORY_URL+'\n\n'
            + ('Scan warnings:\n'+'\n'.join(self.warnings) if self.warnings else 'No scan warnings.'))

    def review_options(self, _):
        app = self.active_app()
        if not app or self.busy:
            return
        dialog = Gtk.Dialog(title='Uninstall options', transient_for=self, modal=True)
        dialog.set_default_size(590, 300)
        dialog.add_button('Cancel', Gtk.ResponseType.CANCEL)
        dialog.add_button('Create preview', Gtk.ResponseType.OK)
        body = dialog.get_content_area()
        body.set_border_width(22)
        body.set_spacing(12)
        row = Gtk.Box(spacing=14)
        row.pack_start(Gtk.Image.new_from_pixbuf(icon_pixbuf(app.icon, 48)), False, False, 0)
        row.pack_start(label(app.name, 'detail-title'), True, True, 0)
        body.pack_start(row, False, False, 0)
        family = Gtk.CheckButton(label='Remove the entire LibreOffice suite')
        family.set_active(False)
        if app.package.startswith('libreoffice') and app.source == 'APT':
            body.pack_start(family, False, False, 0)
        deps = Gtk.CheckButton(label='Include dependencies made unused by this removal')
        deps.set_sensitive(app.source in ('APT', 'pip'))
        body.pack_start(deps, False, False, 0)
        cleanup = Gtk.CheckButton(label='Move known user data and settings to Trash')
        cleanup.set_sensitive(bool(backend.data_paths(app)))
        body.pack_start(cleanup, False, False, 0)
        body.pack_start(label('Selected data may contain history, sign-ins, and profiles.\nThe next screen lists every known location before you confirm.', 'notice', True), False, False, 0)
        if app.source == 'Snap':
            body.pack_start(label('Snap manages its own data and automatic snapshots.', 'notice', True), False, False, 0)
        dialog.show_all()
        response = dialog.run()
        options = deps.get_active(), cleanup.get_active(), family.get_active()
        dialog.destroy()
        if response == Gtk.ResponseType.OK:
            self.status.set_text('Preparing a removal plan. Packages have not been changed…')
            self.async_work(lambda: backend.make_plan(app, *options), self.show_plan)

    def show_plan(self, plan, error):
        if error:
            self.message('Could not create a removal plan', error)
            return
        dialog = Gtk.Dialog(title='Review before uninstalling', transient_for=self, modal=True)
        dialog.set_default_size(760, 620)
        dialog.add_button('Cancel', Gtk.ResponseType.CANCEL)
        confirm = dialog.add_button('Uninstall now', Gtk.ResponseType.OK)
        confirm.get_style_context().add_class('destructive-action')
        dialog.set_default_response(Gtk.ResponseType.CANCEL)
        body = dialog.get_content_area()
        body.set_border_width(20)
        body.set_spacing(12)
        row = Gtk.Box(spacing=14)
        row.pack_start(Gtk.Image.new_from_pixbuf(icon_pixbuf(plan.app.icon, 48)), False, False, 0)
        row.pack_start(label(plan.app.name, 'detail-title'), True, True, 0)
        body.pack_start(row, False, False, 0)
        body.pack_start(label(f'{len(plan.removed)} packages/apps · {len(plan.extra)} extra dependencies · {len(plan.data)} data locations', 'subtitle', True), False, False, 0)
        scroll, _ = text_box(backend.describe_plan(plan), 360)
        body.pack_start(scroll, True, True, 0)
        acknowledgement = Gtk.CheckButton(label='I have reviewed the packages and data locations above')
        acknowledgement.connect('toggled', lambda w: confirm.set_sensitive(w.get_active()))
        confirm.set_sensitive(False)
        body.pack_start(acknowledgement, False, False, 0)
        dialog.show_all()
        response = dialog.run()
        dialog.destroy()
        if response == Gtk.ResponseType.OK:
            self.perform(plan)
        else:
            self.status.set_text('Preview closed. Nothing was changed.')

    def perform(self, plan):
        self.mutating = True
        dialog = Gtk.Dialog(title='Uninstall result', transient_for=self, modal=True)
        dialog.set_default_size(780, 550)
        close = dialog.add_button('Close', Gtk.ResponseType.CLOSE)
        close.set_sensitive(False)
        dialog.connect('delete-event', lambda *_: self.busy)
        box = dialog.get_content_area()
        box.set_border_width(16)
        heading = label('Uninstalling '+plan.app.name+'…', 'detail-title')
        box.pack_start(heading, False, False, 12)
        scroll, view = text_box('', 350)
        box.pack_start(scroll, True, True, 0)
        def append(text):
            def update():
                buffer = view.get_buffer()
                buffer.insert(buffer.get_end_iter(), text)
                view.scroll_to_iter(buffer.get_end_iter(), 0.0, False, 0, 1)
                return False
            GLib.idle_add(update)
        def finished(_, error):
            self.mutating = False
            heading.set_text('Operation completed' if not error else 'Operation incomplete')
            if error:
                append('\n'+error+'\n')
            close.set_sensitive(True)
            self.status.set_text('Review the operation log for the result.')
        dialog.show_all()
        self.async_work(lambda: backend.execute(plan, append), finished)
        dialog.run()
        dialog.destroy()
        self.refresh()

    def export(self, _):
        dialog = Gtk.FileChooserDialog(title='Save software inventory', transient_for=self,
                                       action=Gtk.FileChooserAction.SAVE)
        dialog.add_buttons('Cancel', Gtk.ResponseType.CANCEL, 'Save', Gtk.ResponseType.OK)
        dialog.set_current_name('sweepdesk-inventory.json')
        dialog.set_do_overwrite_confirmation(True)
        if dialog.run() == Gtk.ResponseType.OK:
            try:
                Path(dialog.get_filename()).write_text(json.dumps(
                    {'apps': [asdict(a) for a in self.apps], 'warnings': self.warnings},
                    ensure_ascii=False, indent=2)+'\n')
            except OSError as exc:
                self.message('Export failed', str(exc))
        dialog.destroy()

    def save_screenshot(self):
        import cairo
        allocation = self.get_allocation()
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, allocation.width, allocation.height)
        self.draw(cairo.Context(surface))
        surface.write_to_png(self.screenshot)
        Gtk.main_quit()
        return False


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='SweepDesk — software inventory and reviewed uninstall')
    parser.add_argument('--scan-json', action='store_true', help='Print the inventory as JSON without opening a window')
    parser.add_argument('--screenshot', help=argparse.SUPPRESS)
    parser.add_argument('--python', action='append', default=[], metavar='PATH',
                        help='Also scan this Python interpreter or virtualenv (repeatable)')
    parser.add_argument('--version', action='version', version='SweepDesk '+VERSION)
    parser.add_argument('--manual-dir', action='append', default=[], metavar='PATH',
                        help='Also scan executables directly inside this custom installation folder')
    args = parser.parse_args()
    if args.scan_json:
        apps, warnings = backend.scan(args.python, args.manual_dir)
        print(json.dumps({'apps': [asdict(a) for a in apps], 'warnings': warnings}, ensure_ascii=False, indent=2))
    else:
        if os.geteuid() == 0:
            raise SystemExit('Run SweepDesk as a regular user. Administrator authentication is requested only when removing system packages.')
        Window(args.screenshot, args.python, args.manual_dir)
        Gtk.main()
