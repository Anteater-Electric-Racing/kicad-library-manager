# Architecture

The Mac application is a native AppKit window hosting a bundled React/TypeScript frontend in WKWebView. The window owns one standard-library Python loopback worker; no browser or persistent background service is required. Three.js provides interactive geometry and transforms; an OpenCascade WebAssembly worker parses STEP locally. KiCad CLI supplies native SVG previews and export verification. Python 3.11+ is the runtime prerequisite; Node is development-only.

## Modules

- `storage`: explicit roots, format version 2, canonical CSV, derived SQLite/KiCad configuration, component-folder reconciliation, locking, backup/journal transactions and data-only library creation.
- `importer`: temporary upload sessions, safe archive expansion, immutable review proposals, duplicate replacement, parent/accessory atomic saves, folder moves and recipe validation.
- `cad` / `sexpr`: structural KiCad parsing, symbol inheritance, explicit pin-number evidence, connector layouts and model transform serialization.
- `supplier` / `passives`: supplier metadata extraction, exact-part manufacturer document fallback, provenance, passive values, ratings and unit-aware package selection.
- `bom`: KiCad XML instances, DNP/exclusions, fixed recipe expansion, explicit accessory ownership, purchasing aggregation and release snapshots.
- `kicad` / `odbc`: CLI detection/rendering, explicit backed-up registration and native queries against the generated connection.
- `migration`: copy-only legacy conversion, source hashing, active-row preservation, model-path relocation, original/source archives and conversion reports.
- `server`: process-scoped import sessions and token-protected UI endpoints. It does not discover installed libraries.

## Folder and catalog contracts

The portable root contains `components/` and `appdata/`. `appdata/library.json` holds `formatVersion: 2` and the stable library UUID. Original downloads, backups and generated indexes remain under `appdata`. Runtime and bundled resources live inside the installed Mac app.

`appdata/components.csv` owns product metadata and relative CAD locations. IDs remain stable after assignment. Manufacturer/MPN combinations distinguish purchasable choices; category paths are organization, not identity. Imported legacy IDs are preserved. The old `Status` column is retained blank for the current schema; the UI does not expose a “needs review” state. Import validation and explicit pin checks remain.

Bespoke assets live in a terminal component folder under `components`. Its `component.json` has PartID and LibraryID only; it does not duplicate product metadata. Generic passives and CAD-free accessory records have empty `AssetFolder` values and do not create per-part directories. Resistors and capacitors are two spreadsheet-style UI views of the same CSV, with shared assets under `components/generic_models`. The default package is imperial 0805. Custom passive models can still use a bespoke folder.

A connector's `recipes.json` stays beside its CAD and contains version 1 plus `items: [{partID, quantity, role}]`. Folderless records can own recipes under `appdata/recipes/<ID digest>.json`. Quantities are positive integers. Missing references, self-reference, duplicates and cycles fail validation. The representation leaves room for future alternative recipes and per-instance quantity rules.

## Import transaction

Accessories are inline rows at the bottom of component details, each requesting manufacturer, MPN and quantity. Matching catalog records can be reused. Newly entered accessories remain staged with their parent; cancelling the import does not create orphan accessory entries. The final transaction includes the parent, new accessory rows, the local recipe and derived indexes.

Save first prepares an internal token tied to the selected library, catalog/recipe revision and file fingerprints, then commits it. The UI has no review page. A fresh duplicate import requires an explicit replacement choice; an explicit edit saves directly. Live previews use scratch files and never prepare a catalog transaction. Catalog, working assets, recipes, download archives and generated files are backed up and installed as one journaled operation. Failure restores exact previous bytes; a remaining journal enables explicit recovery. A local lock and optimistic fingerprints are not distributed cloud locking, so synced libraries require one editor.

IC imports do not show the URL importer. They use uploaded model metadata and manually entered fields. Supported non-IC URL imports first try the supplier page. If it is blocked, a supported exact-part YAGEO Group PDF lookup may supply specifications. The response records provenance and warns when price/stock were not retrieved. This is not a universal DigiKey/Mouser blocking bypass. Unsupported fallbacks can return URL identity only and require copied details or manual specifications; missing ratings are never guessed from a family name.

## Manual folder moves

Opening a library or requesting its state through Refresh scans `components` for `component.json` markers. An intact folder can move or change its terminal name without losing its PartID. Reconciliation updates `AssetFolder`, category, contained CAD paths, relocated model URIs and derived indexes in a backed-up transaction. It preserves source CAD nicknames and model transformations.

The complete component folder and marker must move together. Individual CAD renames, shared generic-file moves, duplicate copies, missing markers/assets, foreign library IDs and uncatalogued markers are not guessed through; issues are shown and block writes. A concurrent writer or unresolved journal also prevents reconciliation. This is an on-open/Refresh reconciliation step, not a filesystem watcher.

## KiCad identity and search

