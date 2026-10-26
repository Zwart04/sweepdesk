# SPDX-FileCopyrightText: 2026 Zwart04
# SPDX-License-Identifier: GPL-3.0-or-later
# SweepDesk: see LICENSE for copying terms and warranty disclaimer.
import string
import unittest
from unittest.mock import patch
import i18n
import preferences


class TranslationTests(unittest.TestCase):
    def tearDown(self):
        i18n.configure('en')

    def test_catalogue_preserves_all_format_fields(self):
        formatter=string.Formatter()
        for source,translation in i18n.ID.items():
            with self.subTest(source=source):
                fields=lambda text:{field for _,field,_,_ in formatter.parse(text) if field is not None}
                self.assertEqual(fields(source),fields(translation))

    def test_language_detection_and_settings_validation(self):
        with patch.dict('os.environ',{'LANGUAGE':'id_ID:en','LC_ALL':'en_US.UTF-8'}):
            self.assertEqual(i18n.configure('system'),'id')
        self.assertEqual(i18n.tr('Settings'),'Pengaturan')
        self.assertEqual(i18n.tr('{name} was removed successfully.',name='Firefox ESR'),'Firefox ESR berhasil dihapus.')
        self.assertEqual(i18n.tr('/usr/bin/firefox'),'/usr/bin/firefox')
        self.assertEqual(preferences.validate({'language':'unknown'})['language'],'system')
        self.assertEqual(preferences.validate({'language':'id'})['language'],'id')
