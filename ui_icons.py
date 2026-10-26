# SPDX-FileCopyrightText: 2026 Zwart04
# SPDX-License-Identifier: GPL-3.0-or-later
# SweepDesk: see LICENSE for copying terms and warranty disclaimer.
"""Original line icons for consistent controls across desktop themes."""
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GdkPixbuf

PATHS = {
 'trash':'<path d="M3 5h14M7 5V2.5h6V5M5 5l1 12h8l1-12M8 8v6m4-6v6"/>',
 'sidebar':'<rect x="2" y="2.5" width="16" height="15" rx="2"/><path d="M7 3v14"/>',
 'settings':'<path d="M3 5h14M3 10h14M3 15h14"/><path d="M7 3v4m6 1v4m-5 1v4" stroke-width="3.4"/>',
 'more':'<circle cx="4" cy="10" r=".9" fill="currentColor"/><circle cx="10" cy="10" r=".9" fill="currentColor"/><circle cx="16" cy="10" r=".9" fill="currentColor"/>',
 'refresh':'<path d="M16 6a7 7 0 1 0 1 7M16 2v5h-5"/>',
 'details':'<circle cx="10" cy="10" r="7.5"/><path d="M10 9v5"/><circle cx="10" cy="6" r=".6" fill="currentColor"/>',
 'list':'<path d="M7 5h10M7 10h10M7 15h10"/><path d="M3 5h.2M3 10h.2M3 15h.2" stroke-width="2.8"/>',
 'grid':'<rect x="2.5" y="2.5" width="6" height="6" rx="1"/><rect x="11.5" y="2.5" width="6" height="6" rx="1"/><rect x="2.5" y="11.5" width="6" height="6" rx="1"/><rect x="11.5" y="11.5" width="6" height="6" rx="1"/>',
 'apps':'<rect x="2.5" y="2.5" width="15" height="15" rx="3"/><path d="m6 13 4-7 4 7M7 11h6"/>',
 'terminal':'<rect x="2" y="3" width="16" height="14" rx="2"/><path d="m6 7 3 3-3 3m5 0h3"/>',
 'package':'<path d="m10 2 7 4v8l-7 4-7-4V6zM3 6l7 4 7-4m-7 4v8M6.5 4l7 4"/>',
 'folder':'<path d="M2 6V4.5A1.5 1.5 0 0 1 3.5 3H8l2 3h6.5A1.5 1.5 0 0 1 18 7.5v8a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 2 15.5z"/>',
 'search':'<circle cx="8.5" cy="8.5" r="5.5"/><path d="m13 13 4.5 4.5"/>',
 'minus':'<path d="M4 10h12"/>',
 'plus':'<path d="M4 10h12M10 4v12"/>',
}
ALIASES = {
 'view-sidebar-symbolic':'sidebar','emblem-system-symbolic':'settings','open-menu-symbolic':'more',
 'view-refresh-symbolic':'refresh','dialog-information-symbolic':'details','view-list-symbolic':'list',
 'view-grid-symbolic':'grid','applications-other-symbolic':'apps','utilities-terminal-symbolic':'terminal',
 'package-x-generic-symbolic':'package','folder-symbolic':'folder','system-search-symbolic':'search',
 'list-remove-symbolic':'minus','list-add-symbolic':'plus','folder-open-symbolic':'folder',
}


def pixbuf(name,size=16,dark=True):
    key=ALIASES.get(name,name)
    color='#c7c7ce' if dark else '#565660'
    paths=PATHS.get(key,PATHS['package']).replace('currentColor',color)
    svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 20 20"><g fill="none" stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">{paths}</g></svg>'
    loader=GdkPixbuf.PixbufLoader.new_with_type('svg')
    loader.write(svg.encode())
    loader.close()
    return loader.get_pixbuf()


def image(name,size=16):
    dark=Gtk.Settings.get_default().get_property('gtk-application-prefer-dark-theme')
    widget=Gtk.Image.new_from_pixbuf(pixbuf(name,size,dark))
    widget.sweepdesk_symbol=(name,size)
    return widget


def refresh(dark):
    def walk(widget):
        if isinstance(widget,Gtk.Image) and hasattr(widget,'sweepdesk_symbol'):
            name,size=widget.sweepdesk_symbol
            widget.set_from_pixbuf(pixbuf(name,size,dark))
        if isinstance(widget,Gtk.Container):
            for child in widget.get_children():
                walk(child)
    for window in Gtk.Window.list_toplevels():
        walk(window)
