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
              b.App('Protected','protected','1','pip',readonly_reason='Externally managed')]
        with patch.object(ui.Window,'refresh'):
            window=ui.Window(prefs=dict(preferences.defaults(),language='en'))
        try:
            window.loaded((apps,[]),None)
            self.assertEqual(window.support_link.get_uri(),'https://tako.id/Zwart04')
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
        finally:
            window.destroy()

    def make_window(self):
        with patch.object(ui.Window,'refresh'):
            window=ui.Window(prefs=dict(preferences.defaults(),language='en'))
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


if __name__=='__main__':
    unittest.main()
