"""Smoke test LaunchServices reopen/quit for an explicitly chosen installed app."""
from pathlib import Path
import json, os, re, subprocess, sys, tempfile, time
from urllib.request import Request, urlopen
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from manager.storage import create_library

app=Path(sys.argv[1]).resolve()
log=Path.home()/'Library/Logs/KiCad Library Manager/desktop.log'
with tempfile.TemporaryDirectory(prefix='manager-installed-check-') as temp:
    root=Path(temp)
    library=create_library(root/'Installed App Fixture')
    preferences=root/'preferences.json'
    preferences.write_text(json.dumps({'lastLibrary':str(library.root),'pcbOpacity':.55}))
    for iteration in range(2):
        offset=log.stat().st_size if log.exists() else 0
        process=subprocess.Popen(['open','-W','-a',str(app),'--env','KICAD_MANAGER_PREFERENCES='+str(preferences)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        try:
            for _ in range(150):
                text=log.read_text()[offset:] if log.exists() else ''
                found=re.findall(r'Library Manager: (http://127\.0\.0\.1:\d+/)#token=([^\s]+)',text)
                if found: break
                if process.poll() is not None: raise AssertionError(process.stderr.read().decode())
                time.sleep(.1)
            else: raise AssertionError('Installed app did not start')
            url,token=found[-1]
            def request(path, data=None):
                with urlopen(Request(url+'api/'+path,data=data,headers={'X-Library-Token':token,'Content-Type':'application/json'}),timeout=10) as response: return json.load(response)
            state=request('state')
            assert state['library']['id']==library.id
            assert state['version']=='0.3.0'
            assert request('preferences')['pcbOpacity']==.55
            subprocess.run(['open','-a',str(app)],check=True)
            # Read-only state round trip verifies the existing worker is still reachable.
            assert request('state')['library']['id']==library.id
            assert log.read_text()[offset:].count('Library Manager: ')==1,'Reopen started a duplicate worker'
            request('quit',b'{}')
            process.wait(timeout=10)
            assert process.returncode==0
            print('Installed launch/reopen/quit cycle',iteration+1,'passed')
            time.sleep(.8) # Let LaunchServices finish unregistering the terminated process.
        finally:
            if process.poll() is None:
                try: request('quit',b'{}')
                except Exception: pass
                process.wait(timeout=10)
            process.stdout.close();process.stderr.close()
