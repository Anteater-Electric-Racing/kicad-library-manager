"""Build one Mac app release. Library folders contain data, not application copies."""
from pathlib import Path
import shutil
import subprocess
import sys
from build_mac_app import build_app, compile_host, ROOT
sys.path.insert(0, str(ROOT))
from manager import VERSION

if not (ROOT / 'web/index.html').exists():
    raise SystemExit('Run npm run build first')
compile_host()
out = ROOT / 'dist/KiCad Library Manager.app'
if out.exists():
    shutil.rmtree(out)
build_app(out)
archive = ROOT / f'dist/KiCad-Library-Manager-{VERSION}-mac.zip'
subprocess.run(['ditto', '-c', '-k', '--sequesterRsrc', '--keepParent', str(out), str(archive)], check=True)
print(archive)
