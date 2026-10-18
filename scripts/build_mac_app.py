"""Build the standalone Mac app; never put application code in library folders."""
from pathlib import Path
import argparse
import plistlib
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from manager import VERSION


def build_app(destination, source=ROOT, identifier="local.kicad-library-manager.desktop"):
    destination = Path(destination)
    if destination.exists():
        raise ValueError("Build into a new destination; replace installed apps only after closing them")
    contents = destination / "Contents"
    executable = contents / "MacOS/KiCad Library Manager"
    executable.parent.mkdir(parents=True)
    shutil.copy2(ROOT / "manager/macos/desktop", executable)
    runtime = contents / "Resources/runtime"
    for name in ("manager", "web", "resources"):
        shutil.copytree(source / name, runtime / name,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.m", "launcher", "desktop"))
    shutil.copy2(source / "app.py", runtime / "app.py")
    icon = ROOT / "resources/Manager.icns"
    if icon.exists():
        shutil.copy2(icon, contents / "Resources/Manager.icns")
    (contents / "Info.plist").write_bytes(plistlib.dumps(dict(
        CFBundleExecutable=executable.name,
        CFBundleIdentifier=identifier,
        CFBundleName="KiCad Library Manager",
        CFBundleDisplayName="KiCad Library Manager",
        CFBundlePackageType="APPL",
        CFBundleShortVersionString=VERSION,
        CFBundleVersion="4",
        CFBundleIconFile="Manager",
        LSMinimumSystemVersion="12.3",
        NSHighResolutionCapable=True,
        NSPrincipalClass="NSApplication",
        NSAppTransportSecurity={"NSAllowsLocalNetworking": True},
        NSHumanReadableCopyright="KiCad Library Manager. Bundled model licenses are included with the application.",
    )))
    subprocess.run(["codesign", "--force", "--sign", "-", str(destination)], check=True, capture_output=True)
    return destination


def compile_host():
    subprocess.run([
        "clang", "-fobjc-arc", "-framework", "Cocoa", "-framework", "WebKit",
        "-mmacosx-version-min=12.3", "-arch", "arm64", "-arch", "x86_64",
        str(ROOT / "manager/macos/desktop.m"), "-o", str(ROOT / "manager/macos/desktop"),
    ], check=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    compile_host()
    print(build_app(args.output))
