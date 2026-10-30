#!/usr/bin/python3
# SPDX-FileCopyrightText: 2026 Zwart04
# SPDX-License-Identifier: GPL-3.0-or-later
# SweepDesk: see LICENSE for copying terms and warranty disclaimer.
"""SweepDesk's native desktop interface."""
import argparse
import datetime
import json
import os
import threading
import time
import sys
import subprocess
import updater
import native_packages
from dataclasses import asdict
from pathlib import Path

try:
    import gi
    gi.require_version('Gtk', '3.0')
    from gi.repository import Gtk, Gdk, GdkPixbuf, GLib, Gio, Pango, GObject
except (ImportError, ValueError) as exc:
    raise SystemExit('Install Python 3, PyGObject, GTK 3, librsvg, and polkit using your distribution package manager.\n'+str(exc))

import backend
import preferences
import styles
import ui_icons
import i18n
from i18n import tr

VERSION = '0.5.6'
APP_ID = 'io.github.Zwart04.SweepDesk'
SUPPORT_URL = 'https://tako.id/Zwart04'
REPOSITORY_URL = 'https://github.com/Zwart04/sweepdesk'
ROOT = Path(__file__).resolve().parent


def system_prefers_dark():
    source=Gio.SettingsSchemaSource.get_default()
    schema=source.lookup('org.gnome.desktop.interface',True) if source else None
    if schema and schema.has_key('color-scheme'):
        value=Gio.Settings.new_full(schema,None,None).get_string('color-scheme')
        if value in ('prefer-dark','prefer-light'):
            return value=='prefer-dark'
        if value=='default':
            return 'dark' in Gtk.Settings.get_default().get_property('gtk-theme-name').lower()
    settings=Gtk.Settings.get_default()
    return 'dark' in settings.get_property('gtk-theme-name').lower() or settings.get_property('gtk-application-prefer-dark-theme')


def label(text='', cls=None, wrap=False, selectable=False):
    widget = Gtk.Label(label=tr(text), xalign=0)
    widget.set_line_wrap(wrap)
    if wrap:
        widget.set_max_width_chars(62)
    widget.set_selectable(selectable)
    if cls:
        widget.get_style_context().add_class(cls)
    return widget


def size_label(size):
    if not size:
        return '—'
    number = float(size)
    for unit in ('B', 'KB', 'MB', 'GB'):
        if number < 1024 or unit == 'GB':
            return f'{number:.1f} {unit}'
        number /= 1024


def icon_pixbuf(name, size, dark=True):
    if name in ('utilities-terminal','package-x-generic','application-x-executable'):
        return ui_icons.pixbuf('terminal' if name=='utilities-terminal' else 'package',size,dark)
    if not dark and os.path.isabs(name):
        replacement = {'opencode.svg':'opencode-light.svg','curl.svg':'curl-light.svg'}.get(Path(name).name)
        if replacement and Path(name).with_name(replacement).is_file():
            name = str(Path(name).with_name(replacement))
    if os.path.isabs(name):
        try:
            return GdkPixbuf.Pixbuf.new_from_file_at_scale(name, size, size, True)
        except GLib.Error:
            pass
    theme = Gtk.IconTheme.get_default()
    for candidate in (name, name+'-symbolic', 'utilities-terminal-symbolic', 'application-x-executable-symbolic'):
        try:
            info = theme.lookup_icon(candidate, size, Gtk.IconLookupFlags.FORCE_SIZE)
            if not info:
                continue
            if info.is_symbolic():
                color = Gdk.RGBA()
                color.parse('#d1d1d6' if dark else '#50505a')
                pixbuf, _ = info.load_symbolic(color, None, None, None)
                return pixbuf
            return info.load_icon()
        except GLib.Error:
            pass
    pixbuf = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, size, size)
    pixbuf.fill(0x80808aff)
    return pixbuf


def text_box(text='', height=200):
    view = Gtk.TextView(editable=False, cursor_visible=False, monospace=True)
    view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
    for side in ('left', 'right', 'top', 'bottom'):
        getattr(view, 'set_'+side+'_margin')(12)
    view.get_buffer().set_text(text)
    scroll = Gtk.ScrolledWindow()
    scroll.set_min_content_height(height)
    scroll.add(view)
    return scroll, view


def dialog_shell(parent, title, width=600, height=400, buttons=()):
    dialog = Gtk.Dialog(title=tr(title), transient_for=parent, modal=True, use_header_bar=True)
    dialog.set_default_size(width, height)
    dialog.set_destroy_with_parent(True)
    dialog.get_style_context().add_class('sweep-dialog')
    dialog.get_header_bar().set_has_subtitle(False)
    dialog.get_header_bar().get_style_context().add_class('compact-toolbar')
    dialog.get_content_area().get_style_context().add_class('dialog-content')
    dialog.set_default_response(Gtk.ResponseType.NONE)
    for text, response, cls in buttons:
        button = dialog.add_button(tr(text), response)
        if cls:
            button.get_style_context().add_class('primary-action' if cls=='suggested-action' else cls)
    if any(response==Gtk.ResponseType.OK and cls=='suggested-action' for _,response,cls in buttons):
        dialog.set_default_response(Gtk.ResponseType.OK)
    return dialog


def icon_button(name, tooltip, callback):
    button = Gtk.Button()
    button.add(ui_icons.image(name))
    button.get_style_context().add_class('flat')
    button.set_tooltip_text(tr(tooltip))
    button.connect('clicked', callback)
    return button


