# SPDX-FileCopyrightText: 2026 Zwart04
# SPDX-License-Identifier: GPL-3.0-or-later
# SweepDesk: see LICENSE for copying terms and warranty disclaimer.
"""Scoped native GTK styling; no fake macOS window controls."""
BASE = '''
* { font-family: "Inter", "Cantarell", "Noto Sans", sans-serif; font-size: 13px; }
window { background: @base; color: @fg; }
.sweep-dialog { background: @base; color: @fg; }
headerbar { min-height: 28px; padding: 3px 10px; background: @chrome; border-bottom: 1px solid @border; box-shadow: none; }
headerbar .title { font-size: 13px; font-weight: 600; }
headerbar .subtitle { font-size: 11px; color: @muted; opacity: 1; }
headerbar button { min-height: 24px; min-width: 24px; padding: 3px 7px; border-radius: 6px; }
headerbar .titlebutton { min-height: 20px; min-width: 20px; padding: 2px; margin: 0 2px; }
headerbar.compact-toolbar { min-height: 30px; padding: 1px 8px; }
headerbar.compact-toolbar button { min-height: 20px; min-width: 20px; padding: 2px 6px; margin-top: 0; margin-bottom: 0; }
.toolbar-title { font-size: 13px; font-weight: 600; }
button { min-height: 24px; padding: 5px 12px; border-radius: 7px; border: 1px solid @border; background: @button; color: @fg; box-shadow: none; text-shadow: none; }
button { transition: background-color 120ms ease-out, border-color 120ms ease-out; }
button:hover { background: @hover; }
button:disabled { color: @disabled; background: @surface; border-color: @border; }
button.flat { background: transparent; border-color: transparent; }
button.flat:hover { background: @hover; }
button.suggested-action { background: #0a84ff; color: white; border-color: #0a84ff; font-weight: 600; }
button.suggested-action:hover { background: #409cff; }
button.primary-action { background: #0a84ff; color: white; border-color: #0a84ff; font-weight: 600; }
button.primary-action:hover { background: #409cff; }
button.destructive-action { background: #e34850; color: white; border-color: #e34850; }
button.coffee-pill { color: @coffeefg; min-height: 22px; padding: 2px 12px; border-radius: 999px; background: @coffeebg; border: 1px solid @coffeeborder; box-shadow: inset 0 1px rgba(255,255,255,.22), 0 1px 2px rgba(0,0,0,.12); }
button.coffee-pill label { color: @coffeefg; text-decoration: none; font-size: 11px; font-weight: 600; }
button.coffee-pill:hover { background: @coffeehover; }
button.primary-action:disabled, button.suggested-action:disabled, button.destructive-action:disabled { background: @surface; color: @disabled; border-color: @border; }
.sidebar { background: @sidebar; border-right: 1px solid @border; }
.sidebar list { background: transparent; }
.nav-section { color: @muted; font-size: 10px; font-weight: 700; }
row.nav-row { border-radius: 7px; padding: 6px 8px; margin: 1px 8px; color: @secondary; }
row.nav-row:selected { background: @navselected; color: @fg; }
row.nav-row:hover { background: @hover; }
.nav-count { font-size: 10px; color: @muted; }
.page-title { font-size: 21px; font-weight: 700; }
.section-title { font-size: 16px; font-weight: 600; }
.subtitle { color: @secondary; font-size: 12px; }
.caption { color: @muted; font-size: 11px; }
.count-badge { color: @secondary; background: @surface; border-radius: 6px; padding: 3px 7px; font-size: 10px; }
entry { min-height: 24px; padding: 5px 8px; border: 1px solid @border; border-radius: 7px; background: @surface; color: @fg; box-shadow: none; }
entry:focus { border-color: #0a84ff; }
.software-frame { border: 1px solid @border; border-radius: 9px; background: @base; }
treeview { background: @base; color: @fg; border-color: @rowborder; }
treeview { -GtkTreeView-horizontal-separator: 4; }
treeview:selected { background: #185db4; color: #ffffff; }
treeview header button { min-height: 18px; padding: 5px 10px; border: 0; border-bottom: 1px solid @border; border-radius: 0; background: @surface; color: @secondary; font-size: 11px; font-weight: 600; }
treeview header button:hover { background: @hover; }
.inspector { background: @surface; border: 1px solid @border; border-radius: 9px; padding: 14px; }
.inspector-title { font-size: 15px; font-weight: 600; }
.statusbar { color: @muted; font-size: 11px; }
.empty-title { font-size: 17px; font-weight: 600; }
.empty-icon { color: @muted; }
.card { background: @surface; border: 1px solid @border; border-radius: 9px; padding: 14px; }
.settings-sidebar { background: @sidebar; border-right: 1px solid @border; padding: 10px 0; }
.settings-sidebar list { background: @sidebar; }
.dialog-content, .settings-page, viewport { background: @base; }
.settings-stack, .settings-scroller, .settings-scroller viewport { background: @base; }
.settings-page { padding: 24px; }
.outcome-banner { padding: 14px; border-radius: 9px; border: 1px solid @border; background: @surface; }
.outcome-symbol { font-size: 30px; font-weight: 700; min-width: 36px; }
.outcome-success { border-color: @successborder; background: @successbg; }
.outcome-success .section-title, .outcome-success .outcome-symbol { color: @successfg; }
.outcome-error { border-color: @errorborder; background: @errorbg; }
.outcome-error .section-title, .outcome-error .outcome-symbol { color: @errorfg; }
.confirmation-card { background: @surface; border: 1px solid @border; border-radius: 9px; padding: 16px; }
.confirmation-title { font-weight: 600; color: @fg; }
checkbutton.confirmation-check { color: @fg; padding: 5px 0; }
checkbutton.confirmation-check check { min-width: 20px; min-height: 20px; border: 2px solid #0a84ff; border-radius: 5px; }
checkbutton.confirmation-check:focus check { outline: 2px solid #409cff; outline-offset: 2px; }
.confirmation-card button { min-height: 28px; padding: 6px 16px; }
spinner { color: #0a84ff; }
spinner.loading-spinner { min-width: 40px; min-height: 40px; }
.settings-scroller undershoot { background-image: none; }
stacksidebar row { border-radius: 6px; margin: 2px 8px; padding: 8px; }
stacksidebar row:selected { background: @navselected; color: @fg; }
stacksidebar row:selected label { color: @fg; }
switch { min-height: 20px; min-width: 38px; }
switch:checked { background: #0a84ff; border-color: #0a84ff; }
switch slider { background: #ffffff; border-radius: 999px; border: 1px solid rgba(0,0,0,.14); min-height: 16px; min-width: 16px; }
checkbutton { color: @secondary; }
check { background: @surface; border-color: @muted; }
check:checked { background: #0a84ff; color: white; }
textview, textview text { background: @surface; color: @fg; }
textview { font-family: monospace; font-size: 11px; }
menu, menuitem, popover { background: @surface; color: @fg; border-color: @border; }
menu { padding: 5px; border-radius: 9px; }
menuitem { padding: 5px 10px; border-radius: 5px; }
menuitem:hover { background: #185db4; color: white; }
menuitem:disabled, menuitem:disabled label { color: @disabled; }
separator { background: @border; min-height: 1px; }
infobar { background: @surface; color: @fg; }
selection { background: #185db4; color: white; }
'''

