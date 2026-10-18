from pathlib import Path
import subprocess, tempfile
root=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as directory:
    base=Path(directory)
    png=base/'icon.png'
    subprocess.run(['swift',str(root/'scripts/build_mac_icon.swift'),str(png)],check=True)
    icons=base/'Manager.iconset';icons.mkdir()
    for size in [16,32,128,256,512]:
        for scale in [1,2]:
            name=f'icon_{size}x{size}'+('@2x' if scale==2 else '')+'.png'
            subprocess.run(['sips','-z',str(size*scale),str(size*scale),str(png),'--out',str(icons/name)],check=True,stdout=subprocess.DEVNULL)
    subprocess.run(['iconutil','-c','icns',str(icons),'-o',str(root/'resources/Manager.icns')],check=True)
