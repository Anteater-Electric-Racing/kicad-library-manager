# Verification record — v0.2 / format v2

Development tests use disposable fixtures and isolated KiCad configuration. The user explicitly authorized conversion of the selected Virtus library; it was copied to a separate sibling. The source library, retired importer and actual machine registrations remain unchanged.

## Verified on this Mac

- Python regression suite: 67 tests pass with ResourceWarnings treated as errors. Coverage includes shared passive assets, inline accessories staged atomically, manual folder reconciliation and duplicate detection, catalog-only recipe revisions, originals and ID preservation, interrupted-write recovery, pin/shield checks, model preservation during edits, BOM quantities/DNP and copied portable runtime startup.
- The copied runtime starts from an unrelated working directory, loads its own library, serves bundled frontend/STEP WebAssembly, supplies default 0805 preview geometry, rejects missing tokens and cross-origin API calls, and exits through Quit. Root contents are exactly `components`, `appdata`, `Open Library.app` and `Open Library.bat`. The original shell-launcher check was superseded by the native LaunchServices regression below.
- Production TypeScript/Vite build passes. STEP parsing and manufacturer PDF parsing dependencies are bundled locally with licenses.
- Browser: a new passive opens with 0805 models already available. The user's DigiKey sample URL filled YAGEO / RC0805FR-07243KL / 243 kΩ / 1% / 0805 / 0.125 W, displayed its exact manufacturer source, and saved as a catalog row without a per-part folder. Resistor and capacitor table views expose the specifications.
- Browser: the IC form contains no URL importer or review-status controls. The wizard has no Accessories page; inline manufacturer/MPN/quantity rows appear at the bottom of details.
- Browser: a synthetic connector ZIP with an inline housing saved both records together. 3D buttons moved X from 1 to 1.5 mm and snapped Z from 30° to 90°. Saved footprint values match. A manual complete-folder move followed by Refresh updated the displayed category, model paths and database indexes while keeping the recipe and part ID.
- BOM export after that move produced two headers, two housings and one resistor for the synthetic design, without status warnings.
- Native model transform comparison against KiCad 10.0.1 STEP export still matches within `4e-13` mm. Model transforms retain KiCad's negative Z–Y–X rotation convention.
- Live supplier checks: the sample plus YAGEO RC0603FR-0710KL and KEMET C0805C104K5RACTU returned exact-part manufacturer specifications. Direct DigiKey fetch returns HTTP403 here; the fallback is explicitly attributed and does not invent price or stock. Other manufacturers can still require copied details/manual input.
- Virtus conversion: all 45 active catalog IDs preserved; all 453 source files hash-identical. Three passives share legacy CAD with no per-part directories; 42 bespoke component folders and eight logo files are retained. All 90 native KiCad symbol/footprint render jobs passed; the exact generated ODBC library returns all 45 records across seven categories. Detailed results are in the converted library's `appdata/migration/verification.json`.

- All 45 converted records also pass read-only edit preparation with their existing KiCad item names and file paths preserved. Existing source pin mismatches, blank manufacturers and one non-URL datasheet reference remain explicit warnings; newly introduced invalid values are rejected. No catalog/CAD edits were committed by this check.

## Known limits

- Native Windows startup, dialogs, driver setup and browser graphics need a Windows run. Cross-platform source and CI definitions are not native Windows verification.
- KiCad's live chooser search and placement still need a native UI check. SearchPath/category values, generated indexes and ODBC queries are verified.
- Manual organization supports whole component folders with their marker and contents. Renaming individual CAD files, moving shared models, or moving components/appdata independently is unsupported. Duplicate/missing folders are reported instead of guessed.
- The two historically absent WRL references for BM15B-GHS-TBT and SM15B-GHS-TB remain recorded in the migration report. Their schematic/footprint data converted successfully; no geometry was invented.
- The converted sibling has not replaced the original machine registration or relinked existing designs. Connect it explicitly in the app when ready.


## 2026-09-26 editor regression verification

- Supplied `LIB_01000062Z.zip`: direct supplier pins 1–4 match the footprint, leaf identity is inferred, a temporary save succeeds, and KiCad exports both saved assets. Original input is archived byte-for-byte. No ratings were inferred from geometry or the test's synthetic values.
- Native KiCad symbol upgrade and export retain both connector body styles with identical pin identities, names and electrical types. Metadata editing preserves both styles. Live placement/body-style UI switching remains a separate manual acceptance check.
- Browser on a temporary library: inferred LITTELFUSE / 01000062Z, single form with live original/generated previews, connector amps/volts, inline accessory, double-Enter save, one visible component with the accessory hidden, clipboard button populated a text box, and bottom 3D view. A local test harness sent a File-bearing drop event onto the catalog and opened/populated Add component. Native OS file/folder dragging remains unautomated.
- Geometry raycasts pass through round, slotted/rotated/offset and nonplated drills from top and bottom, while hitting retained copper/board and full-depth barrel walls. Directory-drop tests cover nested paths, batched readers, early data-store capture and file fallback.
- Export from the browser-saved temporary component produced two components and four accessories across all five BOM artifacts. Parent/accessory cancellation, rollback, reuse, BOM quantity updates, DNP, explicit-accessory deduplication and existing catalog-only recipe revisions pass. The BOM implementation and internal stable-ID contract are retained.
- Current production build and source distribution are rebuilt. The actual installed libraries, their copied runtimes, original downloads and machine KiCad registrations were not changed by this development work.

