"""Standalone worker lifetime and saved-library behavior, using temporary fixtures."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from urllib.request import Request, urlopen
from unittest.mock import patch

from manager import preferences
from manager.storage import create_library, SOURCE_ROOT


class DesktopLifecycleTests(unittest.TestCase):
    def test_display_updates_preserve_remembered_library(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {'KICAD_MANAGER_PREFERENCES': str(Path(directory)/'prefs.json')}):
                preferences.remember_library(directory)
                preferences.save({'pcbOpacity': .75})
                self.assertEqual(preferences.read()['lastLibrary'], str(Path(directory).resolve()))
                preferences.remember_library(str(Path(directory)/'moved'))
                self.assertEqual(preferences.read()['pcbOpacity'], .75)

    def test_desktop_reopens_remembered_library_and_missing_path_is_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory)
            library=create_library(base/'fixture')
            prefs=base/'preferences.json'
            for remembered, expected in [(str(library.root),library.id),(str(base/'missing'),None)]:
                prefs.write_text(json.dumps({'lastLibrary':remembered,'pcbOpacity':.2}))
                process=subprocess.Popen([sys.executable,'-B','-u',str(SOURCE_ROOT/'app.py'),'--desktop','--no-browser'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env={**os.environ,'KICAD_MANAGER_PREFERENCES':str(prefs)})
                try:
                    line=process.stdout.readline().strip().split('Library Manager: ')[1]
                    url,token=line.split('#token=')
                    with urlopen(Request(url+'api/state',headers={'X-Library-Token':token}),timeout=5) as response:
                        state=json.load(response)
                    self.assertEqual(state['library']['id'] if state['library'] else None,expected)
                    if not expected: self.assertIn('previous library',state['startupWarning'])
                    with urlopen(Request(url+'api/quit',data=b'{}',headers={'X-Library-Token':token}),timeout=5) as response:
                        response.read()
                    process.wait(timeout=5)
                    self.assertEqual(process.returncode,0)
                    self.assertFalse((base/'missing').exists())
                finally:
                    if process.poll() is None: process.kill();process.wait()
                    process.stdout.close();process.stderr.close()

    def test_parent_death_stops_worker(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory)
            # A short-lived parent starts the real worker, then exits as a crashed host would.
            parent = '''
import os,subprocess,sys,time
from pathlib import Path
log=Path(sys.argv[1])
with log.open('w') as stream:
 p=subprocess.Popen([sys.executable,'-B','-u',sys.argv[2],'--desktop','--no-browser','--parent-pid',str(os.getpid())],stdout=stream,stderr=stream)
for _ in range(100):
 if 'Library Manager:' in log.read_text(): break
 time.sleep(.05)
else: p.kill(); raise SystemExit('Worker not ready')
print(p.pid)
'''
            proc=subprocess.run([sys.executable,'-c',parent,str(base/'worker.log'),str(SOURCE_ROOT/'app.py')],capture_output=True,text=True,timeout=10,env={**os.environ,'KICAD_MANAGER_PREFERENCES':str(base/'preferences.json')})
            self.assertEqual(proc.returncode,0,proc.stderr)
            url=(base/'worker.log').read_text().split('Library Manager: ')[1].split('#')[0]
            port=int(url.split(':')[2].strip('/'))
            for _ in range(60):
                with socket.socket() as sock:
                    if sock.connect_ex(('127.0.0.1',port)) != 0: break
                time.sleep(.1)
            else:
                os.kill(int(proc.stdout),9)
                self.fail('Worker remained listening after parent exited')

    def test_shutdown_waits_for_active_write(self):
        with tempfile.TemporaryDirectory() as directory:
            prefs=Path(directory)/'prefs.json'
            entry='''
import time
from manager import preferences
from manager.server import run
save=preferences.save
def delayed(data):
 print('WRITE STARTED',flush=True)
 time.sleep(.8)
 return save(data)
preferences.save=delayed
run(open_browser=False,desktop=True)
'''
            process=subprocess.Popen([sys.executable,'-B','-u','-c',entry],cwd=SOURCE_ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env={**os.environ,'KICAD_MANAGER_PREFERENCES':str(prefs)})
            try:
                url,token=process.stdout.readline().strip().split('Library Manager: ')[1].split('#token=')
                errors=[]
                def write():
                    try:
                        with urlopen(Request(url+'api/preferences',data=b'{"pcbOpacity":0.8}',headers={'X-Library-Token':token}),timeout=5) as response: response.read()
                    except Exception as exc: errors.append(exc)
                writer=threading.Thread(target=write);writer.start()
                self.assertEqual(process.stdout.readline().strip(),'WRITE STARTED')
                with urlopen(Request(url+'api/quit',data=b'{}',headers={'X-Library-Token':token}),timeout=5) as response: response.read()
                writer.join(5)
                process.wait(timeout=5)
                self.assertFalse(errors)
                self.assertEqual(json.loads(prefs.read_text())['pcbOpacity'],.8)
                self.assertEqual(process.returncode,0)
            finally:
                if process.poll() is None: process.kill();process.wait()
                process.stdout.close();process.stderr.close()
