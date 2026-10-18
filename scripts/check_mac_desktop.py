"""Real native host/renderer checks; all writable library and settings paths are temporary."""
from pathlib import Path
import json, os, subprocess, sys, tempfile, hashlib
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from manager.storage import create_library
from build_mac_app import build_app, compile_host, ROOT

compile_host()
with tempfile.TemporaryDirectory(prefix='manager-desktop-test-') as temp:
    base=Path(temp)
    lib=create_library(base/'Desktop Fixture')
    preferences=base/'preferences.json'
    preferences.write_text(json.dumps({'pcbOpacity':.4,'lastLibrary':str(lib.root)}))
    app=build_app(base/'Desktop Test.app',identifier='local.kicad-library-manager.integration')
    executable=app/'Contents/MacOS/KiCad Library Manager'
    subprocess.run(['clang','-fobjc-arc','-framework','Cocoa','-framework','WebKit','-mmacosx-version-min=12.3',str(ROOT/'tests/desktop_harness.m'),'-o',str(executable)],check=True)
    subprocess.run(['codesign','--force','--sign','-',str(app)],check=True,capture_output=True)
    before={str(p.relative_to(lib.root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in lib.root.rglob('*') if p.is_file()}
    with (base/'host.log').open('w') as log:
        process=subprocess.Popen([str(executable)],env={**os.environ,'KICAD_MANAGER_PREFERENCES':str(preferences),'MANAGER_TEST_RESULT':str(base/'result.json')},stdout=log,stderr=log)
        try: process.wait(timeout=85)
        except subprocess.TimeoutExpired:
            process.kill();process.wait()
            raise AssertionError((base/'host.log').read_text())
    if not (base/'result.json').exists(): raise AssertionError((base/'host.log').read_text())
    result=json.loads((base/'result.json').read_text())
    print(json.dumps(result,indent=2))
    if not result['passed']: raise AssertionError((base/'host.log').read_text())
    after={str(p.relative_to(lib.root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in lib.root.rglob('*') if p.is_file()}
    assert before==after,'Native preview/close changed library files'
    try: os.kill(result['workerPID'],0)
    except ProcessLookupError: pass
    else: raise AssertionError('Worker survived closing its native window')
    print('Native desktop checks passed; worker exited and library files are unchanged.')
