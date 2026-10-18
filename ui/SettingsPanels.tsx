import { writeClipboard } from "./desktop";
import { ArrowDownToLine, Settings2 } from "lucide-react";
import { useEffect, useState } from "react";
import { api, Library } from "./api";

import { Field } from "./fields";
export function Setup({
  library,
  notify,
}: {
  library: Library;
  notify: (s: string, e?: boolean) => void;
}) {
  const [status, setStatus] = useState<any>(null),
    [switching, setSwitching] = useState(false),
    [busy, setBusy] = useState(false),
    [odbc, setODBC] = useState<any>(null);
  useEffect(() => {
    api("setup")
      .then(setStatus)
      .catch((e) => notify(String(e), true));
  }, [library.id]);
  return (
    <div className="content narrow">
      <div className="eyebrow">ONE-TIME CONNECTION</div>
      <h1>Bring your library into KiCad</h1>
      <p className="muted">
        Connect this folder once. New components then appear through its shared
        library tables after KiCad refreshes.
      </p>
      <section className="settings-card">
        <h3>1. KiCad 10</h3>
        <p>
          {status?.cli ||
            "KiCad CLI was not found. Install KiCad 10, then reopen the manager."}
        </p>
        <h3>2. SQLite ODBC connection</h3>
        <p>
          Install the matching SQLite ODBC driver and create a user DSN named{" "}
          <code>VirtusSQLite</code>. The library uses its own relative database
          path.
        </p>
        <p className="muted">
          Mac: install sqliteodbc; Windows: use the 64-bit SQLite ODBC driver.
          Existing driver settings are preserved.
        </p>
        <button
          className="secondary"
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            try {
              setODBC(await api("check-odbc", {}));
              notify("The actual KiCad database connection passed.");
            } catch (e) {
              setODBC(null);
              notify(String(e), true);
            } finally {
              setBusy(false);
            }
          }}
        >
          Check database connection
        </button>
        {odbc && (
          <div className="info-box">
            ODBC query passed using {odbc.configuration}.{" "}
            {odbc.counts.reduce(
              (n: number, r: string[]) => n + Number(r[1]),
              0,
            )}{" "}
            parts visible.
          </div>
        )}
        <h3>3. Connect this library</h3>
        <p>
          Close KiCad first. Connection backs up its settings and adds the
          shared symbol and footprint tables.
        </p>
        <div className="info-box">
          <strong>
            {status?.connected
              ? "Library path connected"
              : "Not connected to this folder"}
          </strong>
          <p>{status?.activeLibrary || "No active Library Manager path"}</p>
          <small>
            Path registration is separate from a working ODBC driver.
          </small>
        </div>
        {status?.activeLibrary && !status.connected && (
          <label className="check-label">
            <input
              type="checkbox"
              checked={switching}
              onChange={(e) => setSwitching(e.target.checked)}
            />
            Switch this machine from the displayed library to {library.name}
          </label>
        )}
        <button
          className="primary"
          disabled={busy}
          onClick={async () => {
            setBusy(true);
            try {
              setStatus(await api("connect", { switch: switching }));
              notify(
                "Library tables connected. Reopen KiCad and verify the ODBC driver is configured.",
              );
            } catch (e) {
              notify(String(e), true);
            } finally {
              setBusy(false);
            }
          }}
        >
          <Settings2 size={17} />
          Connect to KiCad
        </button>
      </section>
    </div>
  );
}
export function BOM({
  library,
  notify,
}: {
  library: Library;
  notify: (s: string, e?: boolean) => void;
}) {
  const [status, setStatus] = useState<any>(null),
    [input, setInput] = useState(""),
    [output, setOutput] = useState(""),
    [result, setResult] = useState<any>(null);
  useEffect(() => {
    api("setup")
      .then(setStatus)
      .catch((e) => notify(String(e), true));
  }, [library.id]);
  return (
    <div className="content narrow">
      <div className="eyebrow">FROM SCHEMATIC TO PURCHASE LIST</div>
      <h1>A BOM with the whole assembly</h1>
      <p className="muted">
        Headers, housings, contacts, and hardware—with a trace back to the
        component that needs them.
      </p>
      <section className="settings-card">
        <h3>Export directly from KiCad</h3>
        <ol>
          <li>Open the schematic’s external / legacy BOM generator.</li>
          <li>
            Add the following command as a generator named{" "}
            <strong>Library Manager BOM</strong>.
          </li>
          <li>Generate the BOM from your saved design.</li>
        </ol>
        <pre className="command">
          {status?.bomCommand || "Loading command…"}
        </pre>
        <button
          className="secondary"
          onClick={() =>
            writeClipboard(status?.bomCommand || "").then(() =>
              notify("BOM command copied."),
            )
          }
        >
          Copy generator command
        </button>
        <p className="muted">
          Exports the combined purchasing list, PCB items, accessories, detailed
          sources, and a JSON snapshot beside the output.
        </p>
        <details>
          <summary>Explicit accessory symbols</summary>
          <p>
            When an accessory is also represented in the schematic, give it an{" "}
            <code>AccessoryOf</code> field naming its owning connector reference
            (for example J1). Its quantity must match the fixed recipe.
            Unassigned identical parts remain independent purchases.
          </p>
        </details>
      </section>
      <section className="settings-card">
        <h3>Or test an existing KiCad XML export</h3>
        <Field label="KiCad XML input" value={input} onChange={setInput} />
        <Field label="BOM output path" value={output} onChange={setOutput} />
        <button
          className="primary"
          disabled={!input || !output}
          onClick={async () => {
            try {
              setResult(await api("bom", { input, output }));
              notify("BOM files exported.");
            } catch (e) {
              notify(String(e), true);
            }
          }}
        >
          <ArrowDownToLine size={17} />
          Export BOM
        </button>
        {result && (
          <>
            <h4>Created files</h4>
            {result.files.map((f: string) => (
              <p className="mono" key={f}>
                {f}
              </p>
            ))}
            {result.warnings.map((w: string) => (
              <p className="warning-text" key={w}>
                {w}
              </p>
            ))}
          </>
        )}
      </section>
    </div>
  );
}
