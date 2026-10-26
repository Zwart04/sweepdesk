#!/usr/bin/python3
# SPDX-FileCopyrightText: 2026 Zwart04
# SPDX-License-Identifier: GPL-3.0-or-later
# SweepDesk: see LICENSE for copying terms and warranty disclaimer.
"""Render native interface states with sample data; no uninstall handlers run."""
from pathlib import Path
import sys
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import cairo
import backend as b
import preferences
import sweepdesk as ui
from gi.repository import Gtk,GLib,Gdk

OUT=ROOT/'.work/ui-review'
OUT.mkdir(parents=True,exist_ok=True)
apps=[b.decorate(b.App('Command Code','command-code','1.88.0','npm',scope='User installation'),{}),
      b.decorate(b.App('curl','curl','8.14.1','APT',description='Command-line transfer tool',size=523264),{}),
      b.decorate(b.App('OpenCode','opencode','1.4.0','Manual',description='Native CLI installation',scope='User installation'),{}),
      b.App('Firefox ESR','firefox-esr','1.0','APT',description='Web browser'),
      b.App('libraw1394-11','libraw1394-11','2.1.2','APT',support=True,description='Library for IEEE 1394 bus access (FireWire)')]
with patch.object(ui.Window,'refresh'):
    window=ui.Window(prefs=dict(preferences.defaults(),language='en',auto_check_updates=False))
window.loaded((apps,[]),None)
window.status.set_text('Sample inventory · Interface review · No packages are being changed')
window.tree.get_selection().select_path(Gtk.TreePath.new_from_indices([0]))
plan=b.Plan(apps[1],commands=[['apt-get','purge','curl']],removed=['curl'],notes=['Sample preview only. No command is executed.'])


def capture(widget,name):
    allocation=widget.get_allocation()
    surface=cairo.ImageSurface(cairo.FORMAT_ARGB32,max(1,allocation.width),max(1,allocation.height))
    widget.draw(cairo.Context(surface))
    surface.write_to_png(str(OUT/(name+'.png')))


steps=[]
def main_view():
    capture(window,'main-dark')
    dialog=window.build_settings_dialog()
    return dialog,'settings'
def success():
    dialog=window.build_progress_dialog(apps[0]);window.complete_progress(dialog,apps[0],None)
    return dialog,'success'
def failure():
    dialog=window.build_progress_dialog(apps[0]);window.complete_progress(dialog,apps[0],'Sample failure')
    return dialog,'failure'
def search():
    window.search.set_text('fire');window.refilter()
    return window,'search-description'
def details(): return window.build_details_dialog(apps[2]),'details'
def settings_page(name):
    dialog=window.build_settings_dialog()
    dialog.show_all()
    dialog.settings_stack.set_visible_child_name(name)
    return dialog,'settings-'+name.lower().replace(' & ','-').replace(' ','-')
def loading_id():
    window.scanning=True;window.loading_spinner.start();window.refilter()
    return window,'loading-id'
def review_id():
    window.scanning=False;window.loading_spinner.stop();window.refilter()
    return window.build_plan_dialog(plan),'review-id'
def running_id(): return window.build_progress_dialog(apps[0]),'running-id'
def preparing_id(): return window.build_loading_dialog('Preparing a removal preview…','Checking which packages and data would be removed. Please wait.'),'preparing-id'
def updates_id():
    dialog=window.build_settings_dialog();dialog.show_all();dialog.settings_stack.set_visible_child_name('Updates')
    return dialog,'updates-id'
def context():
    window.tree.get_selection().select_path(Gtk.TreePath.new_from_indices([0]))
    menu=window.build_context_menu()
    menu.popup_at_widget(window.tree,Gdk.Gravity.CENTER,Gdk.Gravity.NORTH_WEST,None)
    return menu,'context-menu'
def options(): return window.build_options_dialog(apps[1]),'options'
def preview(): return window.build_plan_dialog(plan),'review'
def activity(): return window.build_activity_dialog(),'activity'
def indonesian():
    window.prefs['language']='id';window.prefs['theme']='dark';window.apply_style();ui.i18n.configure('id')
    dialog=window.build_settings_dialog()
    return dialog,'settings-id'
def indonesian_main():
    global window
    window=window.rebuild_language()
    window.search.set_text('');window.refilter()
    return window,'main-id'
def empty():
    window.search.set_text('no-such-application');window.refilter()
    return window,'empty'
def light():
    window.search.set_text('');window.refilter()
    window.prefs['theme']='light';window.apply_style();window.apply_density();window.populate_sidebar()
    return window,'main-light'
steps=[main_view,lambda:settings_page('Scanning'),lambda:settings_page('Sources'),lambda:settings_page('About'),lambda:settings_page('Updates'),details,options,preview,activity,context,search,empty,light,indonesian,indonesian_main,loading_id,review_id,running_id,preparing_id,updates_id,success,failure]
index=0
def advance():
    global index
    if index>=len(steps):
        Gtk.main_quit();return False
    widget,name=steps[index]();index+=1
    widget.show_all()
    def snapshot():
        capture(widget,name)
        if widget is not window: widget.destroy()
        GLib.timeout_add(100,advance)
        return False
    GLib.timeout_add(300,snapshot)
    return False
GLib.timeout_add(400,advance)
Gtk.main()
print('Rendered states:',', '.join(p.name for p in sorted(OUT.glob('*.png'))))
