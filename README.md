# KiCad Library Manager

Keep each imported component's models and connector accessories together, share passive models, and export a BOM that includes housings and contacts.

## Open the app

1. Open **KiCad Library Manager** from Spotlight (Command–Space) or Applications.
2. Choose a library folder, or choose an empty folder and click **Create library**. The app remembers the last folder you opened.
3. Save your edits and close the window. Closing the last window or choosing Quit stops the app and its worker. An open editor prompts before discarding changes; an active operation must finish first.

This release is **Mac-only** (macOS 12.3 or newer). Python 3.11+ and KiCad 10 remain prerequisites. The editor, STEP viewer and importer are bundled in one installed app; Node/npm are development-only. A Windows desktop port is deferred. Library data stays portable and KiCad reads saved assets without the manager running.

For development: `npm ci`, `npm run build`, then `python3 scripts/package.py` builds a Mac app and release ZIP. `python3 app.py` is a browser development entry point, not the installed desktop workflow.

## Add a component

1. Drop a folder or ZIP onto the library view, or click **Add component** and drop it anywhere in the editor. The app selects a unique lowest-level symbol and fills available part details. Choose the intended symbol when a file contains multiple candidate parts.
2. Choose the component type. **Connectors** ask for current in amps and voltage in volts; enter known ratings. **Resistors/capacitors** start with shared symbol, footprint and STEP models in **0805**. Other bundled packages are 0402, 0603 and 1206. ICs use model metadata and manual fields, with no supplier importer.
3. Enter details manually, read a DigiKey/Mouser URL, or click **Paste clipboard**. That button opens a text box containing the copied details; click **Read pasted details** to fill the form. Choose a category such as `connectors` under the displayed `components/` prefix.
4. Previews update while you edit. **Symbol** shows the supplied symbol alongside changed connector representations. **Include both connector body styles** saves single-column and odd/even arrangements as native KiCad body styles, switchable after placement. Choose the default layout and check the pin list; no electrical mapping is inferred from geometry.
5. Inspect the footprint and 3D model. Use **top/bottom** views to inspect real through holes in the mock PCB. The saved **PCB opacity** slider fades the board while keeping copper visible. **Full screen** expands alignment; Escape exits. Alignment has XYZ **0.5 mm move buttons** that repeat while held,, **90° rotation snap buttons**, numeric fields and drag handles. Original STEP geometry and footprint pads stay unchanged.
6. Use **Add** under **Accessories** at the bottom of the form. Enter manufacturer, part number and quantity. Accessories belong to components and have no separate catalog page or add-part type. Matching identities are reused for BOM export, and new accessories save atomically with their parent.
7. Click **Save**, or press **Enter twice** in a field. There are no wizard steps or separate review page. Validation errors stay in the editor. A new import matching an existing part shows its differences and requires an explicit replacement choice; editing an existing part saves directly. Cancelling discards staged changes.

DigiKey sometimes blocks direct page retrieval. For supported YAGEO/KEMET parts, the app can read the exact part's manufacturer PDF and identifies that source. This fallback imports specifications, not supplier stock or prices. Other blocked pages can still require copied product details or manual fields; the app does not bypass every distributor restriction.

Click a catalog component and choose **Edit component** to change its metadata, folder, models, alignment or accessories. IDs stay stable and changed files are backed up.

## Passive tables

**Resistors** and **Capacitors** are two spreadsheet-style views of one catalog. Each purchasable manufacturer/part-number combination has a row so the BOM can identify what to buy. Standard passives share symbols, footprints and models; adding another part number does **not** create another model folder. There are no independently maintained resistor/capacitor spreadsheets to keep in sync.

## Move folders manually

Move or rename a **whole component folder** anywhere under `components`, keeping its `component.json`, recipe and CAD files together. Then open the manager or click **Refresh**. It finds the component by its stable ID and updates catalog paths, model references and KiCad indexes.

Existing PCB designs embed their own model paths. After moving a component folder, Refresh the manager and update already placed footprints from the library in KiCad; the manager does not rewrite board files.

Do not rename or move individual CAD files, shared generic model files, or the `components`/`appdata` folders. Missing files, duplicate component folders and foreign markers are reported and block writes until corrected. Wait for cloud sync before refreshing after a move. Moving or renaming the entire library has separate connection implications below.

## Use the library in KiCad