class Window(Gtk.Window):
    def __init__(self, screenshot=None, extra_python=(), extra_manual=(), application=None, prefs=None, prefs_file=None, initial_inventory=None):
        super().__init__(title='SweepDesk', application=application)
        self.set_default_size(1120, 720)
        self.set_size_request(850, 540)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_icon_from_file(str(ROOT/'assets/sweepdesk.svg'))
        self.connect('delete-event', self.on_close)
        self.connect('key-press-event', self.key_pressed)
        self.apps, self.warnings, self.activity = [], [], []
        self.search_texts, self.row_markup, self.cli_flags = [], [], []
        self.search_query = ''
        self.filter_idle = None
        self.store_iter_by_index = {}
        self.busy = self.mutating = self.pending_refresh = self.scanning = False
        self.screenshot, self.prefs_file = screenshot, prefs_file
        self.prefs = preferences.validate(prefs) if prefs is not None else preferences.load(prefs_file)
        i18n.configure(self.prefs['language'])
        remembered_python = self.prefs['python_folders'] if self.prefs['remember_folders'] else []
        remembered_manual = self.prefs['manual_folders'] if self.prefs['remember_folders'] else []
        self.extra_python = tuple(dict.fromkeys([*remembered_python, *extra_python]))
        self.extra_manual = tuple(dict.fromkeys([*remembered_manual, *extra_manual]))
        self.category, self.source_id = 'all', None
        self.nav_updating, self.last_scan = False, ''
        self.icons = {}
        self.css = Gtk.CssProvider()
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), self.css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.system_dark = system_prefers_dark()
        self.apply_style()
        self.build_header()
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(outer)
        split = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        outer.pack_start(split, True, True, 0)
        self.sidebar_revealer = Gtk.Revealer(transition_type=Gtk.RevealerTransitionType.SLIDE_RIGHT, transition_duration=160, reveal_child=True)
        self.sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.sidebar.get_style_context().add_class('sidebar')
        self.sidebar.set_size_request(188, -1)
        nav_scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.nav = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.nav.connect('row-selected', self.nav_selected)
        nav_scroll.add(self.nav)
        self.sidebar.pack_start(nav_scroll, True, True, 8)
        author = label('Made by Zwart04', 'caption')
        author.set_margin_start(18)
        author.set_margin_bottom(15)
        self.sidebar.pack_end(author, False, False, 0)
        self.sidebar_revealer.add(self.sidebar)
        split.pack_start(self.sidebar_revealer, False, False, 0)
        main = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        main.set_border_width(20)
        split.pack_start(main, True, True, 0)
        heading = Gtk.Box(spacing=12)
        self.page_title = label('Installed Software', 'page-title')
        heading.pack_start(self.page_title, True, True, 0)
        self.counter = label('Loading…', 'count-badge')
        heading.pack_end(self.counter, False, False, 0)
        main.pack_start(heading, False, False, 0)
        self.page_subtitle = label('Applications and command-line tools', 'subtitle')
        main.pack_start(self.page_subtitle, False, False, 0)
        controls = Gtk.Box(spacing=8)
        self.search = Gtk.SearchEntry(placeholder_text=tr('Search software…'))
        self.search.connect('changed', lambda _: self.queue_refilter())
        controls.pack_start(self.search, True, True, 0)
        self.sort = Gtk.ComboBoxText()
        for name in ('Name', 'Source', 'Size'):
            self.sort.append_text(tr('Sort: {name}',name=tr(name)))
        self.sort.set_active(0)
        self.sort.connect('changed', self.sort_changed)
        controls.pack_end(self.sort, False, False, 0)
        self.view_button = Gtk.MenuButton()
        view_content = Gtk.Box(spacing=6)
        view_content.pack_start(ui_icons.image('view-list-symbolic'),False,False,0)
        view_content.pack_start(label('View'),False,False,0)
        view_content.pack_start(label('▾'),False,False,0)
        self.view_button.add(view_content)
        self.view_button.set_tooltip_text(tr('View options'))
        self.view_button.set_popover(self.build_view_popover())
        controls.pack_end(self.view_button, False, False, 0)
        main.pack_start(controls, False, False, 0)
        self.build_update_banner(main)
        self.banner = Gtk.InfoBar(message_type=Gtk.MessageType.WARNING, show_close_button=True)
        self.banner_text = label('', 'subtitle', True)
        self.banner.get_content_area().add(self.banner_text)
        self.banner.connect('response', lambda *_: self.banner.hide())
        self.banner.set_no_show_all(True)
        main.pack_start(self.banner, False, False, 0)
        self.store = Gtk.ListStore(GdkPixbuf.Pixbuf, str, str, str, str, int, str, str, str, GObject.TYPE_UINT64)
        self.filtered = self.store.filter_new()
        self.filtered.set_visible_func(self.visible)
        self.sort_model = self.filtered
        self.store.set_sort_column_id(7, Gtk.SortType.ASCENDING)
        self.tree = Gtk.TreeView(model=self.sort_model, enable_search=False)
        self.tree.set_grid_lines(Gtk.TreeViewGridLines.NONE)
        self.tree.set_tooltip_column(6)
        self.selection_handler = self.tree.get_selection().connect('changed', self.selected)
        self.tree.connect('button-press-event', self.tree_button)
        self.tree.connect('popup-menu', self.popup_keyboard)
        self.tree.connect('row-activated', lambda *_: self.details())
        self.tree.connect('key-press-event', self.tree_key)
        # One header owns both renderers: there is no empty icon-header column.
        self.name_column = Gtk.TreeViewColumn(tr('Name'))
        self.icon_renderer = Gtk.CellRendererPixbuf()
        self.icon_renderer.set_property('xpad', 10)
        self.name_renderer = Gtk.CellRendererText(ellipsize=Pango.EllipsizeMode.END, xpad=3)
        self.name_column.pack_start(self.icon_renderer, False)
        self.name_column.add_attribute(self.icon_renderer, 'pixbuf', 0)
        self.name_column.pack_start(self.name_renderer, True)
        self.name_column.set_cell_data_func(self.name_renderer,self.render_software_name)
        self.name_column.set_expand(True)
        self.name_column.set_min_width(200)
        self.name_column.set_clickable(True)
        self.name_column.connect('clicked',lambda column:self.sort_header(column,7))
        self.name_column.sort_key = 7
        self.tree.append_column(self.name_column)
        for name, column, width in [('Version', 2, 115), ('Source', 3, 90), ('Size', 4, 85)]:
            renderer = Gtk.CellRendererText(ellipsize=Pango.EllipsizeMode.END, xpad=9)
            view_column = Gtk.TreeViewColumn(tr(name), renderer, text=column)
            view_column.set_min_width(width)
            view_column.set_resizable(True)
            if column in (3, 4):
                view_column.set_clickable(True)
                view_column.sort_key = {3:8,4:9}[column]
                view_column.connect('clicked',lambda widget:self.sort_header(widget,widget.sort_key))
            self.tree.append_column(view_column)
        self.store.connect('sort-column-changed',lambda *_:self.sync_sort_indicators())
        self.sync_sort_indicators()
        scroll = Gtk.ScrolledWindow()
        scroll.add(self.tree)
        self.list_stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, transition_duration=120)
        self.list_stack.add_named(scroll, 'list')
        empty = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
        empty_image = ui_icons.image('system-search-symbolic',44)
        empty_image.get_style_context().add_class('empty-icon')
        empty.pack_start(empty_image, False, False, 0)
        self.empty_title = label('No software found', 'empty-title')
        self.empty_description = label('Try another search or choose a different source.', 'subtitle', True)
        self.empty_description.set_max_width_chars(45)
        empty.pack_start(self.empty_title, False, False, 0)
        empty.pack_start(self.empty_description, False, False, 0)
        clear = Gtk.Button(label=tr('Clear filters'))
        clear.connect('clicked', lambda _: self.clear_filters())
        empty.pack_start(clear, False, False, 5)
        self.list_stack.add_named(empty, 'empty')
        loading = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14,
                          halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
        self.loading_spinner = Gtk.Spinner(width_request=40, height_request=40)
        self.loading_spinner.get_style_context().add_class('loading-spinner')
        loading.pack_start(self.loading_spinner, False, False, 0)
        loading.pack_start(label('Loading your software…', 'empty-title'), False, False, 0)
        loading.pack_start(label('Finding installed apps and command-line tools. Please wait.', 'subtitle', True), False, False, 0)
        self.list_stack.add_named(loading, 'loading')
        frame = Gtk.Frame()
        frame.get_style_context().add_class('software-frame')
        frame.add(self.list_stack)
        main.pack_start(frame, True, True, 0)
        self.inspector = Gtk.Revealer(transition_type=Gtk.RevealerTransitionType.SLIDE_UP, transition_duration=160)
        self.build_inspector()
        main.pack_start(self.inspector, False, False, 0)
        footer = Gtk.Box(spacing=10)
        self.status = label('Loading local inventory…', 'statusbar')
        self.status.set_ellipsize(Pango.EllipsizeMode.END)
        footer.pack_start(self.status, True, True, 0)
        self.details_toggle = icon_button('dialog-information-symbolic', 'Toggle selection details', lambda _: self.toggle_details())
        footer.pack_end(self.details_toggle, False, False, 0)
        main.pack_end(footer, False, False, 0)
        self.populate_sidebar()
        self.apply_density()
        self.show_all()
        self.inspector.set_reveal_child(False)
        if initial_inventory is not None:
            self.loaded(initial_inventory,None)
        elif self.prefs['scan_on_start']:
            self.refresh()
        else:
            self.refilter()
            self.status.set_text(tr('Automatic scan is off. Click Refresh to scan your software.'))
        self.closed = False
        self.update_release = None
        self.update_checking = False
        self.update_dialog = None
        self.update_installed = False
        self.update_timer = GLib.timeout_add_seconds(3,self.automatic_update_check)
        self.connect('destroy',self.cleanup_update_timer)

    def build_update_banner(self, parent):
        self.update_banner=Gtk.Revealer(reveal_child=False)
        card=Gtk.Box(spacing=12)
        card.get_style_context().add_class('card')
        self.update_label=label('','subtitle',True)
        card.pack_start(self.update_label,True,True,0)
        self.update_button=Gtk.Button(label=tr('Update Now'))
        self.update_button.get_style_context().add_class('primary-action')
        self.update_button.connect('clicked',self.update_clicked)
        card.pack_end(self.update_button,False,False,0)
        self.update_banner.add(card)
        parent.pack_start(self.update_banner,False,False,0)

    def cleanup_update_timer(self, *_):
        self.closed=True
        if self.filter_idle is not None:
            GLib.source_remove(self.filter_idle)
            self.filter_idle = None
        if getattr(self,'update_timer',None):
            GLib.source_remove(self.update_timer)
            self.update_timer=None

    def automatic_update_check(self):
        self.update_timer=None
        if self.prefs['auto_check_updates'] and time.time()-self.prefs['last_update_check']>=86400:
            self.prefs['last_update_check']=int(time.time())
            self.persist()
            self.check_updates(False)
        self.update_timer=GLib.timeout_add_seconds(3600,self.automatic_update_check)
        return False

    def native_update_available(self):
        return bool(self.update_release and updater.packaged_install(ROOT)
                    and updater.package_name(self.update_release.version)
                    and not native_packages.immutable_system())

    def ensure_update_dialog(self):
        if self.update_dialog is not None:
            self.update_dialog.present()
            return self.update_dialog
        dialog = dialog_shell(self,'Updates',540,300)
        body = dialog.get_content_area()
        body.set_border_width(24)
        body.set_spacing(16)
        hero = Gtk.Box(spacing=16)
        hero.pack_start(Gtk.Image.new_from_pixbuf(self.cached_icon(str(ROOT/'assets/sweepdesk.svg'),56)),False,False,0)
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=6)
        dialog.status_title = label('Checking GitHub for updates…','section-title',True)
        dialog.version_label = label('SweepDesk '+VERSION,'caption')
        text.pack_start(dialog.status_title,False,False,0)
        text.pack_start(dialog.version_label,False,False,0)
        hero.pack_start(text,True,True,0)
        body.pack_start(hero,False,False,0)
        dialog.status_detail = label('Please wait. You can keep using SweepDesk.','subtitle',True,True)
        body.pack_start(dialog.status_detail,True,True,0)
        dialog.error_details = Gtk.Expander(label=tr('Details'))
        error_scroll,dialog.error_view = text_box('',120)
        dialog.error_details.add(error_scroll)
        error_scroll.show_all()
        dialog.error_details.set_no_show_all(True)
        body.pack_start(dialog.error_details,False,False,0)
        footer = Gtk.Box(spacing=10)
        dialog.spinner = Gtk.Spinner(width_request=20,height_request=20)
        footer.pack_start(dialog.spinner,False,False,0)
        actions = Gtk.Box(spacing=10)
        dialog.close_button = Gtk.Button(label=tr('Close'))
        dialog.close_button.connect('clicked',lambda _:dialog.response(Gtk.ResponseType.CLOSE))
        actions.pack_start(dialog.close_button,False,False,0)
        dialog.update_action = Gtk.Button(label=tr('Update Now'))
        dialog.update_action.get_style_context().add_class('primary-action')
        dialog.update_action.connect('clicked',lambda _:dialog.response(Gtk.ResponseType.OK))
        actions.pack_start(dialog.update_action,False,False,0)
        footer.pack_end(actions,False,False,0)
        body.pack_end(footer,False,False,0)
        dialog.connect('delete-event',lambda *_:self.mutating)
        def responded(_,response):
            if self.mutating: return
            if response == Gtk.ResponseType.OK:
                if self.busy:
                    dialog.status_detail.set_text(tr('Wait for the current task to finish, then try again.'))
                    return
                if dialog.state == 'error' and not dialog.retry_install:
                    self.check_updates(True)
                else:
                    self.update_clicked(confirmed=True)
            else:
                dialog.destroy()
        dialog.connect('response',responded)
        def destroyed(_):
            if self.update_dialog is dialog: self.update_dialog=None
        dialog.connect('destroy',destroyed)
        self.update_dialog = dialog
        dialog.state,dialog.retry_install = 'checking',False
        dialog.show_all()
        self.render_update_dialog('checking')
        return dialog

    def render_update_dialog(self, state, error=None, retry_install=False):
        dialog = self.update_dialog
        if dialog is None: return
        dialog.state,dialog.retry_install = state,retry_install
        dialog.set_modal(state=='installing')
        running = state in ('checking','installing')
        dialog.spinner.start() if running else dialog.spinner.stop()
        dialog.spinner.set_visible(running)
        dialog.close_button.set_sensitive(state!='installing')
        dialog.update_action.set_visible(state in ('available','installed','error'))
        dialog.error_details.set_expanded(False)
        dialog.error_details.set_visible(state=='error')
        dialog.version_label.set_text(tr('Update {current} → {latest}',current=VERSION,latest=self.update_release.version)
                                      if self.update_release else 'SweepDesk '+VERSION)
        titles = {'checking':'Checking GitHub for updates…','available':'Update available',
                  'installing':'Updating SweepDesk…','installed':'Update installed',
                  'current':'Up to date','error':'Update failed'}
        dialog.status_title.set_text(tr(titles[state]))
        if state == 'checking':
            detail = tr('Please wait. You can keep using SweepDesk.')
        elif state == 'available':
            detail = tr('Install the new version here. The download is verified before installation. You may be asked for your administrator password.') if self.native_update_available() else tr('This source, portable, or immutable installation needs a manual update. Download the release and follow its install guide.')
            dialog.update_action.set_label(tr('Update Now' if self.native_update_available() else 'Download release'))
        elif state == 'installing':
            detail = tr('Downloading, verifying, and installing the update. Please keep this window open.')
        elif state == 'installed':
            detail = tr('The update is ready. Restart SweepDesk to use the new version.')
            dialog.update_action.set_label(tr('Restart SweepDesk'))
        elif state == 'current':
            detail = tr('You are using SweepDesk {version}. No newer stable release is available.',version=VERSION)
        else:
            detail = tr('The update could not finish. Try again, or open Details to see the error.')
            dialog.error_view.get_buffer().set_text(str(error or tr('Update failed. Nothing was reported as successful.')))
            dialog.update_action.set_label(tr('Try again'))
        dialog.status_detail.set_text(detail)

    def check_updates(self, manual=False):
        if self.mutating:
            if manual and self.update_dialog: self.update_dialog.present()
            return
        if manual:
            self.ensure_update_dialog()
            if self.update_installed:
                self.render_update_dialog('installed')
                return
            self.render_update_dialog('checking')
        if self.update_checking: return
        self.update_checking=True
        def worker():
            try: release,error=updater.check(VERSION),None
            except Exception as exc: release,error=None,str(exc)
            GLib.idle_add(finished,release,error)
        def finished(release,error):
            self.update_checking=False
            if self.closed: return False
            if error is not None:
                self.render_update_dialog('error',error)
                return False
            self.prefs['last_update_check']=int(time.time())
            self.persist()
            self.update_release=release
            if release:
                self.update_label.set_text(tr('SweepDesk {version} is available.',version=release.version))
                self.update_banner.set_reveal_child(True)
            else:
                self.update_banner.set_reveal_child(False)
            self.render_update_dialog('available' if release else 'current')
            return False
        threading.Thread(target=worker,daemon=True).start()

    def update_clicked(self, *_, confirmed=False):
        if self.busy or self.mutating: return
        if self.update_installed:
            os.execv(sys.executable,[sys.executable,str(ROOT/'sweepdesk.py')])
            return
        release=self.update_release
        if not release: return
        self.ensure_update_dialog()
        if not confirmed:
            self.render_update_dialog('available')
            return
        if not self.native_update_available():
            self.open_uri(release.url)
            self.update_dialog.destroy()
            return
        self.mutating=True
        self.render_update_dialog('installing')
        self.update_button.set_sensitive(False)
        self.update_label.set_text(tr('Downloading and verifying the update…'))
        def apply():
            temporary,path=updater.download(release)
            try:
                command=updater.install_command(path)
                process=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,stdin=subprocess.DEVNULL)
                if process.returncode: raise RuntimeError(process.stdout[-6000:] or 'Update failed or authentication was canceled.')
                installed=subprocess.run([sys.executable,str(ROOT/'sweepdesk.py'),'--version'],capture_output=True,text=True,check=True)
                if installed.stdout.strip()!='SweepDesk '+release.version: raise RuntimeError('The installed version could not be verified. Restart and check the version.')
            finally: temporary.cleanup()
        def complete(_,error):
            self.mutating=False
            self.update_button.set_sensitive(True)
            if error is not None:
                self.update_label.set_text(tr('Update failed. Nothing was reported as successful.'))
                self.render_update_dialog('error',error,retry_install=True)
            else:
                self.update_installed=True
                self.update_label.set_text(tr('SweepDesk {version} installed. Restart to use it.',version=release.version))
                self.update_button.set_label(tr('Restart SweepDesk'))
                self.render_update_dialog('installed')
        self.async_work(apply,complete)

    def build_header(self):
        header = Gtk.HeaderBar(title=tr('SweepDesk'), show_close_button=True)
        header.get_style_context().add_class('compact-toolbar')
        header.set_has_subtitle(False)
        self.set_titlebar(header)
        header.pack_start(icon_button('view-sidebar-symbolic', 'Toggle sidebar', lambda _: self.sidebar_revealer.set_reveal_child(not self.sidebar_revealer.get_reveal_child())))
        header.pack_start(Gtk.Image.new_from_pixbuf(icon_pixbuf(str(ROOT/'assets/sweepdesk.svg'), 22, self.dark)))
        self.spinner = Gtk.Spinner()
        header.pack_start(self.spinner)
        self.support_link = Gtk.LinkButton.new_with_label(SUPPORT_URL,tr('Buy me a coffee'))
        self.support_link.get_style_context().add_class('coffee-pill')
        self.support_link.set_image(ui_icons.image('coffee'))
        self.support_link.set_always_show_image(True)
        self.support_link.set_tooltip_text(tr('Buy Zwart04 a coffee on Tako — opens your browser'))
        header.pack_end(self.support_link)
        self.settings_button = icon_button('emblem-system-symbolic', 'Settings (Ctrl+,)', lambda _: self.settings())
        header.pack_end(self.settings_button)
        more = Gtk.MenuButton()
        more.get_style_context().add_class('flat')
        more.add(ui_icons.image('open-menu-symbolic'))
        more.set_tooltip_text(tr('More actions'))
        more.set_popup(self.build_more_menu())
        header.pack_end(more)
        self.refresh_button = icon_button('view-refresh-symbolic', 'Refresh software (Ctrl+R)', lambda _: self.refresh())
        header.pack_end(self.refresh_button)
        self.export_button = None

    def build_inspector(self):
        card = Gtk.Box(spacing=12)
        card.get_style_context().add_class('inspector')
        self.detail_icon = Gtk.Image()
        card.pack_start(self.detail_icon, False, False, 0)
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.detail_title = label('', 'inspector-title')
        self.detail_desc = label('', 'subtitle')
        self.detail_desc.set_ellipsize(Pango.EllipsizeMode.END)
        self.detail_id = label('', 'caption', selectable=True)
        self.detail_id.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        for widget in (self.detail_title, self.detail_desc, self.detail_id):
            text.pack_start(widget, False, False, 0)
        card.pack_start(text, True, True, 0)
        actions = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, valign=Gtk.Align.CENTER)
        self.remove_button = Gtk.Button(label=tr('Review Uninstall…'))
        self.remove_button.get_style_context().add_class('destructive-action')
        self.remove_button.connect('clicked', self.review_options)
        actions.pack_start(self.remove_button, False, False, 0)
        details = Gtk.Button(label=tr('Show Details'))
        details.get_style_context().add_class('flat')
        details.connect('clicked', lambda _: self.details())
        actions.pack_start(details, False, False, 0)
        card.pack_end(actions, False, False, 0)
        self.inspector.add(card)

    def apply_style(self):
        theme = self.prefs['theme']
        self.dark = self.system_dark if theme == 'system' else theme == 'dark'
        Gtk.Settings.get_default().set_property('gtk-application-prefer-dark-theme', self.dark)
        self.css.load_from_data(styles.stylesheet(self.dark))
        self.icons.clear()
        ui_icons.refresh(self.dark)

    def apply_density(self):
        compact = self.prefs['density'] == 'compact'
        self.icon_size = 24 if compact else 32
        self.icon_renderer.set_property('ypad', 5 if compact else 8)
        for row in self.store:
            app = self.apps[row[5]]
            key = (app.icon, self.icon_size, self.dark)
            if key not in self.icons:
                self.icons[key] = icon_pixbuf(app.icon, self.icon_size, self.dark)
            row[0] = self.icons[key]

    @staticmethod
    def app_is_cli(app):
        if app.source=='Manual' and app.manager in ('desktop-launcher','horizon-launcher'):
            return False
        if app.source=='Manual' and app.executable.lower().endswith('.appimage'):
            return False
        if app.package.split(':')[0] in ('git','curl','wget','jq','ripgrep','fd-find','htop','btop','tmux','zsh','bash','fish','nodejs','cargo','rustc','vim','neovim'):
            return True
        return (app.source in ('RPM','Pacman','APK') and app.icon=='package-x-generic') or app.source in ('npm', 'pip', 'Cargo', 'pipx', 'uv', 'Bun', 'Homebrew', 'Manual') or 'utilities-terminal' in app.icon or '/assets/brands/' in app.icon

    def populate_sidebar(self):
        self.nav_updating = True
        for child in self.nav.get_children():
            self.nav.remove(child)
        def section(text):
            row = Gtk.ListBoxRow(selectable=False, activatable=False)
            title = label(text, 'nav-section')
            title.set_margin_start(18)
            title.set_margin_top(12)
            title.set_margin_bottom(5)
            row.add(title)
            self.nav.add(row)
        def item(title, icon, kind, value, count):
            row = Gtk.ListBoxRow()
            row.filter_kind, row.filter_value = kind, value
            row.filter_title = title
            row.get_style_context().add_class('nav-row')
            line = Gtk.Box(spacing=8)
            line.pack_start(ui_icons.image(icon), False, False, 0)
            line.pack_start(label(title), True, True, 0)
            line.pack_end(label(str(count), 'nav-count'), False, False, 0)
            row.add(line)
            self.nav.add(row)
            return row
        section('LIBRARY')
        counts = {'all':sum(not a.support or self.prefs['show_system'] for a in self.apps),
                  'apps':sum(not a.support and not self.app_is_cli(a) for a in self.apps),
                  'cli':sum(not a.support and self.app_is_cli(a) for a in self.apps),
                  'system':sum(a.support for a in self.apps)}
        chosen = None
        for title, icon, key in [('All Software','view-grid-symbolic','all'),('Applications','applications-other-symbolic','apps'),
                                 ('Command Line','utilities-terminal-symbolic','cli'),('System Packages','package-x-generic-symbolic','system')]:
            row = item(title, icon, 'category', key, counts[key])
            if self.category == key and self.source_id is None:
                chosen = row
        section('SOURCES')
        for source in backend.SOURCES:
            count = sum(a.source == source for a in self.apps)
            if not count and not self.prefs['show_empty_sources']:
                continue
            row = item(source, 'folder-symbolic' if source in ('Manual','ArtCraft') else 'package-x-generic-symbolic', 'source', source, count)
            if self.source_id == source:
                chosen = row
        self.nav.show_all()
        if chosen is None:
            self.category,self.source_id='all',None
            chosen=next(r for r in self.nav.get_children() if hasattr(r,'filter_kind'))
            if hasattr(self,'page_title'):
                self.page_title.set_text(tr('Installed Software'))
        self.nav.select_row(chosen)
        self.nav_updating = False

    def nav_selected(self, _, row):
        if self.nav_updating or row is None or not hasattr(row, 'filter_kind'):
            return
        self.category = row.filter_value if row.filter_kind == 'category' else 'all'
        self.source_id = row.filter_value if row.filter_kind == 'source' else None
        self.page_title.set_text(tr(row.filter_title if self.category != 'all' or self.source_id else 'Installed Software'))
        self.refilter()

    def visible(self, model, it, *_):
        app = self.apps[model[it][5]]
        query = self.search_query
        if self.source_id and app.source != self.source_id:
            return False
        if self.category == 'system':
            if not app.support:
                return False
        elif self.category in ('apps','cli'):
            if app.support or self.cli_flags[model.get_value(it,5)] != (self.category == 'cli'):
                return False
        elif not query and app.support and not self.prefs['show_system']:
            return False
        return not query or query in self.search_texts[model.get_value(it,5)]

    def render_software_name(self, column, renderer, model, iterator, data=None):
        renderer.set_property('markup',self.row_markup[model.get_value(iterator,5)])

    def cached_icon(self, name, size):
        key = (name, size, self.dark)
        if key not in self.icons:
            self.icons[key] = icon_pixbuf(name, size, self.dark)
        return self.icons[key]

    def sort_changed(self, _):
        if not hasattr(self, 'sort_model'):
            return
        column = (7,8,9)[max(0,self.sort.get_active())]
        self.store.set_sort_column_id(column, Gtk.SortType.DESCENDING if column == 9 else Gtk.SortType.ASCENDING)

    def sort_header(self, widget, key):
        current, order = self.store.get_sort_column_id()
        order = Gtk.SortType.DESCENDING if current == key and order == Gtk.SortType.ASCENDING else Gtk.SortType.ASCENDING
        self.store.set_sort_column_id(key,order)

    def sync_sort_indicators(self):
        current, order = self.store.get_sort_column_id()
        for column in self.tree.get_columns():
            column.set_sort_indicator(getattr(column,'sort_key',None)==current)
            column.set_sort_order(order)

    def queue_refilter(self):
        if self.filter_idle is None:
            def flush():
                self.filter_idle = None
                if not self.closed: self.refilter()
                return False
            self.filter_idle = GLib.idle_add(flush)

    def refilter(self):
        if self.filter_idle is not None:
            GLib.source_remove(self.filter_idle)
            self.filter_idle = None
        self.search_query = self.search.get_text().strip().casefold()
        selection = self.tree.get_selection()
        model, iterator = selection.get_selected()
        selected_index = model.get_value(iterator,5) if iterator is not None else None
        selection.handler_block(self.selection_handler)
        try:
            # Batch model changes rather than relaying thousands of row updates to the view.
            self.tree.set_model(None)
            self.filtered.refilter()
            self.tree.set_model(self.sort_model)
            if selected_index is not None:
                iterator = self.store_iter_by_index.get(selected_index)
                if iterator is not None:
                    path = self.filtered.convert_child_path_to_path(self.store.get_path(iterator))
                    if path is not None: selection.select_path(path)
        finally:
            selection.handler_unblock(self.selection_handler)
        count = len(self.filtered)
        self.counter.set_text(tr('Loading…') if self.scanning else tr('{count} item' if count==1 else '{count} items',count=f'{count:,}'))
        self.page_subtitle.set_text(tr('{count} installed packages · {sources} sources',count=f'{len(self.apps):,}',sources=len({a.source for a in self.apps})) if self.apps else tr('Applications and command-line tools'))
        self.list_stack.set_visible_child_name('loading' if self.scanning and not self.apps else 'list' if count else 'empty')
        self.empty_title.set_text(tr('No matches' if self.apps else 'Your software library'))
        self.empty_description.set_text(tr('Try a different search or clear your filters.' if self.apps else 'Refresh to find installed apps and command-line tools.'))
        self.selected(self.tree.get_selection())

    def clear_filters(self):
        self.search.set_text('')
        self.category, self.source_id = 'all', None
        self.page_title.set_text(tr('Installed Software'))
        self.populate_sidebar()
        self.refilter()

    def active_app(self):
        model, it = self.tree.get_selection().get_selected()
        return self.apps[model[it][5]] if it is not None else None

    def can_remove(self, app):
        return bool(app and not self.busy and not app.essential and not app.readonly_reason)

    def selected(self, _):
        app = self.active_app()
        self.remove_button.set_sensitive(self.can_remove(app))
        self.inspector.set_reveal_child(bool(app and self.prefs['show_details']))
        if not app:
            return
        self.detail_icon.set_from_pixbuf(self.cached_icon(app.icon, 40))
        self.detail_title.set_text(tr(app.name))
        self.detail_desc.set_text(tr(app.readonly_reason or app.description or 'Installed software'))
        self.detail_id.set_text(tr(app.package+' · '+app.source+' · '+(app.version or 'Version unknown')))
        self.remove_button.set_tooltip_text(tr(app.readonly_reason or ('Protected system package' if app.essential else 'Review the complete removal plan')))

    def async_work(self, function, done):
        self.busy = True
        self.spinner.start()
        self.refresh_button.set_sensitive(False)
        self.selected(self.tree.get_selection())
        def worker():
            try:
                value, error = function(), None
            except Exception as exc:
                value, error = None, str(exc)
            GLib.idle_add(finish, value, error)
        def finish(value, error):
            self.busy = False
            self.spinner.stop()
            self.refresh_button.set_sensitive(True)
            done(value, error)
            self.selected(self.tree.get_selection())
            if self.pending_refresh and not self.mutating:
                self.pending_refresh = False
                GLib.idle_add(self.refresh)
            return False
        threading.Thread(target=worker, daemon=True).start()

    def refresh(self):
        if self.busy:
            return False
        self.scanning = True
        self.loading_spinner.start()
        self.refilter()
        self.status.set_text(tr('Loading your software…'))
        self.banner.hide()
        self.async_work(lambda: backend.scan(self.extra_python,self.extra_manual,self.prefs['enabled_sources']), self.loaded)
        return False

    def loaded(self, result, error):
        self.scanning = False
        self.loading_spinner.stop()
        if error:
            self.refilter()
            self.banner_text.set_text(tr('Scan failed: {error}',error=error))
            self.banner.show_all()
            self.status.set_text(tr('Scan incomplete. Refresh to try again.'))
            return
        previous = self.active_app()
        previous_key = previous.key if previous else None
        self.tree.set_model(None)
        self.store.clear()
        self.apps, self.warnings = result
        self.store_iter_by_index = {}
        self.search_texts = [(a.name+' '+a.package+' '+a.description).casefold() for a in self.apps]
        self.cli_flags = [self.app_is_cli(a) for a in self.apps]
        self.row_markup = []
        for app in self.apps:
            description = ' '.join((app.description or app.readonly_reason or app.package).split())[:220]
            self.row_markup.append(GLib.markup_escape_text(app.name)+'\n<span size="small" alpha="78%">'+GLib.markup_escape_text(description)+'</span>')
        for index, app in enumerate(self.apps):
            self.store_iter_by_index[index] = self.store.append([self.cached_icon(app.icon,self.icon_size),app.name,app.version,app.source,size_label(app.size),index,app.package+'\n'+(app.readonly_reason or app.description),app.name.casefold(),app.source.casefold()+' / '+app.name.casefold(),max(0,app.size)])
        self.tree.set_model(self.sort_model)
        if previous_key is not None:
            index = next((i for i,app in enumerate(self.apps) if app.key==previous_key),None)
            if index is not None:
                path = self.filtered.convert_child_path_to_path(self.store.get_path(self.store_iter_by_index[index]))
                if path is not None: self.tree.get_selection().select_path(path)
        self.populate_sidebar()
        self.refilter()
        self.last_scan = datetime.datetime.now().strftime('%H:%M')
        self.status.set_text(tr('Updated {time} · Package sizes exclude user data',time=self.last_scan))
        if self.warnings:
            self.banner_text.set_text(tr('{count} source(s) could not be scanned. Open Scan Status for details.',count=len(self.warnings)))
            self.banner.show_all()
        if self.screenshot:
            GLib.timeout_add(600,self.save_screenshot)

    def menu_item(self, menu, title, callback, enabled=True):
        item = Gtk.MenuItem(label=tr(title))
        item.set_sensitive(enabled)
        item.connect('activate',lambda _:callback())
        menu.append(item)
        return item

    def build_more_menu(self):
        menu = Gtk.Menu()
        self.menu_item(menu,'Add Python Environment…',lambda:self.add_environment(None))
        self.menu_item(menu,'Add Install Folder…',lambda:self.add_manual_folder(None))
        menu.append(Gtk.SeparatorMenuItem())
        self.menu_item(menu,'Export Inventory…',lambda:self.export(None))
        self.menu_item(menu,'Check for Updates…',lambda:self.check_updates(True))
        self.menu_item(menu,'Activity',self.show_activity)
        self.menu_item(menu,'Scan Status',self.scan_status)
        menu.append(Gtk.SeparatorMenuItem())
        self.menu_item(menu,'Settings…',lambda:self.settings())
        self.menu_item(menu,'Keyboard Shortcuts',self.shortcuts)
        self.menu_item(menu,'Online Guide',lambda:self.open_uri(REPOSITORY_URL+('/blob/main/README.id.md' if i18n.resolve_language(self.prefs['language'])=='id' else '#readme')))
        self.menu_item(menu,'About SweepDesk',lambda:self.about(None))
        menu.append(Gtk.SeparatorMenuItem())
        self.menu_item(menu,'Quit SweepDesk',self.on_close)
        menu.show_all()
        return menu

    def build_context_menu(self):
        menu = Gtk.Menu()
        app = self.active_app()
        self.menu_item(menu,'Show Details',self.details,bool(app))
        self.menu_item(menu,'Show Installed Files…',self.show_files,bool(app and app.source in ('APT','RPM','Pacman','APK') and not self.busy))
        self.menu_item(menu,'Open Install Folder',self.open_install_folder,bool(app and self.install_folder(app)))
        menu.append(Gtk.SeparatorMenuItem())
        self.menu_item(menu,'Copy Package ID',lambda:self.copy_text(app.package if app else ''),bool(app))
        self.menu_item(menu,'Copy Name',lambda:self.copy_text(app.name if app else ''),bool(app))
        menu.append(Gtk.SeparatorMenuItem())
        self.menu_item(menu,'Review Uninstall…',lambda:self.review_options(None),self.can_remove(app))
        menu.show_all()
        return menu

    def tree_button(self, _, event):
        if event.button != 3:
            return False
        hit = self.tree.get_path_at_pos(int(event.x),int(event.y))
        if not hit:
            return False
        self.tree.get_selection().select_path(hit[0])
        self.context_menu = self.build_context_menu()
        self.context_menu.popup_at_pointer(event)
        return True

    def popup_keyboard(self, _):
        self.context_menu = self.build_context_menu()
        self.context_menu.popup_at_widget(self.tree,Gdk.Gravity.CENTER,Gdk.Gravity.NORTH_WEST,Gtk.get_current_event())
        return True

    def tree_key(self, _, event):
        if event.state & Gdk.ModifierType.CONTROL_MASK and event.keyval in (Gdk.KEY_c,Gdk.KEY_C):
            if self.active_app():
                self.copy_text(self.active_app().package)
            return True
        if event.keyval == Gdk.KEY_Delete:
            self.review_options(None)
            return True
        return False

    def key_pressed(self, _, event):
        if not event.state & Gdk.ModifierType.CONTROL_MASK:
            return False
        callbacks = {Gdk.KEY_f:lambda:self.search.grab_focus(),Gdk.KEY_r:self.refresh,
                     Gdk.KEY_comma:self.settings,Gdk.KEY_i:self.details,
                     Gdk.KEY_e:lambda:self.export(None),Gdk.KEY_q:self.on_close}
        callback = callbacks.get(Gdk.keyval_to_lower(event.keyval))
        if callback:
            callback()
            return True
        return False

    def copy_text(self, text):
        Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(tr(text),-1)
        self.status.set_text(tr('Copied to clipboard'))

    def open_uri(self, uri):
        try:
            Gtk.show_uri_on_window(self,uri,Gdk.CURRENT_TIME)
        except GLib.Error as error:
            self.message('Could not open link',str(error))

    def install_folder(self, app):
        candidates=[]
        if app.source=='npm' and app.scope:
            candidates.append(Path(app.scope)/'lib/node_modules'/app.package)
        elif app.source=='Bun' and app.scope:
            candidates.append(Path(app.scope)/'node_modules'/app.package)
        elif app.source=='Cargo':
            candidates.append(Path(os.environ.get('CARGO_HOME',str(Path.home()/'.cargo')))/'bin')
        elif app.source=='Flatpak':
            base=Path.home()/'.local/share/flatpak' if app.scope=='user' else Path('/var/lib/flatpak')
            candidates.append(base/'app'/app.package)
        elif app.source=='Snap':
            candidates.append(Path('/snap')/app.package/'current')
        for candidate in candidates:
            if candidate.is_dir():
                return candidate
        for raw in (app.executable,app.location,app.scope):
            if raw and Path(raw).is_absolute() and Path(raw).exists():
                path = Path(raw)
                return path if path.is_dir() and not path.name.endswith(('.dist-info','.egg-info')) else path.parent
        return None

    def open_install_folder(self):
        app = self.active_app()
        folder = self.install_folder(app) if app else None
        if folder:
            self.open_uri(folder.as_uri())

    def show_files(self):
        app = self.active_app()
        if not app or app.source not in ('APT','RPM','Pacman','APK') or self.busy:
            return
        self.async_work(lambda:backend.run(['/usr/bin/dpkg-query','-L',app.package]) if app.source=='APT' else native_packages.files(app),
                        lambda value,error:self.show_text(tr('Installed Files · {name}',name=app.name),error or value))

    def build_details_dialog(self, app):
        dialog = dialog_shell(self,'Software Details',590,480,[('Close',Gtk.ResponseType.CLOSE,None)])
        body = dialog.get_content_area()
        body.set_border_width(20)
        body.set_spacing(14)
        hero = Gtk.Box(spacing=14)
        hero.pack_start(Gtk.Image.new_from_pixbuf(icon_pixbuf(app.icon,56,self.dark)),False,False,0)
        title = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=5)
        title.pack_start(label(app.name,'section-title'),False,False,0)
        title.pack_start(label(app.description or app.package,'subtitle',True),False,False,0)
        hero.pack_start(title,True,True,0)
        body.pack_start(hero,False,False,0)
        grid = Gtk.Grid(row_spacing=10,column_spacing=18)
        fields = [('Package ID',app.package),('Source',app.source),('Version',app.version or 'Unknown'),('Package size',size_label(app.size)),
                  ('Environment',app.scope),('Executable',app.executable),('Location',app.location)]
        index = 0
        for key,value in fields:
            if not value:
                continue
            grid.attach(label(key,'caption'),0,index,1,1)
            item = label(value,wrap=True,selectable=True)
            item.set_max_width_chars(54)
            grid.attach(item,1,index,1,1)
            index += 1
        body.pack_start(grid,False,False,0)
        locations = backend.data_paths(app)
        note = app.readonly_reason or ('Protected core system package.' if app.essential else 'Uninstalling always starts with a review of the removal plan.')
        body.pack_start(label(note,'subtitle',True),False,False,0)
        if locations:
            body.pack_start(label('Known user-data locations','caption'),False,False,0)
            scroll,_ = text_box('\n'.join(locations),90)
            body.pack_start(scroll,True,True,0)
        copy = Gtk.Button(label=tr('Copy Package ID'))
        copy.connect('clicked',lambda _:self.copy_text(app.package))
        body.pack_end(copy,False,False,0)
        return dialog

    def details(self):
        app = self.active_app()
        if app:
            self.run_dialog(self.build_details_dialog(app))

    def run_dialog(self, dialog):
        dialog.show_all()
        response = dialog.run()
        dialog.destroy()
        return response

    def message(self, title, text):
        dialog = dialog_shell(self,title,480,230,[('Close',Gtk.ResponseType.CLOSE,None)])
        body = dialog.get_content_area()
        body.set_border_width(22)
        text_label = label(text,'subtitle',True,True)
        text_label.set_max_width_chars(65)
        body.pack_start(text_label,True,True,0)
        self.run_dialog(dialog)

    def show_text(self, title, text):
        dialog = dialog_shell(self,title,720,460,[('Close',Gtk.ResponseType.CLOSE,None)])
        dialog.get_content_area().pack_start(text_box(text,300)[0],True,True,0)
        self.run_dialog(dialog)

    def build_view_popover(self):
        popover = Gtk.Popover()
        popover.syncing = False
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=9)
        content.set_border_width(14)
        popover.view_controls = {}
        for title,key in [('Show system packages','show_system'),('Show selection details','show_details')]:
            check = Gtk.CheckButton(label=tr(title),active=self.prefs[key])
            def changed(widget, key=key):
                if not popover.syncing:
                    self.set_preference(key,widget.get_active())
            check.connect('toggled',changed)
            popover.view_controls[key] = check
            content.pack_start(check,False,False,0)
        content.pack_start(label('Row density','caption'),False,False,0)
        density = Gtk.ComboBoxText()
        for value in ('Compact','Comfortable'):
            density.append_text(tr(value))
        density.set_active(0 if self.prefs['density']=='compact' else 1)
        def density_changed(widget):
            if not popover.syncing:
                self.set_preference('density','compact' if widget.get_active()==0 else 'comfortable')
        density.connect('changed',density_changed)
        content.pack_start(density,False,False,0)
        popover.density_control = density
        def sync_controls(_):
            popover.syncing = True
            try:
                for key,check in popover.view_controls.items():
                    check.set_active(self.prefs[key])
                density.set_active(0 if self.prefs['density']=='compact' else 1)
            finally:
                popover.syncing = False
        popover.connect('show',sync_controls)
        popover.add(content)
        content.show_all()
        return popover

    def persist(self):
        data = dict(self.prefs)
        data['python_folders'] = list(self.extra_python) if data['remember_folders'] else []
        data['manual_folders'] = list(self.extra_manual) if data['remember_folders'] else []
        try:
            preferences.save(data,self.prefs_file)
        except OSError as error:
            self.message('Settings could not be saved',str(error))

    def set_preference(self, key, value):
        self.prefs[key] = value
        self.persist()
        if key == 'theme':
            self.apply_style()
        if key in ('density','theme'):
            self.apply_density()
        if key == 'show_system':
            self.populate_sidebar()
            self.refilter()
        else:
            self.selected(self.tree.get_selection())

    def toggle_details(self):
        self.set_preference('show_details',not self.prefs['show_details'])

    def build_settings_dialog(self):
        dialog = dialog_shell(self,'Settings',720,530,[('Cancel',Gtk.ResponseType.CANCEL,None),('Save',Gtk.ResponseType.OK,'suggested-action')])
        layout = Gtk.Box()
        dialog.get_content_area().pack_start(layout,True,True,0)
        stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE)
        stack.get_style_context().add_class('settings-stack')
        sidebar = Gtk.StackSidebar(stack=stack)
        sidebar.get_style_context().add_class('settings-sidebar')
        sidebar.set_size_request(160,-1)
        layout.pack_start(sidebar,False,False,0)
        layout.pack_start(stack,True,True,0)
        controls = {}
        folders = {'python_folders':list(self.extra_python),'manual_folders':list(self.extra_manual)}
        def page(title,subtitle):
            scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
            scroll.get_style_context().add_class('settings-scroller')
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=16)
            box.get_style_context().add_class('settings-page')
            box.set_border_width(0)
            box.pack_start(label(title,'section-title'),False,False,0)
            text = label(subtitle,'subtitle',True)
            text.set_max_width_chars(48)
            box.pack_start(text,False,False,0)
            scroll.add(box)
            stack.add_titled(scroll,title,tr(title))
            return box
        def row(box,title,description,widget):
            line = Gtk.Box(spacing=16)
            captions = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=4)
            captions.pack_start(label(title),False,False,0)
            if description:
                sub = label(description,'caption',True)
                sub.set_max_width_chars(37)
                captions.pack_start(sub,False,False,0)
            line.pack_start(captions,True,True,0)
            widget.set_valign(Gtk.Align.CENTER)
            line.pack_end(widget,False,False,0)
            box.pack_start(line,False,False,0)
        def toggle(box,key,title,description=''):
            widget = Gtk.Switch(active=self.prefs[key])
            controls[key] = widget
            row(box,title,description,widget)
        appearance = page('Appearance','A familiar, quiet workspace with native desktop controls.')
        language = Gtk.ComboBoxText()
        for key,title in [('system','Follow system'),('id','Bahasa Indonesia'),('en','English')]:
            language.append(key,tr(title))
        language.set_active_id(self.prefs['language'])
        language.set_sensitive(not self.busy)
        controls['language'] = language
        row(appearance,'Language','Finish the current operation before changing language.' if self.busy else 'Changes apply immediately after saving.',language)
        for key,title,values in [('theme','Appearance',('Dark','Light','System')),('density','Row density',('Compact','Comfortable'))]:
            combo = Gtk.ComboBoxText()
            for value in values:
                combo.append(value.lower(),tr(value))
            combo.set_active_id(self.prefs[key])
            controls[key] = combo
            row(appearance,title,'',combo)
        toggle(appearance,'show_details','Selection details','Show an information card below the software list.')
        toggle(appearance,'show_system','System packages','Include support packages in All Software.')
        toggle(appearance,'show_empty_sources','Empty sources','Show sources that have no detected software.')
        scanning = page('Scanning','Choose what is remembered and add installation locations.')
        toggle(scanning,'scan_on_start','Scan when opening','Refresh the local inventory when SweepDesk starts.')
        toggle(scanning,'remember_folders','Remember added folders','Store additional scan locations on this computer.')
        def folder_group(title,key,python):
            scanning.pack_start(label(title,'caption'),False,False,0)
            container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=6)
            scanning.pack_start(container,False,False,0)
            def rebuild():
                for child in container.get_children():
                    container.remove(child)
                for value in folders[key]:
                    line = Gtk.Box(spacing=6)
                    text = label(value,'caption')
                    text.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
                    text.set_tooltip_text(tr(value))
                    line.pack_start(text,True,True,0)
                    remove = icon_button('list-remove-symbolic','Remove scan location',lambda _,v=value:(folders[key].remove(v),rebuild()))
                    line.pack_end(remove,False,False,0)
                    container.pack_start(line,False,False,0)
                container.show_all()
            def add(_):
                selected = self.choose_folder('Choose a Python environment' if python else 'Choose an install folder',dialog)
                if selected:
                    value = str(Path(selected)/'bin/python') if python else selected
                    if python and not Path(value).is_file():
                        self.message('Python not found','Choose a folder containing bin/python.')
                    elif value not in folders[key]:
                        folders[key].append(value)
                        rebuild()
            add_button = Gtk.Button(label=tr('Add Environment…' if python else 'Add Folder…'))
            add_button.connect('clicked',add)
            scanning.pack_start(add_button,False,False,0)
            rebuild()
        folder_group('PYTHON ENVIRONMENTS','python_folders',True)
        folder_group('MANUAL INSTALL FOLDERS','manual_folders',False)
        source_page = page('Sources','Available managers are scanned locally. Turning a source off only hides it from future scans.')
        source_page.set_spacing(10)
        source_controls = {}
        for source in backend.SOURCES:
            switch = Gtk.Switch(active=source in self.prefs['enabled_sources'])
            source_controls[source] = switch
            row(source_page,'APT / DEB' if source=='APT' else source,'',switch)
        updates = page('Updates','Get new SweepDesk releases from GitHub. Your inventory is never sent.')
        toggle(updates,'auto_check_updates','Check automatically','Check at startup, at most once per day. Installing requires your action.')
        updates.pack_start(label(tr('Current version: {version}',version=VERSION),'caption'),False,False,0)
        check_updates_button=Gtk.Button(label=tr('Check for Updates…'))
        check_updates_button.connect('clicked',lambda _:self.check_updates(True))
        updates.pack_start(check_updates_button,False,False,0)
        about = page('About','SweepDesk '+VERSION+' · '+tr('Free and open source, made by Zwart04.'))
        logo = Gtk.Image.new_from_pixbuf(icon_pixbuf(str(ROOT/'assets/sweepdesk.svg'),80,self.dark))
        about.pack_start(logo,False,False,4)
        for text in ('For Debian, Ubuntu, Fedora, openSUSE, Arch Linux, and compatible derivatives.','Removal always requires a reviewed plan. Known user data goes to Trash; shared dependencies and uncertain files are kept.'):
            about.pack_start(label(text,'subtitle',True),False,False,0)
        support = Gtk.LinkButton.new_with_label(SUPPORT_URL,tr('Buy me a coffee'))
        support.set_halign(Gtk.Align.CENTER)
        support.get_style_context().add_class('coffee-pill')
        support.set_image(ui_icons.image('coffee'))
        support.set_always_show_image(True)
        about.pack_start(support,False,False,0)
        about.pack_start(Gtk.LinkButton.new_with_label(REPOSITORY_URL,tr('Source code and documentation ↗')),False,False,0)
        dialog.settings_controls, dialog.source_controls, dialog.scan_folders = controls, source_controls, folders
        dialog.settings_stack=stack
        return dialog

    def settings(self):
        dialog = self.build_settings_dialog()
        dialog.show_all()
        response = dialog.run()
        language_changed = False
        if response == Gtk.ResponseType.OK:
            old_language = self.prefs['language']
            old_sources = list(self.prefs['enabled_sources'])
            old_folders = (self.extra_python,self.extra_manual)
            for key,widget in dialog.settings_controls.items():
                self.prefs[key] = widget.get_active_id() if isinstance(widget,Gtk.ComboBoxText) else widget.get_active()
            self.prefs['enabled_sources'] = [s for s,w in dialog.source_controls.items() if w.get_active()]
            self.extra_python = tuple(dialog.scan_folders['python_folders'])
            self.extra_manual = tuple(dialog.scan_folders['manual_folders'])
            language_changed = old_language != self.prefs['language']
            self.persist()
            self.apply_style()
            self.apply_density()
            self.populate_sidebar()
            self.refilter()
            if not language_changed and (old_sources != self.prefs['enabled_sources'] or old_folders != (self.extra_python,self.extra_manual)):
                if self.busy:
                    self.pending_refresh = True
                else:
                    self.refresh()
        dialog.destroy()
        if language_changed:
            replacement = self.rebuild_language()
            if old_sources != self.prefs['enabled_sources'] or old_folders != (self.extra_python,self.extra_manual):
                replacement.refresh()

    def rebuild_language(self):
        application = self.get_application()
        replacement = Window(extra_python=self.extra_python,extra_manual=self.extra_manual,
                             application=application,prefs=self.prefs,prefs_file=self.prefs_file,
                             initial_inventory=(self.apps,self.warnings))
        replacement.activity = self.activity
        replacement.category,replacement.source_id = self.category,self.source_id
        replacement.populate_sidebar()
        selected = replacement.nav.get_selected_row()
        if selected:
            replacement.page_title.set_text(tr(selected.filter_title if replacement.category!='all' or replacement.source_id else 'Installed Software'))
        replacement.search.set_text(self.search.get_text())
        replacement.refilter()
        if application:
            application.main_window = replacement
        replacement.present()
        self.destroy()
        return replacement

    def choose_folder(self, title, parent=None):
        dialog = Gtk.FileChooserDialog(title=tr(title),transient_for=parent or self,action=Gtk.FileChooserAction.SELECT_FOLDER)
        dialog.add_buttons(tr('Cancel'),Gtk.ResponseType.CANCEL,tr('Choose Folder'),Gtk.ResponseType.OK)
        response = dialog.run()
        path = dialog.get_filename() if response == Gtk.ResponseType.OK else None
        dialog.destroy()
        return path

    def add_environment(self, _):
        if self.busy:
            return
        folder = self.choose_folder('Choose a Python virtual environment')
        if folder:
            python = str(Path(folder)/'bin/python')
            if not Path(python).is_file():
                self.message('Python not found','Choose a folder containing bin/python.')
                return
            self.extra_python = tuple(dict.fromkeys([*self.extra_python,python]))
            self.persist()
            self.refresh()

    def add_manual_folder(self, _):
        if self.busy:
            return
        folder = self.choose_folder('Choose a manual install folder')
        if folder:
            self.extra_manual = tuple(dict.fromkeys([*self.extra_manual,folder]))
            self.persist()
            self.refresh()

    def build_options_dialog(self, app):
        dialog = dialog_shell(self,'Uninstall Options',580,420 if app.manager=='horizon-launcher' else 350,[('Cancel',Gtk.ResponseType.CANCEL,None),('Preview Removal',Gtk.ResponseType.OK,'suggested-action')])
        body = dialog.get_content_area()
        body.set_border_width(22)
        body.set_spacing(16)
        hero = Gtk.Box(spacing=12)
        hero.pack_start(Gtk.Image.new_from_pixbuf(icon_pixbuf(app.icon,48,self.dark)),False,False,0)
        title = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=5)
        title.pack_start(label(app.name,'section-title'),False,False,0)
        title.pack_start(label(app.package+' · '+app.source,'caption'),False,False,0)
        hero.pack_start(title,True,True,0)
        body.pack_start(hero,False,False,0)
        family = Gtk.CheckButton(label=tr('Remove the entire LibreOffice suite'))
        if app.package.startswith('libreoffice') and app.source=='APT':
            body.pack_start(family,False,False,0)
        deps = Gtk.CheckButton(label=tr('Clean up unneeded support packages'))
        deps.set_sensitive(app.source in ('APT','pip','Pacman'))
        body.pack_start(deps,False,False,0)
        if deps.get_sensitive():
            body.pack_start(label('Also clean up support packages used by this app, if no other apps need them.', 'subtitle', True),False,False,0)
        cleanup = Gtk.CheckButton(label=tr('Move known user data and settings to Trash'))
        cleanup.set_sensitive(bool(backend.data_paths(app)))
        body.pack_start(cleanup,False,False,0)
        if app.manager=='horizon-launcher':
            body.pack_start(label(tr('If selected, Horizon worlds, server data and downloaded game files in the listed folders go to Trash. Saved Horizon accounts are signed out first. Original Minecraft folders stay untouched.'),'subtitle',True),False,False,0)
        body.pack_start(label('Nothing changes yet. The next screen lists every package and known data location for your review.','subtitle',True),False,False,0)
        if app.source=='Snap':
            body.pack_start(label('Snap manages its own data and normal snapshots.','caption',True),False,False,0)
        dialog.option_controls = (deps,cleanup,family)
        return dialog

    def review_options(self, _):
        app = self.active_app()
        if not self.can_remove(app):
            return
        dialog = self.build_options_dialog(app)
        dialog.show_all()
        response = dialog.run()
        options = tuple(w.get_active() for w in dialog.option_controls)
        dialog.destroy()
        if response == Gtk.ResponseType.OK:
            self.status.set_text(tr('Preparing a removal preview…'))
            loading = self.build_loading_dialog('Preparing a removal preview…',
                                                'Checking which packages and data would be removed. Please wait.')
            loading.show_all()
            def ready(plan, error):
                loading.destroy()
                self.show_plan(plan, error)
            self.async_work(lambda:backend.make_plan(app,*options),ready)

    def build_loading_dialog(self, title, description):
        dialog = dialog_shell(self, title, 480, 200)
        dialog.get_header_bar().set_show_close_button(False)
        dialog.connect('delete-event', lambda *_: True)
        body = dialog.get_content_area()
        body.set_border_width(28)
        body.set_spacing(16)
        dialog.spinner = Gtk.Spinner(width_request=32, height_request=32, halign=Gtk.Align.CENTER)
        dialog.spinner.start()
        body.pack_start(dialog.spinner, False, False, 0)
        body.pack_start(label(description, 'subtitle', True), False, False, 0)
        return dialog

    def build_plan_dialog(self, plan):
        dialog = dialog_shell(self,'Review Removal',760,560)
        # Keep consent and the destructive action together, in reading order.
        confirm = Gtk.Button(label=tr('Uninstall'))
        confirm.get_style_context().add_class('destructive-action')
        confirm.set_sensitive(False)
        confirm.connect('clicked', lambda _: dialog.response(Gtk.ResponseType.OK))
        body = dialog.get_content_area()
        body.set_border_width(20)
        body.set_spacing(12)
        hero = Gtk.Box(spacing=12)
        hero.pack_start(Gtk.Image.new_from_pixbuf(icon_pixbuf(plan.app.icon,44,self.dark)),False,False,0)
        info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=5)
        info.pack_start(label(plan.app.name,'section-title'),False,False,0)
        total=len(plan.removed)
        summary=tr('{count} items to remove',count=total)
        if plan.extra:
            summary+=tr(' · {count} extra dependencies',count=len(plan.extra))
        if plan.data:
            summary+=tr(' · {count} data locations',count=len(plan.data))
        info.pack_start(label(summary,'subtitle'),False,False,0)
        hero.pack_start(info,True,True,0)
        body.pack_start(hero,False,False,0)
        body.pack_start(text_box(self.describe_plan(plan),280)[0],True,True,0)
        footer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        footer.get_style_context().add_class('confirmation-card')
        footer.pack_start(label('Confirm before removing', 'confirmation-title'),False,False,0)
        acknowledgement = Gtk.CheckButton(label=tr('I have checked the list and agree to remove these items'))
        acknowledgement.get_style_context().add_class('confirmation-check')
        footer.pack_start(acknowledgement,False,False,0)
        hint = label('Tick the checkbox above to enable Uninstall.', 'subtitle', True)
        footer.pack_start(hint,False,False,0)
        def consent_changed(widget):
            accepted = widget.get_active()
            confirm.set_sensitive(accepted)
            hint.set_text(tr('Ready to remove. Click Uninstall to continue.' if accepted else
                             'Tick the checkbox above to enable Uninstall.'))
        acknowledgement.connect('toggled', consent_changed)
        actions = Gtk.Box(spacing=10, halign=Gtk.Align.END)
        cancel = Gtk.Button(label=tr('Cancel'))
        cancel.connect('clicked',lambda _:dialog.response(Gtk.ResponseType.CANCEL))
        actions.pack_start(cancel,False,False,0)
        actions.pack_start(confirm,False,False,0)
        footer.pack_start(actions,False,False,0)
        body.pack_start(footer,False,False,0)
        dialog.confirm_button, dialog.acknowledgement = confirm, acknowledgement
        return dialog

    def describe_plan(self, plan):
        lines = [tr('WILL BE REMOVED ({count})',count=len(plan.removed)),*plan.removed]
        if plan.extra:
            lines += ['',tr('NEWLY UNUSED DEPENDENCIES ({count})',count=len(plan.extra)),*plan.extra]
        if plan.files:
            lines += ['',tr('INSTALLATION FILES → TRASH'),*plan.files]
        if plan.data:
            lines += ['',tr('USER DATA → TRASH'),*plan.data]
        if plan.notes:
            lines += ['',tr('NOTES'),*[tr(note) for note in plan.notes]]
        import shlex
        lines += ['',tr('COMMANDS'),*[shlex.join(c) for c in plan.commands]]
        return '\n'.join(lines)

    def show_plan(self, plan, error):
        if error:
            self.message('Removal preview unavailable',error)
            return
        if self.run_dialog(self.build_plan_dialog(plan)) == Gtk.ResponseType.OK:
            self.perform(plan)
        else:
            self.status.set_text(tr('Preview closed · Nothing changed'))

    def build_progress_dialog(self, app):
        dialog = dialog_shell(self,'Removal Progress',720,500,[('Close',Gtk.ResponseType.CLOSE,None)])
        dialog.close_button = dialog.get_widget_for_response(Gtk.ResponseType.CLOSE)
        dialog.close_button.set_sensitive(False)
        dialog.connect('delete-event',lambda *_:self.mutating)
        body = dialog.get_content_area()
        body.set_border_width(18)
        body.set_spacing(14)
        banner = Gtk.Box(spacing=12)
        banner.get_style_context().add_class('outcome-banner')
        banner.get_style_context().add_class('outcome-pending')
        dialog.outcome_icon = Gtk.Label(label='…')
        dialog.outcome_icon.get_style_context().add_class('outcome-symbol')
        dialog.outcome_stack = Gtk.Stack()
        dialog.progress_spinner = Gtk.Spinner(width_request=32, height_request=32, valign=Gtk.Align.CENTER)
        dialog.progress_spinner.start()
        dialog.outcome_stack.add_named(dialog.progress_spinner, 'running')
        dialog.outcome_stack.add_named(dialog.outcome_icon, 'result')
        dialog.outcome_stack.show_all()
        dialog.outcome_stack.set_visible_child_name('running')
        banner.pack_start(dialog.outcome_stack,False,False,0)
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=5)
        dialog.outcome_heading = label(tr('Uninstalling {name}…',name=app.name),'section-title')
        dialog.outcome_detail = label('Removal is running. Please wait.','subtitle',True)
        dialog.outcome_detail.set_max_width_chars(65)
        text.pack_start(dialog.outcome_heading,False,False,0)
        text.pack_start(dialog.outcome_detail,False,False,0)
        banner.pack_start(text,True,True,0)
        body.pack_start(banner,False,False,0)
        scroll,dialog.progress_view = text_box('',260)
        body.pack_start(scroll,True,True,0)
        dialog.outcome_banner = banner
        return dialog

    def complete_progress(self, dialog, app, error):
        failed = error is not None
        dialog.progress_spinner.stop()
        dialog.outcome_stack.set_visible_child_name('result')
        context = dialog.outcome_banner.get_style_context()
        context.remove_class('outcome-pending')
        context.add_class('outcome-error' if failed else 'outcome-success')
        dialog.outcome_icon.set_text('!' if failed else '✓')
        dialog.outcome_heading.set_text(tr('Removal incomplete' if failed else 'Successfully removed'))
        dialog.outcome_detail.set_text(
            tr('{name} could not be completely removed.' if failed else '{name} was removed successfully.',name=app.name)
            +'\n'+tr('Some steps may have finished. Review the log before trying again.' if failed else
                      'The removal command finished successfully. Review the log below for details.'))
        dialog.close_button.set_sensitive(True)
        dialog.close_button.get_style_context().add_class('primary-action')
        self.status.set_text(tr('Removal incomplete · See Activity for its log') if failed else
                             tr('Successfully removed {name} · See Activity for its log',name=app.name))

    def perform(self, plan):
        self.mutating = True
        dialog = self.build_progress_dialog(plan.app)
        view = dialog.progress_view
        lines = []
        def append(text):
            lines.append(text)
            def update():
                buffer = view.get_buffer()
                buffer.insert(buffer.get_end_iter(),text)
                view.scroll_to_iter(buffer.get_end_iter(),0.0,False,0,1)
                return False
            GLib.idle_add(update)
        def finished(_, error):
            self.mutating = False
            if error is not None:
                append('\n'+error+'\n')
            self.complete_progress(dialog,plan.app,error)
            self.activity.append({'time':datetime.datetime.now().strftime('%H:%M'),'app':plan.app.name,
                                  'result':'Incomplete' if error is not None else 'Completed','log':''.join(lines)})
        dialog.show_all()
        self.async_work(lambda:backend.execute(plan,append),finished)
        dialog.run()
        dialog.destroy()
        self.refresh()

    def build_activity_dialog(self):
        dialog = dialog_shell(self,'Activity',680,430,[('Close',Gtk.ResponseType.CLOSE,None)])
        body = dialog.get_content_area()
        body.set_border_width(20)
        body.set_spacing(10)
        body.pack_start(label('This session','section-title'),False,False,0)
        if not self.activity:
            body.pack_start(label('No removals yet. Completed and interrupted operations appear here. Logs remain in memory for this session.','subtitle',True),True,True,0)
        else:
            scroll=Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
            entries=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=7)
            for item in reversed(self.activity[-20:]):
                button = Gtk.Button(label=item['time']+'   '+item['app']+'   ·   '+tr(item['result']))
                button.get_child().set_ellipsize(Pango.EllipsizeMode.END)
                button.get_child().set_xalign(0)
                button.connect('clicked',lambda _,entry=item:self.show_text(entry['app']+' · '+tr(entry['result']),entry['log']))
                entries.pack_start(button,False,False,0)
            scroll.add(entries)
            body.pack_start(scroll,True,True,0)
        return dialog

    def show_activity(self):
        self.run_dialog(self.build_activity_dialog())

    def scan_status(self):
        enabled = ', '.join(self.prefs['enabled_sources']) or tr('None')
        text = tr('Enabled sources: {sources}',sources=enabled)+'\n\n'+(tr('Warnings:')+'\n'+'\n'.join(self.warnings) if self.warnings else tr('No source warnings in the last scan.'))
        self.show_text('Scan Status',text)

    def shortcuts(self):
        self.message('Keyboard Shortcuts','Ctrl+F   Search\nCtrl+R   Refresh\nCtrl+,   Settings\nCtrl+I   Selected software details\nCtrl+E   Export inventory\nCtrl+Q   Quit\nCtrl+C   Copy package ID while the list is focused\nEnter     Show details\nDelete    Review uninstall (never immediate deletion)\nShift+F10 / Menu key    Context menu')

    def about(self, _):
        self.message(tr('About SweepDesk {version}',version=VERSION),'\n\n'.join(tr(line) for line in [
            'Native software inventory and reviewed uninstall for major Linux desktops.',
            'Made by Zwart04 · GPL-3.0-or-later licensed original code.',
            'Known data cleanup is opt-in. Shared dependencies, caches, and uncertain files are preserved. See the online guide for each source’s limits.',
            REPOSITORY_URL])+ '\n'+tr('Buy me a coffee: {url}',url=SUPPORT_URL))

    def export(self, _):
        dialog = Gtk.FileChooserDialog(title=tr('Export Software Inventory'),transient_for=self,action=Gtk.FileChooserAction.SAVE)
        dialog.add_buttons(tr('Cancel'),Gtk.ResponseType.CANCEL,tr('Export'),Gtk.ResponseType.OK)
        dialog.set_current_name('sweepdesk-inventory.json')
        dialog.set_do_overwrite_confirmation(True)
        if dialog.run() == Gtk.ResponseType.OK:
            try:
                Path(dialog.get_filename()).write_text(json.dumps({'apps':[asdict(a) for a in self.apps],'warnings':self.warnings},ensure_ascii=False,indent=2)+'\n')
            except OSError as error:
                self.message('Export failed',str(error))
            else:
                self.status.set_text(tr('Inventory exported successfully.'))
        dialog.destroy()

    def on_close(self, *_):
        if self.mutating:
            self.message('Operation in progress','Wait until the current removal finishes so its result can be checked.')
            return True
        self.quit_loop()
        return False

    def quit_loop(self):
        if self.get_application():
            self.get_application().quit()
        elif Gtk.main_level():
            Gtk.main_quit()

    def save_screenshot(self):
        import cairo
        area = self.get_allocation()
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32,area.width,area.height)
        self.draw(cairo.Context(surface))
        surface.write_to_png(self.screenshot)
        self.quit_loop()
        return False


