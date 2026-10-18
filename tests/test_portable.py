import json
import os
import plistlib
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
import unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from manager.storage import create_library, SOURCE_ROOT


@unittest.skipUnless(
    (SOURCE_ROOT / "web/index.html").exists(), "Build the web interface first"
)
class SeparateApplicationTests(unittest.TestCase):
    def test_application_opens_data_only_library_from_unrelated_cwd(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            lib = create_library(base / "portable folder with spaces")
            unrelated = base / "elsewhere"
            unrelated.mkdir()
            command = [
                sys.executable,
                str(SOURCE_ROOT / "app.py"),
                "--library",
                str(lib.root),
                "--no-browser",
            ]
            proc = subprocess.Popen(
                command,
                cwd=unrelated,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            try:
                lines = []
                reader = threading.Thread(
                    target=lambda: lines.append(proc.stdout.readline()), daemon=True
                )
                reader.start()
                reader.join(10)
                self.assertTrue(lines, "Server did not become ready within 10 seconds")
                url = re.search(r"http://127\.0\.0\.1:\d+/", lines[0])[0]
                token = lines[0].split("#token=", 1)[1].strip()
                with self.assertRaises(HTTPError) as denied:
                    urlopen(url + "api/state", timeout=3)
                self.assertEqual(denied.exception.code, 403)
                denied.exception.close()
                req = Request(url + "api/state", headers={"X-Library-Token": token})
                with urlopen(req, timeout=3) as response:
                    state = json.load(response)
                self.assertEqual(state["library"]["id"], lib.id)
                self.assertEqual(Path(state["library"]["path"]), lib.root)
                req = Request(
                    url + "api/generic-preview?type=resistor&package=0805",
                    headers={"X-Library-Token": token},
                )
                with urlopen(req, timeout=3) as response:
                    preview = json.load(response)["info"]
                self.assertEqual({p["number"] for p in preview["pins"]}, {"1", "2"})
                self.assertIn("0805", preview["footprint"]["name"])
                self.assertTrue(
                    (
                        lib.root / "components/generic_models" / preview["genericModel"]
                    ).is_file()
                )
                self.assertTrue(
                    (
                        SOURCE_ROOT / "manager/_vendor/pypdf/__init__.py"
                    ).is_file()
                )
                req = Request(
                    url + "api/state",
                    headers={
                        "X-Library-Token": token,
                        "Origin": "https://unrelated.invalid",
                    },
                )
                with self.assertRaises(HTTPError) as denied:
                    urlopen(req, timeout=3)
                self.assertEqual(denied.exception.code, 403)
                denied.exception.close()
                with urlopen(url, timeout=3) as response:
                    self.assertIn(
                        b"<title>KiCad Library Manager</title>", response.read()
                    )
                with urlopen(url + "vendor/occt-import-js.wasm", timeout=3) as response:
                    self.assertTrue(response.read(4).startswith(b"\x00asm"))
                req = Request(
                    url + "api/quit",
                    data=b"{}",
                    headers={
                        "X-Library-Token": token,
                        "Content-Type": "application/json",
                    },
                )
                with urlopen(req, timeout=3) as response:
                    self.assertTrue(json.load(response)["ok"])
                proc.wait(timeout=5)
                self.assertEqual(proc.returncode, 0)
            finally:
                if proc.poll() is None:
                    proc.terminate()
                    proc.wait(timeout=5)
                proc.stdout.close()
                proc.stderr.close()

    def test_libraries_do_not_contain_application_copies(self):
        with tempfile.TemporaryDirectory() as directory:
            lib = create_library(Path(directory) / "Library")
            self.assertEqual({p.name for p in lib.root.iterdir()}, {"components", "appdata"})
            self.assertFalse((lib.appdata / "runtime").exists())
            from manager.storage import install_portable_runtime
            install_portable_runtime(lib.root)
            self.assertFalse((lib.appdata / "runtime").exists())
            self.assertIn("Spotlight", (lib.appdata / "Start here.txt").read_text())