1. Open **KiCad connection** in the manager.
2. Install your platform's SQLite ODBC driver and configure the **VirtusSQLite** user DSN. See [setup details](docs/SETUP.md).
3. Click **Check database connection** to query the actual library configuration using the native ODBC manager.
4. Close KiCad, then click **Connect to KiCad**. The app backs up its changes and preserves unrelated settings.
5. Reopen KiCad. The database nickname uses your library folder's name. Category names and **SearchPath** contain folder words, for example `Workshop Parts/components/ICs/op amps/LM123`.

New imports update shared library tables. KiCad may need reopening to refresh cached libraries. Folder hierarchy is searchable metadata, not an arbitrary nested chooser tree.

`MYCO_PARTS_DIR` points to the selected library's `appdata` folder. Switching libraries is explicit. Moving the entire library preserves its identity; reconnect its new location on that computer. **Renaming the root changes the KiCad nickname:** reconnect and deliberately update old designs' library links. Moving a component category does not change its database key.

## Export a BOM from KiCad

1. Open **BOM export** in the manager and copy its generator command.
2. In KiCad's schematic editor, add the command to the external/legacy BOM generator as **Library Manager BOM**.
3. Generate the BOM and keep its outputs with your PCB project.

The exporter produces purchasing, PCB, accessory and detailed CSVs plus a JSON snapshot. A connector used twice with a recipe of one housing and six crimps produces two housings and twelve crimps. DNP/excluded components are omitted when marked in the KiCad XML.

If an accessory also appears explicitly in the schematic, set its `AccessoryOf` field to the owning connector reference, such as `J1`. Its quantity must match the recipe. Components without that ownership field remain independent requirements. Populated-contact counting and per-instance accessory choices are future features.

## Portable folder layout

```text
Your Library/
  components/
    ICs/op amps/LM123/
      component.json
      symbol.kicad_sym
      footprint.pretty/LM123.kicad_mod
      model.step
      recipes.json
    connectors/...
    resistors/
    capacitors/
    generic_models/
      symbols/
      footprints/
      models-3d/
    logos/...
  appdata/
    library.json
    components.csv
    parts.sqlite / parts.kicad_dbl
    sym-lib-table / fp-lib-table
    recipes/
    backups/
    original-downloads/
    docs/
```

The root contains only `components` and `appdata`; application code lives in the installed Mac app. `appdata/components.csv` owns product metadata. A connector's `recipes.json` lives with that connector. Catalog-only records need no folders; any recipes they own are kept under `appdata/recipes`. SQLite and library tables are generated. Original inputs are archived with hashes. No example catalog parts are seeded.

Use **one editor at a time** in a synced folder and wait for sync before changing computers. Keep the whole library together and do not edit generated files.

## Development and verification

```sh
npm ci
npm run build
python3 -B -W error::ResourceWarning -m unittest discover -s tests -v
node scripts/check_board_geometry.mjs
node scripts/check_drop_files.mjs
python3 scripts/check_alignment.py
python3 app.py --no-browser
```

The alignment check compares preview transforms with native KiCad STEP exports using temporary fixtures. `KICAD_CLI` can select the CLI executable. Actual verification and remaining platform acceptance are recorded in [verification notes](docs/VERIFICATION.md). Native Windows launch and live KiCad chooser/placement still need hands-on checks.

Module contracts are in [architecture notes](docs/ARCHITECTURE.md). **Open library** does not silently convert retired importer libraries; [migration](docs/MIGRATION.md) is an explicit copy operation.


### Standard IC packages

In Add component, choose **IC**, then use **Standard package** directly below the component type buttons. The bundled collection includes TO-220-3 horizontal tab down, SOT-23, SOT-23-5, SOT-23-6, SOIC-8 (3.9 × 4.9 mm, 1.27 mm pitch), and TSSOP-8 (3 × 3 mm, 0.65 mm pitch). Each selection loads the original KiCad footprint and its STEP model for preview. Supply the device symbol and verify the manufacturer's pinout; matching pad numbers alone do not establish electrical compatibility.

Reference templates live in `components/generic_models/standard_packages/StandardPackages.pretty`, with STEP models and attribution beside them. New libraries include the collection. In an existing library, selecting a package is scratch-only; its templates are added with the component's successful Save. Existing differing templates are never overwritten. Each saved component retains its own working CAD and reviewed model transform, following the usual import and backup workflow. Use Custom / uploaded footprint to select other CAD.

The reproducible resource builder is `python3 scripts/bundle_standard_packages.py /path/to/KiCad/SharedSupport`.
