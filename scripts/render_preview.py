#!/usr/bin/python3
"""Create a public screenshot with a labeled sample inventory, never private local data."""
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import argparse
import preferences
import backend as b
import sweepdesk as ui
from gi.repository import Gtk, GLib

parser=argparse.ArgumentParser()
parser.add_argument('--language',choices=('en','id'),default='en')
args=parser.parse_args()
prefs=dict(preferences.defaults(),auto_check_updates=False);prefs['language']=args.language

apps=[
    b.App('Command Code','command-code','1.88.0','npm',description='Coding agent · global Node.js package',scope='User installation'),
    b.App('curl','curl','8.14.1','APT',description='Command line tool for transferring data',size=523264),
    b.App('Firefox','firefox','Stable','Flatpak',description='Web browser',icon='firefox-esr',scope='user'),
    b.App('Git','git','2.47.3','APT',description='Distributed version control',icon='git',size=48234496),
    b.App('npm','npm','11.19.1','npm',description='Node.js package manager'),
    b.App('OpenCode','opencode','1.4.0','Manual',description='Native CLI installation · official OpenCode icon',scope='User installation'),
    b.App('ruff','ruff','0.14.0','uv',description='Python linter and formatter'),
    b.App('Visual Studio Code','code','Stable','APT',description='Code editor',icon='visual-studio-code'),
]
for a in apps:
    b.decorate(a,{})
with patch.object(ui.Window,'refresh'):
    window=ui.Window(prefs=prefs)
window.loaded((apps,[]),None)
window.status.set_text('Daftar contoh · Data pribadi tidak digunakan' if args.language=='id' else 'Sample inventory · No private inventory is shown')
for i,row in enumerate(window.filtered):
    if window.apps[row[5]].package=='opencode':
        window.tree.get_selection().select_path(Gtk.TreePath.new_from_indices([i]))
        break
window.remove_button.set_sensitive(False)
window.screenshot=str(ROOT/('docs/screenshot-id.png' if args.language=='id' else 'docs/screenshot.png'))
GLib.timeout_add(600,window.save_screenshot)
Gtk.main()
print(window.screenshot)
