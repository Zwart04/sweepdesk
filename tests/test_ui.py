# SPDX-FileCopyrightText: 2026 Zwart04
# SPDX-License-Identifier: GPL-3.0-or-later
# SweepDesk: see LICENSE for copying terms and warranty disclaimer.
"""Run with xvfb-run -a python3 -m unittest discover -s tests -p test_ui.py."""
import os
import unittest
from unittest.mock import patch

if os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY'):
    import sweepdesk as ui
    from gi.repository import Gtk
    import backend as b
    import preferences
else:
    ui = None


@unittest.skipIf(ui is None, 'A graphical session or Xvfb is required')
class UITests(unittest.TestCase):
    def test_icons_source_filter_and_support_link(self):
        apps=[b.decorate(b.App('curl','curl','1','APT'),{}),
              b.decorate(b.App('OpenCode','opencode','1','Manual'),{}),
              b.App('Protected','protected','1','pip',readonly_reason='Externally managed'),
              b.App('Horizon','horizon-launcher','—','Manual',manager='horizon-launcher')]
        with patch.object(ui.Window,'refresh'):
            window=ui.Window(prefs=dict(preferences.defaults(),language='en',auto_check_updates=False))
        try:
            window.loaded((apps,[]),None)
            self.assertEqual(window.support_link.get_uri(),'https://tako.id/Zwart04')
            self.assertEqual(window.support_link.get_label(),'Buy me a coffee')
            self.assertIsNotNone(window.support_link.get_image())
            self.assertIsNone(window.remove_button.get_image())
            self.assertTrue(window.remove_button.get_style_context().has_class('destructive-action'))
            window.search.set_text('opencode')
            window.refilter()
            self.assertEqual(len(window.filtered),1)
            window.tree.get_selection().select_path(Gtk.TreePath.new_from_indices([0]))
            self.assertEqual(window.active_app().package,'opencode')
            self.assertTrue(window.remove_button.get_sensitive())
            window.search.set_text('protected')
            window.refilter()
            window.tree.get_selection().select_path(Gtk.TreePath.new_from_indices([0]))
            self.assertFalse(window.remove_button.get_sensitive())
            window.search.set_text('horizon')
            window.refilter()
            window.tree.get_selection().select_path(Gtk.TreePath.new_from_indices([0]))
            self.assertTrue(window.remove_button.get_sensitive())
            self.assertFalse(ui.Window.app_is_cli(window.active_app()))
        finally:
            window.destroy()

    def make_window(self):
        with patch.object(ui.Window,'refresh'):
            window=ui.Window(prefs=dict(preferences.defaults(),language='en',auto_check_updates=False))
        apps=[b.decorate(b.App('curl','curl','1','APT',size=50),{}),
              b.App('Protected','protected','1','APT',essential=True,support=True),
              b.App('Example','example','1','pip',readonly_reason='Externally managed')]
        window.loaded((apps,[]),None)
        return window

    def test_compact_header_and_combined_icon_name_column(self):
        window=self.make_window()
        try:
            self.assertFalse(window.get_titlebar().get_has_subtitle())
            columns=window.tree.get_columns()
            self.assertEqual([c.get_title() for c in columns],['Name','Version','Source','Size'])
            self.assertEqual(len(columns[0].get_cells()),2)
            self.assertEqual(window.icon_size,24)
        finally:
            window.destroy()

    def test_context_menu_respects_readonly_and_core_packages(self):
        window=self.make_window()
        try:
            for query,can_remove in [('curl',True),('protected',False),('example',False)]:
                window.search.set_text(query)
                window.refilter()
                window.tree.get_selection().select_path(Gtk.TreePath.new_from_indices([0]))
                menu=window.build_context_menu()
                items={item.get_label():item for item in menu.get_children() if isinstance(item,Gtk.MenuItem)}
                self.assertIn('Copy Package ID',items)
                self.assertIn('Show Details',items)
                self.assertEqual(items['Review Uninstall…'].get_sensitive(),can_remove)
                menu.destroy()
        finally:
            window.destroy()

    def test_view_button_opens_and_changes_real_display_options(self):
        window=self.make_window()
        try:
            self.assertTrue(window.view_button.get_sensitive())
            popover=window.view_button.get_popover()
            self.assertIsNotNone(popover)
            window.view_button.clicked()
            while Gtk.events_pending(): Gtk.main_iteration_do(False)
            self.assertTrue(popover.get_visible())
            self.assertTrue(window.view_button.get_active())
            with patch.object(window,'persist') as persist:
                system=popover.view_controls['show_system']
                system.set_active(True)
                self.assertTrue(window.prefs['show_system'])
                self.assertEqual(len(window.filtered),3)
                system.set_active(False)
                self.assertEqual(len(window.filtered),2)
                details=popover.view_controls['show_details']
                details.set_active(not details.get_active())
                self.assertEqual(window.prefs['show_details'],details.get_active())
                popover.density_control.set_active(1)
                self.assertEqual(window.icon_size,32)
                persist.assert_called()
            popover.hide()
            window.prefs['density']='compact'
            window.prefs['show_system']=True
            with patch.object(window,'persist') as persist:
                window.view_button.set_active(False)
                window.view_button.clicked()
                while Gtk.events_pending(): Gtk.main_iteration_do(False)
                self.assertTrue(popover.view_controls['show_system'].get_active())
                self.assertEqual(popover.density_control.get_active(),0)
                persist.assert_not_called()
        finally: window.destroy()

    def test_settings_dialog_and_review_guard(self):
        window=self.make_window()
        try:
            settings=window.build_settings_dialog()
            self.assertEqual(set(settings.source_controls),set(b.SOURCES))
            self.assertIn('theme',settings.settings_controls)
            self.assertIn('remember_folders',settings.settings_controls)
            settings.show_all()
            settings.settings_stack.set_visible_child_name('Sources')
            self.assertEqual(settings.settings_stack.get_visible_child_name(),'Sources')
            settings.destroy()
            plan=b.Plan(window.apps[0],removed=['curl'])
            dialog=window.build_plan_dialog(plan)
            self.assertFalse(dialog.confirm_button.get_sensitive())
            dialog.acknowledgement.set_active(True)
            self.assertTrue(dialog.confirm_button.get_sensitive())
            dialog.destroy()
        finally:
            window.destroy()

    def test_empty_state_and_light_theme(self):
        window=self.make_window()
        try:
            window.search.set_text('no-such-application')
            window.refilter()
            self.assertEqual(window.list_stack.get_visible_child_name(),'empty')
            self.assertFalse(window.remove_button.get_sensitive())
            window.prefs['theme']='light'
            window.apply_style()
            window.apply_density()
            self.assertFalse(window.dark)
        finally:
            window.destroy()

    def test_scan_stays_loading_through_filter_changes_and_recovers(self):
        window=self.make_window()
        completions=[]
        try:
            window.loaded(([],[]),None)
            # Defer the scan result: filter changes must not show the empty prompt.
            with patch.object(window,'async_work',side_effect=lambda work,done:completions.append(done)):
                window.refresh()
            window.search.set_text('no-such-app')
            window.refilter()
            self.assertEqual(window.list_stack.get_visible_child_name(),'loading')
            self.assertEqual(window.counter.get_text(),'Loading…')
            self.assertTrue(window.loading_spinner.get_property('active'))
            completions.pop()((window.apps,[]),None)
            self.assertEqual(window.list_stack.get_visible_child_name(),'empty')
            self.assertFalse(window.loading_spinner.get_property('active'))
            with patch.object(window,'async_work',side_effect=lambda work,done:completions.append(done)):
                window.refresh()
            completions.pop()(None,'fixture scan failure')
            self.assertFalse(window.scanning)
            self.assertFalse(window.loading_spinner.get_property('active'))
            self.assertNotEqual(window.list_stack.get_visible_child_name(),'loading')
        finally: window.destroy()

    def test_review_consent_and_action_follow_reading_order(self):
        window=self.make_window()
        try:
            dialog=window.build_plan_dialog(b.Plan(window.apps[0],removed=['curl']))
            dialog.show_all()
            while Gtk.events_pending(): Gtk.main_iteration_do(False)
            self.assertGreater(dialog.confirm_button.get_allocation().y,dialog.acknowledgement.get_allocation().y)
            self.assertIsNone(dialog.confirm_button.get_image())
            self.assertTrue(dialog.confirm_button.get_style_context().has_class('destructive-action'))
            self.assertFalse(dialog.confirm_button.get_sensitive())
            dialog.acknowledgement.set_active(True)
            self.assertTrue(dialog.confirm_button.get_sensitive())
            dialog.acknowledgement.set_active(False)
            self.assertFalse(dialog.confirm_button.get_sensitive())
            dialog.destroy()
            progress=window.build_progress_dialog(window.apps[0])
            self.assertTrue(progress.progress_spinner.get_property('active'))
            window.complete_progress(progress,window.apps[0],None)
            self.assertFalse(progress.progress_spinner.get_property('active'))
            self.assertEqual(progress.outcome_stack.get_visible_child_name(),'result')
            progress.destroy()
        finally: window.destroy()

    def test_search_keeps_description_matches_and_renders_description_safely(self):
        window=self.make_window()
        try:
            apps=[b.App('Firefox ESR','firefox-esr','1','APT',description='Web browser'),
                  b.App('libraw1394-11','libraw1394-11','1','APT',description='IEEE 1394 (FireWire) <bus> & library',support=True)]
            window.loaded((apps,[]),None)
            window.search.set_text('fire')
            window.refilter()
            self.assertEqual(len(window.filtered),2)
            iterator=window.sort_model.get_iter_first()
            window.render_software_name(window.name_column,window.name_renderer,window.sort_model,iterator)
            markup=window.name_renderer.get_property('text')
            self.assertIn('Web browser',markup)
            iterator=window.sort_model.iter_next(iterator)
            window.render_software_name(window.name_column,window.name_renderer,window.sort_model,iterator)
            markup=window.name_renderer.get_property('text')
            self.assertIn('FireWire',markup)
            self.assertIn('<bus> & library',markup)
        finally:
            window.destroy()

    def test_indonesian_switch_preserves_inventory_and_confirmation(self):
        window=self.make_window()
        replacement=None
        try:
            window.search.set_text('curl')
            window.activity=[{'time':'12:00','app':'Example','result':'Completed','log':'fixture'}]
            window.prefs['language']='id'
            replacement=window.rebuild_language()
            self.assertEqual(replacement.page_title.get_text(),'Perangkat Lunak Terpasang')
            self.assertEqual(replacement.name_column.get_title(),'Nama')
            self.assertEqual(replacement.search.get_placeholder_text(),'Cari perangkat lunak…')
            self.assertEqual(replacement.search.get_text(),'curl')
            self.assertEqual(len(replacement.apps),3)
            self.assertEqual(len(replacement.activity),1)
            settings=replacement.build_settings_dialog()
            self.assertEqual(settings.get_title(),'Pengaturan')
            self.assertEqual(settings.settings_controls['language'].get_active_id(),'id')
            self.assertEqual(settings.settings_controls['theme'].get_active_id(),'dark')
            settings.destroy()
            plan=b.Plan(replacement.apps[0],removed=['curl'])
            dialog=replacement.build_plan_dialog(plan)
            self.assertFalse(dialog.confirm_button.get_sensitive())
            self.assertIn('AKAN DIHAPUS',replacement.describe_plan(plan))
            self.assertIn('curl',replacement.describe_plan(plan))
            dialog.destroy()
        finally:
            if replacement: replacement.destroy()
            else: window.destroy()
            ui.i18n.configure('en')

    def test_success_and_failure_are_distinct_and_do_not_execute_removal(self):
        window=self.make_window()
        try:
            app=window.apps[0]
            for error,expected,style in [(None,'Successfully removed','outcome-success'),('fixture failure','Removal incomplete','outcome-error'),('','Removal incomplete','outcome-error')]:
                dialog=window.build_progress_dialog(app)
                self.assertFalse(dialog.close_button.get_sensitive())
                with patch.object(b,'execute') as execute:
                    window.complete_progress(dialog,app,error)
                    execute.assert_not_called()
                self.assertEqual(dialog.outcome_heading.get_text(),expected)
                self.assertTrue(dialog.outcome_banner.get_style_context().has_class(style))
                self.assertTrue(dialog.close_button.get_sensitive())
                self.assertIn(app.name,dialog.outcome_detail.get_text())
                dialog.destroy()
        finally:
            window.destroy()

    def test_manual_update_stays_in_one_actionable_dialog(self):
        import updater
        window=self.make_window()
        callbacks=[]
        class ImmediateThread:
            def __init__(self,target,**kwargs): self.target=target
            def start(self): self.target()
        try:
            release=updater.Release('0.6.0',())
            with patch.object(ui.threading,'Thread',ImmediateThread),patch.object(updater,'check',return_value=release), \
                 patch.object(updater,'packaged_install',return_value=True),patch.object(updater,'package_name',return_value='fixture.deb'), \
                 patch.object(ui.native_packages,'immutable_system',return_value=False),patch.object(window,'persist'), \
                 patch.object(window,'async_work',side_effect=lambda work,done:callbacks.append(done)), \
                 patch.object(window,'open_uri') as open_uri,patch.object(updater,'download') as download:
                window.check_updates(True)
                while Gtk.events_pending(): Gtk.main_iteration_do(False)
                dialog=window.update_dialog
                self.assertEqual(dialog.state,'available')
                self.assertEqual(dialog.update_action.get_label(),'Update Now')
                dialog.update_action.clicked()
                self.assertIs(window.update_dialog,dialog)
                self.assertEqual(dialog.state,'installing')
                self.assertTrue(dialog.spinner.get_property('active'))
                self.assertFalse(dialog.close_button.get_sensitive())
                callbacks.pop()(None,'fixture authentication cancelled')
                self.assertEqual(dialog.state,'error')
                self.assertTrue(dialog.error_details.get_visible())
                self.assertFalse(dialog.error_details.get_expanded())
                buffer=dialog.error_view.get_buffer()
                self.assertIn('fixture authentication cancelled',buffer.get_text(buffer.get_start_iter(),buffer.get_end_iter(),True))
                self.assertFalse(window.mutating)
                dialog.update_action.clicked()
                self.assertEqual(dialog.state,'installing')
                callbacks.pop()(None,None)
                self.assertEqual(dialog.state,'installed')
                self.assertEqual(dialog.update_action.get_label(),'Restart SweepDesk')
                self.assertTrue(dialog.close_button.get_sensitive())
                open_uri.assert_not_called()
                download.assert_not_called()
        finally: window.destroy()

    def test_closing_update_check_does_not_reopen_a_popup(self):
        import updater
        window=self.make_window()
        workers=[]
        class DeferredThread:
            def __init__(self,target,**kwargs): self.target=target
            def start(self): workers.append(self.target)
        try:
            with patch.object(ui.threading,'Thread',DeferredThread),patch.object(updater,'check',return_value=None),patch.object(window,'persist'):
                window.check_updates(True)
                dialog=window.update_dialog
                self.assertEqual(dialog.state,'checking')
                dialog.destroy()
                workers.pop()()
                while Gtk.events_pending(): Gtk.main_iteration_do(False)
                self.assertIsNone(window.update_dialog)
                self.assertFalse(window.update_checking)
        finally: window.destroy()

    def test_native_sorting_and_selection_survive_filter_changes(self):
        window=self.make_window()
        try:
            apps=[b.App('Zulu','zulu','1','APT',size=10),b.App('alpha','alpha','1','npm',size=2**34)]
            window.loaded((apps,[]),None)
            self.assertEqual([row[1] for row in window.sort_model],['alpha','Zulu'])
            window.tree.get_selection().select_path(Gtk.TreePath.new_from_indices([0]))
            window.search.set_text('a');window.refilter()
            self.assertEqual(window.active_app().package,'alpha')
            window.search.set_text('');window.refilter()
            window.sort.set_active(2)
            self.assertEqual([row[1] for row in window.sort_model],['alpha','Zulu'])
            size_column=window.tree.get_columns()[-1]
            size_column.emit('clicked')
            self.assertEqual([row[1] for row in window.sort_model],['Zulu','alpha'])
            window.search.set_text('alpha');window.refilter()
            self.assertEqual(window.active_app().package,'alpha')
            window.search.set_text('no-match');window.refilter()
            self.assertIsNone(window.active_app())
        finally: window.destroy()

    def test_refresh_keeps_existing_list_and_reuses_shared_icons(self):
        window=self.make_window()
        try:
            window.icons.clear()
            apps=[b.App('Example '+str(i),'example-'+str(i),'1','APT',icon='package-x-generic') for i in range(100)]
            with patch.object(ui,'icon_pixbuf',wraps=ui.icon_pixbuf) as decode:
                window.loaded((apps,[]),None)
                self.assertEqual(decode.call_count,1)
            with patch.object(window,'async_work'):
                window.refresh()
            self.assertTrue(window.scanning)
            self.assertEqual(window.list_stack.get_visible_child_name(),'list')
            self.assertEqual(len(window.filtered),100)
        finally: window.destroy()

    def test_github_release_displays_update_button_without_installing(self):
        from pathlib import Path
        import tempfile
        import updater
        window=self.make_window()
        class ImmediateThread:
            def __init__(self,target,**kwargs): self.target=target
            def start(self): self.target()
        try:
            with tempfile.TemporaryDirectory() as directory:
                window.prefs_file=Path(directory)/'preferences.json'
                release=updater.Release('0.6.0',())
                with patch.object(ui.threading,'Thread',ImmediateThread),patch.object(updater,'check',return_value=release),patch.object(updater,'download') as download:
                    window.check_updates(False)
                    while Gtk.events_pending(): Gtk.main_iteration_do(False)
                    self.assertTrue(window.update_banner.get_reveal_child())
                    self.assertEqual(window.update_button.get_label(),'Update Now')
                    self.assertIn('0.6.0',window.update_label.get_text())
                    download.assert_not_called()
                menu=window.build_more_menu()
                titles=[item.get_label() for item in menu.get_children() if isinstance(item,Gtk.MenuItem)]
                self.assertIn('Check for Updates…',titles)
                menu.destroy()
                with patch.object(updater,'packaged_install',return_value=False),patch.object(window,'message'),patch.object(window,'open_uri') as open_uri:
                    window.update_clicked()
                    open_uri.assert_not_called()
                    window.update_clicked(confirmed=True)
                    open_uri.assert_called_once_with(release.url)
        finally: window.destroy()


if __name__=='__main__':
    unittest.main()