The database registration retains the root folder's nickname and globally unique catalog keys. Chooser categories use `Virtus - <folder category>` labels: ICs becomes `Virtus - IC`, connectors becomes `Virtus - Connectors`, and connectors/deutsch becomes `Virtus - Deutsch Connectors`. Deeper folders remain in the label. Category-name collisions receive a deterministic suffix without renaming previously allocated categories. The complete `SearchPath` contains root name, parent category folders and MPN, excluding the terminal asset folder's name. Folder changes update this field without changing PartID.

Source CAD nicknames derive from stable identity and remain enabled but hidden for compatibility. `category_libraries` emits derived `.pretty` projections under `appdata/generated/categories`, including logos. The database uses a derived `KiCadFootprint` column to select the friendly category footprint; authoritative CSV links and working CAD stay unchanged. `appdata/category-libraries.json` reserves allocated chooser names and remembers historical category aliases, with no editable product metadata. Whole-folder moves regenerate projections and preserve model paths/transforms. Historical footprint aliases remain available for placed boards; an entirely historical category is hidden. If that category still has active parts, its compatibility aliases remain visible alongside them because KiCad visibility is per library. Deleting the last catalog reference removes its generated projections during the same backed-up transaction. Generated libraries must not be edited directly.

Root renaming changes the database nickname. Explicit reconnect regenerates it; existing designs require deliberate link updates. `MYCO_PARTS_DIR` points to the selected v2 library's `appdata`. The ODBC string stays `DSN=VirtusSQLite;Database=${CWD}/parts.sqlite;`. One selected connection is active per machine; the app does not silently retarget it when opening a different library.

## Rendering conventions

Footprint XY positions become `(x, -y, 0)` in 3D, with reference board top at Z=0. STEP vertices retain their origin and use millimeters. The model transform is `T(offset) × Rz(-z) × Ry(-y) × Rx(-x) × S(scale)`, matching KiCad 10.0.1's renderer. Legacy model `(at (xyz ...))` values are inches and are converted to millimeter offsets for preview/editing. Alignment never centers source geometry or moves footprint pads.

Manual controls provide XYZ moves in 0.5 mm increments and rotation snaps to 90° boundaries, alongside numeric fields, drag handles, standard views and reset. Scale defaults to one and changes explicitly. Automatic alignment remains deferred.

The interactive pad map is a simplified inspection overlay; native KiCad SVG is available for full geometry. Pin checks compare identifiers and metadata, never physical connectivity inferred from shape. A valid parse and equal pin counts do not establish manufacturer correctness.

## Legacy conversion and boundaries

Legacy source authority remains its `parts-library-appdata/components.csv`. The explicit converter publishes a separate v2 sibling only after source hashes match. It preserves active rows/IDs, original downloads, licenses, model transform nodes and pad data; unknown old metadata is retained in a source-row report and meaningful Notes. A full source ZIP preserves historical backups and unused variants without recreating retired passive catalog seeds or working passive PDFs.

The authorized Virtus copy preserved 45 IDs and all 453 source files. Ninety native symbol/footprint render jobs passed, and the exact generated ODBC configuration returned all 45 records. Two existing absent external JST 15-pin WRL models remain reported. Neither the source nor machine registrations were changed. These checks do not prove live chooser placement or Windows behavior; see `VERIFICATION.md` and `MIGRATION.md`.

There is no background supplier sync, purchasing workflow, automatic STEP alignment, populated-contact counting, alternative mating recipe selection or per-instance recipe engine. These remain future features.

Accessories have no standalone creation or catalog view. Their internal catalog IDs are retained for recipe references, historical BOM snapshots and explicit schematic ownership. The BOM exporter continues to read the authoritative catalog and recipes directly, independently of the UI filter.


## Mac desktop lifecycle (0.3)

`manager/macos/desktop.m` owns the window and WKWebView, native menus/dialogs, clipboard bridge, fullscreen transitions and child process. `scripts/build_mac_app.py` packages the runtime into a regular `.app` with a stable LaunchServices identity; it is installed once in Applications and found through Spotlight. No launch agent or login item is installed. Python 3.11+ remains an external prerequisite; bundling Python/signing/notarization for general distribution is separate future work.

The frontend publishes open-editor and active-operation guards via a narrow, main-frame, same-origin WKScriptMessageHandler. Window close and Command-Q consult the current guard, offer Keep Editing / Discard and Close, then request authenticated shutdown. The server waits for its writer lock, rejects subsequent writes and closes sessions before exiting. A parent-PID watchdog takes the same shutdown path if the native host disappears. Native shutdown completes only after the worker has exited. Fullscreen alignment uses the native window with a fixed viewer overlay; Escape exits, including if pressed during the entry animation.

Machine-local preferences hold `pcbOpacity` and the explicitly selected `lastLibrary`. Missing/moved/unreadable remembered folders show a chooser without creating files or scanning for replacements. Updates preserve both preferences. Native navigation stays on the worker origin; clicked external HTTP(S)/mail links open the default browser without exposing the native bridge.

The original v2 catalog header without optional connector ratings is accepted read-only and normalized in memory. Unknown schemas are rejected. Saving through the existing transaction writes the current schema with a catalog backup. BOM command generation points to the installed runtime, not a runtime inside a library. Existing manually configured legacy BOM commands need to be replaced from the app's BOM export page.
