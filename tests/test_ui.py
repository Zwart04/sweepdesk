"""Run with xvfb-run -a python3 -m unittest discover -s tests -p test_ui.py."""
import os
import unittest
from unittest.mock import patch

if os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY'):
    import sweepdesk as ui
    from gi.repository import Gtk
    import backend as b
else:
    ui = None


@unittest.skipIf(ui is None, 'A graphical session or Xvfb is required')
class UITests(unittest.TestCase):
    def test_icons_source_filter_and_support_link(self):
        apps=[b.decorate(b.App('curl','curl','1','APT'),{}),
              b.decorate(b.App('OpenCode','opencode','1','Manual'),{}),
              b.App('Protected','protected','1','pip',readonly_reason='Externally managed')]
        with patch.object(ui.Window,'refresh'):
            window=ui.Window()
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


if __name__=='__main__':
    unittest.main()
