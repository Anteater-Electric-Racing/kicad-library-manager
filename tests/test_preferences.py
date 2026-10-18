import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from manager import preferences


class DisplayPreferencesTests(unittest.TestCase):
    def test_persistence_and_invalid_values(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'settings/preferences.json'
            with patch.dict(os.environ, {'KICAD_MANAGER_PREFERENCES': str(path)}):
                self.assertEqual(preferences.read(), {'pcbOpacity': .35})
                for value in [0, .65, 1]:
                    preferences.save({'pcbOpacity': value})
                    self.assertEqual(preferences.read(), {'pcbOpacity': value})
                original = path.read_bytes()
                for value in [-1, 2, None, '0.5', True, float('nan')]:
                    with self.assertRaises(ValueError):
                        preferences.save({'pcbOpacity': value})
                    self.assertEqual(path.read_bytes(), original)
                for malformed in ['{', '[]', '{"pcbOpacity": 7}']:
                    path.write_text(malformed)
                    self.assertEqual(preferences.read(), {'pcbOpacity': .35})
