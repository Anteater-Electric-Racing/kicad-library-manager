# Mac desktop setup (0.3)

Install **KiCad Library Manager.app** in Applications and launch it with Spotlight. Use macOS 12.3+, Python 3.11+ and KiCad 10. Choose the data-only library folder in the app; the last selected folder is remembered. Closing the window stops the worker after checking for unsaved edits and active operations.

The desktop app replaces per-library `Open Library.app`, `Open Library.bat` and `appdata/runtime` copies. Do not recreate them. Existing KiCad registrations and `${MYCO_PARTS_DIR}` references still point to the library's `appdata`; updating the application does not change them.

For maintainers, run `npm run build`, `python3 scripts/build_mac_icon.py` when changing the icon, then `python3 scripts/package.py`. `python3 scripts/check_mac_desktop.py` exercises the actual native host and WebKit renderer with a temporary library. The app is locally ad-hoc signed; distribution to other Macs is not yet notarized. Python is not bundled. Windows desktop packaging is deferred.

The remaining sections below describe KiCad/ODBC configuration and historical platform setup. Browser/portable-launcher instructions are superseded by the desktop workflow above.

# First-machine setup

## Python and launchers

Install [Python 3.11 or newer](https://www.python.org/downloads/) and KiCad 10. The Mac launcher searches `/opt/homebrew/bin`, `/usr/local/bin`, then `/usr/bin`; the Windows launcher uses `py -3`.

In a portable library, double-click **Open Library.app** or **Open Library.bat**. Keep those launchers beside `components` and `appdata`. They open their containing library folder, including after relocation. Normal use needs no Node or npm installation.

For console diagnostics from the library root:

```sh
# macOS
python3 appdata/runtime/app.py --library .
# Windows
py -3 appdata\runtime\app.py --library .
```

The Finder launcher is a bundled native macOS application (Apple Silicon and Intel). Reopening it brings back the same browser session instead of starting another service. Quit in the browser stops the service and launcher. Runtime failures display a message with the log location.

The Finder launcher writes logs to `~/Library/Logs/KiCad Library Manager/launcher.log`. The app opens your default browser. Its service listens only on `127.0.0.1`, uses a random per-run token and rejects cross-origin API requests. Native Windows startup remains a separate hands-on acceptance check.

## SQLite ODBC on macOS

The Homebrew formula `sqliteodbc` provides a SQLite3 ODBC driver. Install the driver for the same architecture as KiCad. Its driver configuration must register it as `SQLite3`; the library path depends on your Homebrew prefix and architecture.

Add a **user** DSN in `~/.odbc.ini` without replacing other entries:

```ini
[VirtusSQLite]
Driver=SQLite3
Description=KiCad component library
```

If `VirtusSQLite` already exists, inspect it rather than overwriting it. The library's `.kicad_dbl` supplies the database filename; do not hard-code a development or old library path into the DSN.

## SQLite ODBC on Windows

Install a **64-bit SQLite ODBC driver** appropriate for KiCad. In **ODBC Data Sources (64-bit)** → **User DSN** → **Add**, choose that driver and name the DSN **VirtusSQLite**. Preserve unrelated data sources. Platform setup instructions alone are not evidence that this project's native Windows workflow has been tested.

## Verify and connect

Click **Check database connection** in the manager. It reads `appdata/parts.kicad_dbl`, substitutes `${CWD}` exactly as KiCad does and queries the native driver manager. A direct Python SQLite query is not equivalent.

The connection string remains:

```text
DSN=VirtusSQLite;Database=${CWD}/parts.sqlite;
```

`MYCO_PARTS_DIR` identifies the selected v2 library's **appdata** folder. It is used for symbol, footprint and model paths, not substituted into the ODBC string. `${CWD}` resolves to the folder containing the database configuration. Paths containing semicolons are rejected because the tested SQLite ODBC connection does not support them reliably.

Close KiCad, then click **Connect to KiCad**. The app backs up configuration changes and preserves unrelated registrations. Conflicting names stop the operation. Reopen KiCad afterward. Native chooser search, placement and existing-instance update behavior still need hands-on acceptance.

## Moving or switching libraries

After moving the complete library, launch it from its new location and explicitly reconnect it on that computer. Renaming its root changes the KiCad nickname; old designs require deliberate library-link updates. Opening another library does not silently change the selected machine connection.

Within `components`, you may move an intact bespoke component folder with its `component.json` marker, CAD and recipe. Open or **Refresh** the manager to update its paths and indexes. Do not rename individual CAD files or move shared generic assets. Missing or duplicate folders are reported and block writes. Wait for cloud sync and use one editor at a time.

## Existing libraries

Open an existing format-v2 library explicitly. Old importer libraries require an explicit copy conversion; see [migration](MIGRATION.md). Library data is distributed separately from this application repository. Connecting a library on each machine is a separate action from opening or copying it.

Maintainers: after changing `manager/macos/desktop.m`, rebuild the app using `python3 scripts/package.py`. End users do not need compiler tools.
