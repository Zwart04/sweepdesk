# SPDX-FileCopyrightText: 2026 Zwart04
# SPDX-License-Identifier: GPL-3.0-or-later
# SweepDesk: see LICENSE for copying terms and warranty disclaimer.
from pathlib import Path
import tempfile
import unittest
import preferences


class PreferenceTests(unittest.TestCase):
    def test_round_trip_and_private_permissions(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'sweepdesk/preferences.json'
            data=preferences.defaults()
            data.update(theme='light',density='comfortable',manual_folders=['/example/apps'])
            preferences.save(data,path)
            self.assertEqual(preferences.load(path),data)
            self.assertEqual(path.stat().st_mode&0o777,0o600)

    def test_corrupt_or_invalid_settings_use_valid_defaults(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'preferences.json'
            path.write_text('not json')
            self.assertEqual(preferences.load(path),preferences.defaults())
        data=preferences.validate({'theme':'bad','show_system':'yes','manual_folders':['relative',False,'/valid'],
                                   'enabled_sources':['APT','invented','npm']})
        self.assertEqual(data['theme'],'dark')
        self.assertFalse(data['show_system'])
        self.assertEqual(data['manual_folders'],['/valid'])
        self.assertEqual(data['enabled_sources'],['APT','npm'])

    def test_symlink_settings_file_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            original=Path(d)/'original'
            original.write_text('keep')
            link=Path(d)/'preferences.json'
            link.symlink_to(original)
            with self.assertRaises(OSError):
                preferences.save(preferences.defaults(),link)
            self.assertEqual(original.read_text(),'keep')
