"""Private, bundled dependencies that require no machine installation."""

from pathlib import Path
import sys

# pypdf uses absolute imports internally. Keep its upstream source unchanged.
_directory = str(Path(__file__).parent)
if _directory not in sys.path:
    sys.path.insert(0, _directory)