DARK = {'successborder':'#35694c','successbg':'#20382b','successfg':'#7bdaa0',
        'errorborder':'#80444d','errorbg':'#40282e','errorfg':'#ff9ba8','base':'#1e1e20','chrome':'#29292c','fg':'#f2f2f5','secondary':'#b5b5bc',
        'muted':'#8d8d96','border':'#39393e','rowborder':'#2b2b30','button':'#36363a',
        'hover':'#3c3c41','disabled':'#66666f','surface':'#29292d','sidebar':'#252528',
        'navselected':'#404046','coffeebg':'#ead0a5','coffeeborder':'#f1dec0',
        'coffeefg':'#493315','coffeehover':'#f2ddb9'}
LIGHT = {'successborder':'#a1d1b0','successbg':'#edf8f0','successfg':'#176d37',
         'errorborder':'#e3a4ac','errorbg':'#fff0f2','errorfg':'#b4243a','base':'#ffffff','chrome':'#f0f0f2','fg':'#202024','secondary':'#62626b',
         'muted':'#80808a','border':'#dcdce1','rowborder':'#ededf1','button':'#ffffff',
         'hover':'#e8e8ed','disabled':'#a8a8b0','surface':'#f6f6f8','sidebar':'#efeff2',
         'navselected':'#dcdce4','coffeebg':'#f8dfac','coffeeborder':'#ebca8c',
         'coffeefg':'#66431a','coffeehover':'#ffe9c2'}


def stylesheet(dark=True):
    text = BASE
    for key, value in sorted((DARK if dark else LIGHT).items(), key=lambda item: -len(item[0])):
        text = text.replace('@'+key, value)
    return text.encode()
