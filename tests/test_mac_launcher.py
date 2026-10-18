"""Packaging regression for the standalone Mac app (legacy per-library launchers retired)."""
from pathlib import Path
import plistlib
import sys
import tempfile
import unittest

from manager.storage import SOURCE_ROOT
sys.path.insert(0, str(SOURCE_ROOT/'scripts'))
from build_mac_app import build_app


@unittest.skipUnless(sys.platform == 'darwin', 'Mac-only app')
class MacDesktopBundleTests(unittest.TestCase):
    def test_bundle_is_regular_app_with_its_own_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            app=build_app(Path(directory)/'Manager.app')
            info=plistlib.loads((app/'Contents/Info.plist').read_bytes())
            self.assertEqual(info['CFBundleIdentifier'],'local.kicad-library-manager.desktop')
            self.assertFalse(info.get('LSUIElement',False))
            runtime=app/'Contents/Resources/runtime'
            self.assertTrue((runtime/'app.py').is_file())
            self.assertTrue((runtime/'web/index.html').is_file())
            self.assertTrue((runtime/'resources/generic_models/inventory.json').is_file())
            self.assertFalse((runtime/'appdata').exists())
            executable=app/'Contents/MacOS'/info['CFBundleExecutable']
            self.assertEqual(executable.read_bytes()[:4],bytes.fromhex('cafebabe'))
