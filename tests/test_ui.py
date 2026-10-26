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
            window=ui.Window(prefs=preferences.defaults())
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
            window=ui.Window(prefs=preferences.defaults())
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


if __name__=='__main__':
    unittest.main()
