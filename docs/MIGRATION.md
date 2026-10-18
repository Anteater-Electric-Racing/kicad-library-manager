# Converting an old importer library

The converter makes a separate Library Manager folder. It reads only the selected old library and does not connect the new copy to KiCad or alter old designs.

```sh
python3 scripts/migrate_legacy.py "/path/to/PCB components" --audit
python3 scripts/migrate_legacy.py "/path/to/PCB components" "/path/to/PCB components - Library Manager"
```

The destination must not exist. Keep the source idle during conversion. A changed source, missing required symbol/footprint, ambiguous library link, symlink, or destination collision stops conversion before the new folder is published.

The converter preserves every current catalog ID and imports only current rows. It does not restore old passive seed rows from backups or make guesses about connector accessories, pin mappings, or missing model positions. Each bespoke component receives a folder with its symbol, footprint, model files and empty local accessory recipe. Resistors and capacitors share their existing source CAD definitions and have no per-part folders. Their metadata remains individual purchasing rows in the central catalog.

Legacy mounting pads and all model transformation nodes are checked for exact structural equality after model paths are relocated. Known obsolete `${MYCO_PARTS_DIR}/STEP` references are resolved against the source's own STEP directory. References to missing external models are retained and reported. A local model matching a component's exact MPN, when the footprint never attached it, is copied beside that component but remains unattached until alignment is checked.

The new folder contains `components`, `appdata`, and launchers. Under `appdata/migration`:

- `README.md` summarizes the result and carried-forward issues.
- `report.json` maps each source row to its new row and preserves every original field.
- `source-catalog.csv` retains the original authoritative catalog bytes.
- `source-inventory.json` records every source file's SHA-256 and size.
- `legacy-source-snapshot.zip` preserves the complete original folder, including historical backups, unused variants, provenance and licenses.

Original downloads are additionally available under `appdata/original-downloads/legacy`. Passive PDFs stay there as original archive material; they are not copied into working passive folders. Nonempty historical fields outside the new catalog's supported schema are kept in Notes, explicitly marked historical, and preserved verbatim in the report. The removed legacy status field is blank in the new catalog.

After conversion, open the new library and use its KiCad connection page when ready. Existing designs still reference the old library names and need deliberate relinking if they should use the new catalog. Copying a library does not update existing placed instances or establish that old imported electrical/mechanical data is correct.

## Virtus conversion verification — 2026-09-25

The user-selected `PCB components` library was copied into its sibling `PCB components - Library Manager`.

- 45 current catalog records and all IDs preserved: 39 connectors, 2 ICs, 1 resistor, 2 capacitors, and 1 other component.
- All 453 source files remained SHA-256 identical after conversion and native verification. The complete original snapshot is included in the new library.
- The three passive records share CAD with no component folders. All 42 bespoke records have component manifests and local recipes. Eight logo footprints were retained.
- 90 native KiCad symbol/footprint render jobs passed, including both logo libraries.
- The new library's exact database configuration queried successfully through KiCad's bundled ODBC manager and returned all 45 records across seven categories.
- Library path reconciliation reports no missing or ambiguous component folders.
- Two pre-existing missing external WRL models remain reported: BM15B-GHS-TBT and SM15B-GHS-TB. No replacement model or alignment was invented.
- Five synthetic migration tests passed. No global KiCad settings or old designs were changed. Native chooser/placement and Windows remain separate acceptance checks.

The copied runtime is installed by the main build after the updated UI is bundled; the conversion report does not by itself establish launcher acceptance.