def main():
    parser = argparse.ArgumentParser(description='SweepDesk — software inventory and reviewed uninstall')
    parser.add_argument('--scan-json',action='store_true',help='Print the inventory as JSON without a window')
    parser.add_argument('--screenshot',help=argparse.SUPPRESS)
    parser.add_argument('--python',action='append',default=[],metavar='PATH',help='Also scan a Python interpreter/virtualenv')
    parser.add_argument('--manual-dir',action='append',default=[],metavar='PATH',help='Also scan direct executable children in this folder')
    parser.add_argument('--version',action='version',version='SweepDesk '+VERSION)
    args = parser.parse_args()
    if args.scan_json:
        apps,warnings = backend.scan(args.python,args.manual_dir)
        print(json.dumps({'apps':[asdict(a) for a in apps],'warnings':warnings},ensure_ascii=False,indent=2))
        return
    if os.geteuid()==0:
        raise SystemExit('Run SweepDesk as a regular user. Administrator authentication is only requested for system package operations.')
    GLib.set_application_name('SweepDesk')
    GLib.set_prgname(APP_ID)
    Gtk.Window.set_default_icon_from_file(str(ROOT/'assets/sweepdesk.svg'))
    application = Gtk.Application(application_id=APP_ID)
    quit_action=Gio.SimpleAction.new('quit',None)
    quit_action.connect('activate',lambda *_:application.main_window.on_close() if hasattr(application,'main_window') else application.quit())
    application.add_action(quit_action)
    def activate(app):
        if hasattr(app,'main_window'):
            app.main_window.present()
        else:
            app.main_window = Window(args.screenshot,args.python,args.manual_dir,application=app)
            app.main_window.present()
    application.connect('activate',activate)
    application.run([])


if __name__=='__main__':
    main()
