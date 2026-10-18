"""Machine-local preferences, independent of library data and server port."""
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import threading

_lock = threading.RLock()


def preference_path():
    override = os.environ.get("KICAD_MANAGER_PREFERENCES")
    if override:
        return Path(override)
    if sys.platform == "darwin":
        base = Path.home() / "Library/Application Support"
    elif sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData/Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "KiCad Library Manager/preferences.json"


def valid_opacity(value):
    return type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1


def read():
    with _lock:
        result = {"pcbOpacity": 0.35}
        try:
            data = json.loads(preference_path().read_text())
            if valid_opacity(data.get("pcbOpacity")):
                result["pcbOpacity"] = data["pcbOpacity"]
            if isinstance(data.get("lastLibrary"), str):
                result["lastLibrary"] = data["lastLibrary"]
        except (OSError, ValueError, AttributeError):
            pass
        return result


def _update(changes):
    with _lock:
        data = {**read(), **changes}
        path = preference_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as file:
                temporary = Path(file.name)
                json.dump(data, file)
            temporary.replace(path)
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)
        return data


def save(data):
    value = data.get("pcbOpacity")
    if not valid_opacity(value):
        raise ValueError("PCB opacity must be between zero and one")
    return _update({"pcbOpacity": value})


def remember_library(path):
    return _update({"lastLibrary": str(Path(path).resolve())})