## 2026-09-28 Finder launcher repair

- The shell executable replaced itself with the Python HTTP service and provided no AppKit reopen handler. A running service was confirmed during the reported Finder “not open anymore” error; the exact historical Finder event was not captured.
- A universal AppKit launcher now owns the child service, handles reopen events by reopening its existing URL, exits after browser Quit, and displays startup/service errors. Bundle identities are distinct per generated app and retained during refresh. Root resolution remains relative to the clicked bundle. No compiler is required on users' machines.
- Native LaunchServices test opens a synthetic library from an unrelated directory, opens it three more times, verifies a reopen event and exactly one child, then quits and relaunches successfully. Portable-copy and full suite: 68 tests pass with ResourceWarnings treated as errors. Apple Silicon was exercised; the Intel slice is built but not run on Intel hardware.
- Applied only launcher files and launcher-generation support to the active Virtus PCB components Lib runtime, with a ZIP backup under its appdata/backups. Verified the real service, repeated open, and byte-identical catalog, CAD, downloads and other protected library files. No KiCad registrations changed; the old PCB library was not modified.

## Mac desktop 0.3 — 2026-09-28

74 Python tests passed after the desktop changes, including preference merging, remembered/missing library startup, parent-death cleanup, and shutdown during an active write. Production TypeScript/Vite build, board geometry/material and file-drop collection checks passed. The native AppKit/WKWebView harness loaded a synthetic library and STEP model, checked close guards, native fullscreen and Escape, then verified both host/worker exit and byte-identical fixture data. The installed Applications bundle passed two LaunchServices open/reopen/quit cycles with temporary preferences. Spotlight returns the installed bundle. Python remains external; Intel and Windows execution and general-distribution notarization are not claimed.

## 2026-10-19 clickable STEP rotation rings

Production build and all 79 Python tests pass with ResourceWarnings treated as errors. `node scripts/check_rotation_handles.mjs` exercises the production Three.js rings: XYZ picking, click/reverse, zoom, drag rejection, cancellation and disposal. The native AppKit/WKWebView harness verifies a DOM pointer click updates exactly one numeric rotation by 90°, Shift-click restores it, and fullscreen/Escape/close still pass with unchanged temporary library files. Synthetic DOM events stub pointer capture; physical mouse/touch interaction is not separately automated. Native KiCad STEP export still agrees with preview transforms within 3.09e-13 mm. Only the bundled web assets and application signature were refreshed in the installed app; other runtime files were hash-verified unchanged.

The refreshed installed app also passed two LaunchServices launch/reopen/quit cycles with isolated preferences and a temporary library.


## Unified model upload — 2026-10-19

The upload area now becomes the model selectors in the same section after files are uploaded, retaining compact file/folder upload controls. Production build and all 79 Python tests pass. The native WKWebView harness uploads a synthetic symbol through the file input and verifies the same section replaces the empty dropzone with selected models. Existing package-selection, STEP rendering, fullscreen/Escape and close checks pass with unchanged temporary library files. Source release ZIP rebuilt; the installed app was subsequently updated.

## 2026-10-19 catalog thumbnails and keyboard navigation

Production TypeScript/Vite build and all 89 Python tests pass. Synthetic browser checks confirmed STEP/footprint/symbol thumbnails for three catalog rows; Down/Right and Left navigation; last-item limits; unchanged component selection when a slider consumes arrows; and navigation restricted to a one-result search. Thumbnails are rendered lazily and cached in memory, with per-render STEP worker/WebGL cleanup. Built web assets were installed with old hashed assets retained for the active session, signature verification and exact non-web runtime hash preservation. No live library or machine registrations changed. Quit/reopen loads the update.

## 2026-10-19 catalog component previews

Installed-app follow-up: Spotlight resolves the single /Applications/KiCad Library Manager.app. Replaced its outdated complete bundle with the current build, preserving a ZIP backup. Signature and 130 runtime asset files verified. Two LaunchServices launch/reopen/quit cycles passed using isolated temporary preferences and a synthetic library. Existing browser services were left running; no live data or machine registrations changed. Earlier pending app-installation notes are superseded; live category-index publication is separate and remains pending.

Catalog component visualization follow-up: production build and all 89 Python tests pass with ResourceWarnings as errors. New native preview checks verify symbol and footprint SVGs, local STEP bytes, unchanged saved transforms, absent CAD and byte-identical library files after viewing. Browser inspection of a synthetic catalog record confirms the interactive top quarter STEP view and both native drawings; multiple symbol styles share one row. The installed app was subsequently updated.

## 2026-10-19 folder category names

87 Python tests pass with ResourceWarnings treated as errors. New checks cover readable category labels, grouped footprints, unchanged catalog/source links, hidden enabled compatibility registrations, staged import CAD, stable duplicate-name allocation, manual folder moves with historical aliases, original model transforms, legacy `(module)` footprints, relative model references, logos, deletion cleanup, exact rollback, and stale source-CAD detection. Native KiCad renders synthetic grouped footprints. The live chooser after restart and publication to an existing library remain unverified by these synthetic tests.
