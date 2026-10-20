import {
  Box,
  Cable,
  Check,
  CircleHelp,
  Cpu,
  LoaderCircle,
  Package,
  Plus,
  ShieldCheck,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api, assetURL, identity, Library, Transform } from "./api";
import ModelViewer from "./ModelViewer";
import { closeGuard, readClipboard } from "./desktop";

import { Field } from "./fields";
import { droppedFiles, UploadEntry } from "./files";
const icon = (type: string) =>
  type === "connector" ? (
    <Cable size={18} />
  ) : type === "IC" ? (
    <Cpu size={18} />
  ) : (
    <Package size={18} />
  );
const categoryFor = (type: string, _mode: string) =>
  type === "connector"
    ? "components/connectors"
    : type === "accessory"
      ? "components/accessories"
      : ["resistor", "capacitor"].includes(type)
        ? `components/${type}s`
        : type === "IC"
          ? "components/ICs"
          : "components/other";

type AccessoryItem = {
  partID?: string;
  manufacturer: string;
  mpn: string;
  quantity: number;
  role: string;
};

export default function ImportDialog({
  library,
  editingID,
  initialEntries = [],
  onClose,
  onSave,
}: {
  library: Library;
  editingID: string;
  initialEntries?: UploadEntry[];
  onClose: () => void;
  onSave: (l: Library) => void;
}) {
  const [session, setSession] = useState<any>(null),
    [busy, setBusy] = useState(""),
    [error, setError] = useState("");
  useEffect(() => {
    closeGuard("editor", { dirty: true, busy: !!busy });
    return () => closeGuard("editor");
  }, [busy]);
  const [part, setPart] = useState<Record<string, string>>({
      Type: "resistor",
      Package: "0805",
    }),
    [mode, setMode] = useState("generic"),
    [category, setCategory] = useState("components/resistors"),
    [folderName, setFolderName] = useState("");
  const [url, setURL] = useState(""),
    [content, setContent] = useState(""),
    [pasteOpen, setPasteOpen] = useState(false),
    [pasteNotice, setPasteNotice] = useState("");
  const [supplierNotice, setSupplierNotice] = useState<{
    warnings: string[];
    provenance: { method?: string; url?: string; fields?: string[] };
  } | null>(null);
  const [symbolAsset, setSymbolAsset] = useState(""),
    [symbolName, setSymbolName] = useState(""),
    [footprintAsset, setFootprintAsset] = useState(""),
    [modelAsset, setModelAsset] = useState(""),
    [modelAction, setModelAction] = useState("preserve"),
    [modelIndex, setModelIndex] = useState<number | null>(null);
  const [alternative, setAlternative] = useState(false),
    [layout, setLayout] = useState("single"),
    [confirmed, setConfirmed] = useState(false),
    [transform, setTransform] = useState<Transform>(identity());
  const [info, setInfo] = useState<any>(null),
    [review, setReview] = useState<any>(null),
    [recipes, setRecipes] = useState<AccessoryItem[]>([]);
  const [previewTab, setPreviewTab] = useState("footprint"),
    [selectedPin, setSelectedPin] = useState(""),
    [svgs, setSVGs] = useState<string[]>([]),
    [originalSVGs, setOriginalSVGs] = useState<string[]>([]),
    [previewBusy, setPreviewBusy] = useState(false),
    [svgError, setSVGError] = useState("");
  const [replace, setReplace] = useState(false);
  const files = useRef<HTMLInputElement>(null),
    folders = useRef<HTMLInputElement>(null);
  const uploadedInitial = useRef(false);
  const explicitType = useRef(!!editingID);
  const saving = useRef(false);
  const lastEnter = useRef(0);
  const inferredMetadata = useRef<Record<string, string>>({});
  const initialTransform = useRef<Transform>(identity());
  const partSet = (key: string, value: string) => {
    setPart((p) => ({ ...p, [key]: value }));
    setReview(null);
  };
  useEffect(() => {
    let disposed = false,
      id = "";
    api(
      editingID ? "import/edit" : "import/new",
      editingID ? { partID: editingID } : {},
    )
      .then((result) => {
        const s = result.inventory || result;
        id = s.id;
        if (disposed) {
          api("import/close", { session: id });
          return;
        }
        setSession(s);
        if (result.draft) {
          const d = result.draft;
          setPart(d.part);
          setMode(d.mode);
          setCategory(d.category);
          setFolderName(d.folderName);
          setRecipes(
            d.recipe.items.map((item: any) => {
              const linked = library.parts.find((p) => p.ID === item.partID);
              return {
                ...item,
                manufacturer: linked?.Manufacturer || item.manufacturer || "",
                mpn: linked?.MPN || item.mpn || "",
              };
            }),
          );
          setSymbolAsset(d.symbolAsset || "");
          setSymbolName(d.symbolName || "");
          setFootprintAsset(d.footprintAsset || "");
          setModelAsset(d.modelAsset || "");
          setModelAction(d.modelAction || "preserve");
          setModelIndex(d.modelIndex ?? null);
          setURL(d.part.SupplierURL || "");
          if (d.transform) setTransform(d.transform);
        }
      })
      .catch((e) => setError(String(e)));
    return () => {
      disposed = true;
      if (id) api("import/close", { session: id }).catch(() => {});
    };
  }, [editingID]);
  const draft = {
    editingID,
    part,
    mode,
    category,
    folderName,
    symbolAsset,
    symbolName,
    footprintAsset,
    modelAsset,
    modelAction,
    alternative,
    layout,
    pinsConfirmed: confirmed,
    transform,
    recipe: { version: 1, items: recipes },
  };
  useEffect(() => {
    if (!session || mode !== "bespoke" || !footprintAsset) return;
    let disposed = false;
    api("import/inspect", {
      session: session.id,
      draft: { symbolAsset, symbolName, footprintAsset },
    })
      .then((r) => {
        if (disposed) return;
        setInfo(r);
        const t = r.footprint?.models[modelIndex ?? 0];
        initialTransform.current = t
          ? { offset: t.offset, rotate: t.rotate, scale: t.scale }
          : identity();
        setTransform(initialTransform.current);
        setConfirmed(false);
        setReview(null);
      })
      .catch((e) => {
        if (!disposed) setError(String(e));
      });
    return () => {
      disposed = true;
    };
  }, [session?.id, symbolAsset, symbolName, footprintAsset, mode, modelIndex]);
  useEffect(() => {
    if (mode !== "generic") return;
    let disposed = false;
    setInfo(null);
    api(
      `generic-preview?${new URLSearchParams({ type: part.Type, package: part.Package || "0805", partID: editingID })}`,
    )
      .then((r) => {
        if (disposed) return;
        const generic = r.info || r;
        setInfo(generic);
        const model =
          generic.footprint?.models?.[generic.genericModelIndex ?? 0];
        const t = model
          ? { offset: model.offset, rotate: model.rotate, scale: model.scale }
          : identity();
        initialTransform.current = t;
        setTransform(t);
      })
      .catch((e) => {
        if (!disposed) setError(String(e));
      });
    return () => {
      disposed = true;
    };
  }, [mode, part.Type, part.Package, editingID]);
  const draftKey = JSON.stringify(draft);
  useEffect(() => {
    setReview(null);
    setReplace(false);
    lastEnter.current = 0;
  }, [draftKey]);
  useEffect(() => {
    if (!session || uploadedInitial.current || !initialEntries.length) return;
    uploadedInitial.current = true;
    void upload(initialEntries);
  }, [session?.id]);
  const visualKey = JSON.stringify({
    symbolAsset,
    symbolName,
    footprintAsset,
    alternative,
    layout,
    part: {
      MPN: part.MPN,
      Value: part.Value,
      Reference: part.Reference,
      Datasheet: part.Datasheet,
    },
  });
  useEffect(() => {
    if (!session || !["symbol", "native"].includes(previewTab)) return;
    let disposed = false;
    setSVGs([]);
    setOriginalSVGs([]);
    setSVGError("");
    setPreviewBusy(true);
    const timer = window.setTimeout(async () => {
      try {
        let result;
        if (mode === "generic") {
          result = await api(
            `preview?${new URLSearchParams({
              kind: "generic",
              type: part.Type,
              package: part.Package || "0805",
              partID: editingID,
              render: previewTab === "native" ? "footprint" : "symbol",
            })}`,
          );
        } else {
          result = await api("import/preview", {
            session: session.id,
            draft,
            kind: previewTab === "native" ? "footprint" : "symbol",
          });
        }
        if (!disposed) {
          setSVGs(result.svgs || []);
          setOriginalSVGs(result.originals || []);
        }
      } catch (e) {
        if (!disposed) setSVGError(String(e));
      } finally {
        if (!disposed) setPreviewBusy(false);
      }
    }, 300);
    return () => {
      disposed = true;
      window.clearTimeout(timer);
    };
  }, [
    session?.id,
    previewTab,
    visualKey,
    mode,
    part.Type,
    part.Package,
    editingID,
  ]);
  async function task(label: string, fn: () => Promise<void>) {
    setBusy(label);
    setError("");
    try {
      await fn();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy("");
    }
  }
  async function upload(entries: UploadEntry[]) {
    if (!session || busy || !entries.length) return;
    await task("Reading CAD files…", async () => {
      let inventory = session;
      for (const { file, name } of entries) {
        if (name.split("/").some((x) => x.startsWith(".") || x === "__MACOSX"))
          continue;
        if (file.size > 128 * 1024 * 1024)
          throw new Error("Select files smaller than 128 MiB each.");
        const data = await new Promise<string>((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = () => resolve(String(reader.result).split(",")[1]);
          reader.onerror = reject;
          reader.readAsDataURL(file);
        });
        inventory = await api("import/upload", {
          session: session.id,
          name,
          data,
        });
      }
      setSession(inventory);
      setMode("bespoke");
      const symbols = inventory.assets.filter(
          (a: any) => a.type === ".kicad_sym" && !a.error,
        ),
        fps = inventory.assets.filter(
          (a: any) => a.type === ".kicad_mod" && !a.error,
        ),
        models = inventory.assets.filter((a: any) =>
          [".step", ".stp"].includes(a.type),
        );
      if (symbols.length === 1) {
        setSymbolAsset(symbols[0].id);
        const chosen =
          symbols[0].suggestedSymbol ||
          (symbols[0].symbols.length === 1 ? symbols[0].symbols[0] : "");
        setSymbolName(chosen);
        applySymbolMetadata(symbols[0], chosen);
      }
      if (fps.length === 1) setFootprintAsset(fps[0].id);
      if (models.length === 1) {
        setModelAsset(models[0].id);
        if (models[0].id !== modelAsset) setModelAction("replace");
      }
      setReview(null);
    });
  }
  async function readSupplier(useCopiedDetails = false) {
    setSupplierNotice(null);
    await task("Reading product details…", async () => {
      const r = await api("supplier", {
        url,
        content: useCopiedDetails ? content : "",
      });
      setSupplierNotice({
        warnings: r.warnings || [],
        provenance: r.provenance || {},
      });
      setPart((p) => {
        const incoming = Object.fromEntries(
          Object.entries(r.part)
            .filter(([, v]) => v !== "")
            .map(([k, v]) => [k, String(v)]),
        );
        const changedIdentity =
          incoming.MPN &&
          p.MPN &&
          (incoming.MPN.toLowerCase() !== p.MPN.toLowerCase() ||
            (incoming.Manufacturer &&
              p.Manufacturer &&
              incoming.Manufacturer.toLowerCase() !==
                p.Manufacturer.toLowerCase()));
        const base = { ...p };
        if (changedIdentity) {
          for (const key of [
            "MPN",
            "Manufacturer",
            "Value",
            "Resistance",
            "Capacitance",
            "Description",
            "Datasheet",
            "Distributor_PN",
            "Tolerance",
            "Power_W",
            "Voltage_VDC",
            "Current_A",
            "Voltage_V",
            "Dielectric",
            "MetricPackage",
          ])
            base[key] = "";
          base.Package = ["resistor", "capacitor"].includes(p.Type)
            ? "0805"
            : "";
        }
        for (const key of [
          "UnitPrice",
          "PriceCurrency",
          "PriceQuantity",
          "PriceCheckedUTC",
        ])
          base[key] = "";
        return { ...base, ...incoming };
      });
      if (r.part.Type) {
        const newMode =
          r.part.Type === "accessory"
            ? "accessory"
            : ["resistor", "capacitor"].includes(r.part.Type)
              ? mode
              : "bespoke";
        setMode(newMode);
        setCategory(categoryFor(r.part.Type, newMode));
      }
      setReview(null);
    });
  }
  function applySymbolMetadata(asset: any, name: string) {
    const suggested = asset?.metadata?.[name];
    if (!suggested) return;
    const previous = inferredMetadata.current;
    inferredMetadata.current = suggested;
    setPart((current) => {
      const next = { ...current };
      for (const [key, value] of Object.entries(suggested)) {
        if (
          (!next[key] || (!editingID && next[key] === previous[key])) &&
          value
        )
          next[key] = String(value);
      }
      return next;
    });
    if (!explicitType.current && !editingID) {
      const reference = suggested.Reference?.toUpperCase();
      const type = ["J", "P", "CN"].includes(reference)
        ? "connector"
        : reference === "U"
          ? "IC"
          : reference === "R"
            ? "resistor"
            : reference === "C"
              ? "capacitor"
              : "other";
      setPart((current) => ({
        ...current,
        Type: type,
        Package: ["resistor", "capacitor"].includes(type)
          ? current.Package || "0805"
          : "",
      }));
      setCategory(categoryFor(type, "bespoke"));
    }
  }
  async function pasteClipboard() {
    setPasteOpen(true);
    setPasteNotice("");
    try {
      const text = await readClipboard();
      setContent(text);
      if (!text.trim())
        setPasteNotice("The clipboard is empty. Paste product details below.");
    } catch {
      setPasteNotice(
        "Clipboard access is unavailable. Paste product details into the text box below.",
      );
    }
  }
  async function save() {
    if (busy || !session || saving.current) return;
    saving.current = true;
    await task("Saving component…", async () => {
      const r =
        review || (await api("import/prepare", { session: session.id, draft }));
      if (r.replacing && !editingID && !replace) {
        setReview(r);
        return;
      }
      const saved = await api("import/save", {
        session: session.id,
        token: r.token,
        replace: !!editingID || replace,
      });
      onSave(saved.library);
      onClose();
    });
    saving.current = false;
  }
  function editAccessory(
    index: number,
    key: keyof AccessoryItem,
    value: string | number,
  ) {
    setRecipes((items) =>
      items.map((item, i) => {
        if (i !== index) return item;
        const updated = { ...item, [key]: value };
        if (key === "manufacturer" || key === "mpn") delete updated.partID;
        return updated;
      }),
    );
    setReview(null);
  }
  const hasModelAssets = !!session?.assets?.length;
  const selectedSymbol = session?.assets.find((a: any) => a.id === symbolAsset);
  const visibleInfo = review?.info || info;
  const modelURL =
    mode === "generic" && visibleInfo?.genericModel
      ? assetURL("generic-model", { path: visibleInfo.genericModel })
      : modelAsset && session
        ? assetURL("asset", { session: session.id, asset: modelAsset })
        : "";
  return (
    <div className="modal-backdrop">
      <section
        className="import-dialog"
        onDragOver={(e) => {
          if (e.dataTransfer.types.includes("Files")) e.preventDefault();
        }}
        onDrop={async (e) => {
          e.preventDefault();
          e.stopPropagation();
          if (!busy && session) {
            try {
              await upload(await droppedFiles(e.dataTransfer.items));
            } catch (error) {
              setError(String(error));
            }
          }
        }}
        onKeyDown={(e) => {
          const target = e.target as HTMLElement;
          if (
            e.key !== "Enter" ||
            e.repeat ||
            e.nativeEvent.isComposing ||
            target.isContentEditable ||
            ["TEXTAREA", "SELECT", "BUTTON"].includes(target.tagName) ||
            (target instanceof HTMLInputElement &&
              ["checkbox", "file"].includes(target.type))
          )
            return;
          e.preventDefault();
          const now = Date.now();
          if (lastEnter.current && now - lastEnter.current < 600) {
            lastEnter.current = 0;
            void save();
          } else lastEnter.current = now;
        }}
      >
        <header className="dialog-header">
          <div>
            <span className="eyebrow">GROW YOUR LIBRARY</span>
            <h2>{editingID ? "Edit component" : "Add component"}</h2>
          </div>
          <button className="close" disabled={!!busy} onClick={onClose}>
            <X size={22} />
          </button>
        </header>
        {error && (
          <div className="notice error">
            <CircleHelp size={18} />
            <span>{error}</span>
            <button onClick={() => setError("")}>
              <X size={16} />
            </button>
          </div>
        )}
        <div className="import-body">
          <fieldset className="import-controls" disabled={!!busy || !session}>
            <>
              <section
                className={`model-upload${hasModelAssets ? " has-assets" : ""}`}
                aria-label="Component models"
              >
                {hasModelAssets ? (
                  <>
                    <div className="model-upload-heading">
                      <h3>Models that belong together</h3>
                      <div className="model-upload-actions">
                        <button
                          className="text-button"
                          onClick={() => files.current?.click()}
                        >
                          <Upload size={15} /> Add files
                        </button>
                        <button
                          className="text-button"
                          onClick={() => folders.current?.click()}
                        >
                          Add folder
                        </button>
                      </div>
                    </div>
                    <p className="muted">
                      Original downloads are preserved. Review the working
                      models before saving. Drop more files here to add models.
                    </p>
                    {mode === "bespoke" && (
                      <>
                        <AssetSelect
                          label="Symbol library"
                          assets={
                            session?.assets.filter(
                              (a: any) => a.type === ".kicad_sym",
                            ) || []
                          }
                          value={symbolAsset}
                          onChange={(v) => {
                            setSymbolAsset(v);
                            const asset = session.assets.find(
                              (a: any) => a.id === v,
                            );
                            const name =
                              asset?.suggestedSymbol ||
                              (asset?.symbols?.length === 1
                                ? asset.symbols[0]
                                : "");
                            setSymbolName(name);
                            applySymbolMetadata(asset, name);
                          }}
                        />
                        {selectedSymbol && (
                          <label className="field">
                            <span>Symbol in file</span>
                            <select
                              value={symbolName}
                              onChange={(e) => {
                                setSymbolName(e.target.value);
                                applySymbolMetadata(
                                  selectedSymbol,
                                  e.target.value,
                                );
                              }}
                            >
                              <option value="">Choose a symbol</option>
                              {selectedSymbol.symbols?.map((n: string) => (
                                <option key={n}>{n}</option>
                              ))}
                            </select>
                          </label>
                        )}
                        <AssetSelect
                          label="Footprint"
                          assets={
                            session?.assets.filter(
                              (a: any) => a.type === ".kicad_mod",
                            ) || []
                          }
                          value={footprintAsset}
                          onChange={setFootprintAsset}
                        />
                        <AssetSelect
                          label="STEP model (optional)"
                          assets={
                            session?.assets.filter((a: any) =>
                              [".step", ".stp"].includes(a.type),
                            ) || []
                          }
                          value={modelAsset}
                          onChange={(v) => {
                            setModelAsset(v);
                            setModelAction(v ? "replace" : "remove");
                            setReview(null);
                          }}
                        />
                        {!!editingID &&
                          (info?.footprint?.models?.length || 0) > 1 && (
                            <p className="info-box">
                              This footprint has {info.footprint.models.length}{" "}
                              model references. The 3D viewer shows the selected
                              STEP; other references keep their saved alignment
                              unless you replace or remove the model.
                            </p>
                          )}
                      </>
                    )}
                  </>
                ) : (
                  <div className="dropzone">
                    <Upload size={30} />
                    <strong>Drop a folder, ZIP, or CAD files</strong>
                    <span>KiCad symbols · footprints · STEP</span>
                    <div>
                      <button
                        className="secondary"
                        onClick={() => files.current?.click()}
                      >
                        Choose files
                      </button>
                      <button
                        className="text-button"
                        onClick={() => folders.current?.click()}
                      >
                        Choose folder
                      </button>
                    </div>
                  </div>
                )}
                {mode === "generic" && (
                  <div className="info-box">
                    Using shared {part.Type} models for package {part.Package}.
                    The symbol, footprint, and STEP model are ready to preview.
                    Change the package in Part details to use another size.
                  </div>
                )}
                {mode === "accessory" && (
                  <div className="info-box">
                    Accessories are catalog entries and do not require models.
                  </div>
                )}
              </section>
              <input
                ref={files}
                type="file"
                multiple
                hidden
                onChange={(e) => {
                  const entries = Array.from(e.target.files || []).map(
                    (file) => ({ file, name: file.name }),
                  );
                  e.target.value = "";
                  void upload(entries);
                }}
              />
              <input
                ref={folders}
                type="file"
                multiple
                hidden
                {...({ webkitdirectory: "" } as any)}
                onChange={(e) => {
                  const entries = Array.from(e.target.files || []).map(
                    (file) => ({
                      file,
                      name: file.webkitRelativePath || file.name,
                    }),
                  );
                  e.target.value = "";
                  void upload(entries);
                }}
              />
            </>

            <>
              <h3>What are you adding?</h3>
              <div className="type-grid">
                {["resistor", "capacitor", "connector", "IC", "other"].map(
                  (t) => (
                    <button
                      key={t}
                      className={part.Type === t ? "selected" : ""}
                      onClick={() => {
                        explicitType.current = true;
                        const m =
                          t === "accessory"
                            ? "accessory"
                            : ["resistor", "capacitor"].includes(t)
                              ? "generic"
                              : "bespoke";
                        setPart((p) => ({
                          ...p,
                          Type: t,
                          Package: ["resistor", "capacitor"].includes(t)
                            ? "0805"
                            : "",
                        }));
                        setReview(null);
                        setMode(m);
                        setCategory(categoryFor(t, m));
                        setAlternative(false);
                      }}
                    >
                      {icon(t)}
                      {t}
                    </button>
                  ),
                )}
              </div>
              {part.Type === "IC" && (
                <label className="field">
                  <span>Standard package</span>
                  <select
                    aria-label="Standard package"
                    disabled={!!busy || !session}
                    value={
                      session?.assets.find((a: any) => a.id === footprintAsset)
                        ?.standardPackage || ""
                    }
                    onChange={(e) => {
                      const packageID = e.target.value;
                      if (!packageID) {
                        setFootprintAsset("");
                        setModelAsset("");
                        setModelAction("remove");
                        setInfo(null);
                        partSet("Package", "");
                        return;
                      }
                      void task("Loading standard package…", async () => {
                        const result = await api("import/standard-package", {
                          session: session.id,
                          package: packageID,
                        });
                        setSession(result.inventory);
                        setFootprintAsset(result.footprintAsset);
                        setModelAsset(result.modelAsset);
                        setModelAction("replace");
                        setModelIndex(null);
                        setMode("bespoke");
                        partSet("Package", result.package);
                        setPreviewTab("footprint");
                      });
                    }}
                  >
                    <option value="">Custom / uploaded footprint</option>
                    {(session?.standardPackages || []).map((item: any) => (
                      <option key={item.id} value={item.id}>
                        {item.label}
                      </option>
                    ))}
                  </select>
                  <small>
                    Includes a footprint and STEP model. Supply the device
                    symbol and check its pinout against the datasheet.
                  </small>
                </label>
              )}
              {["resistor", "capacitor"].includes(part.Type) && (
                <div className="segmented">
                  <button
                    className={mode === "generic" ? "selected" : ""}
                    disabled={!["resistor", "capacitor"].includes(part.Type)}
                    onClick={() => {
                      setMode("generic");
                      setCategory(categoryFor(part.Type, "generic"));
                      setReview(null);
                    }}
                  >
                    Use shared models
                  </button>
                  <button
                    className={mode === "bespoke" ? "selected" : ""}
                    onClick={() => {
                      setMode("bespoke");
                      setCategory(categoryFor(part.Type, "bespoke"));
                      setReview(null);
                    }}
                  >
                    Use custom models
                  </button>
                </div>
              )}
              {part.Type !== "IC" && (
                <div className="supplier-box">
                  <label>Start with a supplier page</label>
                  <div className="inline">
                    <input
                      placeholder="Paste a DigiKey or Mouser product URL"
                      value={url}
                      onChange={(e) => setURL(e.target.value)}
                    />
                    <button
                      className="secondary"
                      disabled={!!busy}
                      onClick={() => readSupplier()}
                    >
                      Read page
                    </button>
                  </div>
                  <button
                    className="secondary"
                    disabled={!!busy}
                    onClick={pasteClipboard}
                  >
                    Paste clipboard
                  </button>
                  {pasteOpen && (
                    <div className="clipboard-details">
                      {pasteNotice && <p role="status">{pasteNotice}</p>}
                      <textarea
                        placeholder="Copy the product identity and specifications from your browser…"
                        value={content}
                        onChange={(e) => setContent(e.target.value)}
                      />
                      <button
                        className="text-button"
                        onClick={() => readSupplier(true)}
                      >
                        Read pasted details
                      </button>
                    </div>
                  )}
                  {supplierNotice && (
                    <div className="info-box" role="status">
                      <strong>
                        {supplierNotice.provenance.method ===
                        "manufacturer-specsheet"
                          ? "Specifications from the manufacturer"
                          : supplierNotice.provenance.method === "url-identity"
                            ? "Part identity found — specifications still needed"
                            : supplierNotice.provenance.method ===
                                "pasted-details"
                              ? "Details read from your pasted text"
                              : "Supplier details imported"}
                      </strong>
                      {supplierNotice.warnings.map((warning, index) => (
                        <p key={index}>{warning}</p>
                      ))}
                      {supplierNotice.provenance.url &&
                        /^https?:\/\//.test(supplierNotice.provenance.url) && (
                          <a
                            href={supplierNotice.provenance.url}
                            target="_blank"
                            rel="noreferrer"
                          >
                            {supplierNotice.provenance.method ===
                            "manufacturer-specsheet"
                              ? "Open manufacturer source ↗"
                              : "Open product source ↗"}
                          </a>
                        )}
                    </div>
                  )}
                </div>
              )}
              <div className="fields two">
                <Field
                  label="Manufacturer *"
                  value={part.Manufacturer}
                  onChange={(v) => partSet("Manufacturer", v)}
                />
                <Field
                  label="Part number *"
                  value={part.MPN}
                  onChange={(v) => partSet("MPN", v)}
                />
                <Field
                  label="Value"
                  value={part.Value}
                  placeholder="10k, 100nF, or part number"
                  onChange={(v) => partSet("Value", v)}
                />
                {mode === "generic" ? (
                  <label className="field">
                    <span>Package</span>
                    <select
                      value={part.Package || "0805"}
                      onChange={(e) => partSet("Package", e.target.value)}
                    >
                      {!["0402", "0603", "0805", "1206"].includes(
                        part.Package,
                      ) &&
                        part.Package && (
                          <option value={part.Package}>{part.Package}</option>
                        )}
                      {["0402", "0603", "0805", "1206"].map((size) => (
                        <option key={size} value={size}>
                          {size}
                        </option>
                      ))}
                    </select>
                  </label>
                ) : (
                  <Field
                    label="Package"
                    value={part.Package}
                    placeholder="Package name"
                    onChange={(v) => partSet("Package", v)}
                  />
                )}
              </div>
              <Field
                label="Description"
                value={part.Description}
                onChange={(v) => partSet("Description", v)}
              />
              <div className="fields two">
                <Field
                  label="Reference prefix"
                  value={part.Reference}
                  placeholder={
                    part.Type === "connector"
                      ? "J"
                      : part.Type === "resistor"
                        ? "R"
                        : part.Type === "capacitor"
                          ? "C"
                          : "U"
                  }
                  onChange={(v) => partSet("Reference", v)}
                />
              </div>
              <Field
                label="Notes"
                value={part.Notes}
                onChange={(v) => partSet("Notes", v)}
              />
              {["resistor", "capacitor"].includes(part.Type) && (
                <div className="fields two">
                  <Field
                    label="Tolerance"
                    value={part.Tolerance}
                    placeholder="1%"
                    onChange={(v) => partSet("Tolerance", v)}
                  />
                  <Field
                    label={
                      part.Type === "resistor"
                        ? "Power rating"
                        : "Voltage rating"
                    }
                    value={
                      part[part.Type === "resistor" ? "Power_W" : "Voltage_VDC"]
                    }
                    placeholder={part.Type === "resistor" ? "0.125 W" : "50 V"}
                    onChange={(v) =>
                      partSet(
                        part.Type === "resistor" ? "Power_W" : "Voltage_VDC",
                        v,
                      )
                    }
                  />
                </div>
              )}
              {part.Type === "connector" && (
                <div className="fields two">
                  <Field
                    label="Current rating (amps)"
                    value={part.Current_A}
                    placeholder="e.g. 5 A"
                    onChange={(v) => partSet("Current_A", v)}
                  />
                  <Field
                    label="Voltage rating (volts)"
                    value={part.Voltage_V}
                    placeholder="e.g. 250 V"
                    onChange={(v) => partSet("Voltage_V", v)}
                  />
                </div>
              )}
              <Field
                label="Online datasheet"
                value={part.Datasheet}
                placeholder="https://…"
                onChange={(v) => partSet("Datasheet", v)}
              />
              {mode === "bespoke" && (
                <>
                  <label className="field">
                    <span>Category under components</span>
                    <div className="category-input">
                      <span>components/</span>
                      <input
                        list="categories"
                        value={category.replace(/^components\/?/, "")}
                        placeholder="connectors"
                        onChange={(e) => {
                          setCategory(
                            "components/" +
                              e.target.value.replace(/^components\//, ""),
                          );
                          setReview(null);
                        }}
                      />
                    </div>
                    <datalist id="categories">
                      {library.categories
                        .filter(
                          (c) =>
                            !/^components\/(generic_models|logos)(\/|$)/i.test(
                              c,
                            ),
                        )
                        .map((c) => (
                          <option
                            value={c.replace(/^components\/?/, "")}
                            key={c}
                          />
                        ))}
                    </datalist>
                  </label>
                  <Field
                    label="Component folder name (optional)"
                    value={folderName}
                    placeholder={part.MPN || "Defaults to part number"}
                    onChange={(v) => {
                      setFolderName(v);
                      setReview(null);
                    }}
                  />
                </>
              )}
              {mode === "generic" && (
                <p className="info-box">
                  One catalog row per purchasable part number. All {part.Type}s
                  with this package share the same symbol, footprint, and STEP
                  model.
                </p>
              )}
            </>
            <>
              {mode === "bespoke" && (
                <>
                  {part.Type === "connector" && (
                    <div className="connector-options">
                      <label className="check-label">
                        <input
                          type="checkbox"
                          checked={alternative}
                          disabled={!info?.inference?.eligible}
                          onChange={(e) => {
                            setAlternative(e.target.checked);
                            setReview(null);
                          }}
                        />
                        <strong>Include both connector body styles</strong>
                      </label>
                      <small>
                        Single column and odd/even layouts are saved together.
                        Switch body style in KiCad after placement.
                      </small>
                      {info?.inference && (
                        <p>
                          {info.inference.count} numbered connections ·{" "}
                          {info.inference.mountingHoles} mounting holes
                        </p>
                      )}
                      {info?.inference?.reasons.map((r: string) => (
                        <p className="warning-text" key={r}>
                          {r}
                        </p>
                      ))}
                      {alternative && (
                        <>
                          <p>Default body style</p>
                          <div className="layout-options">
                            {["single", "split"].map((l) => (
                              <button
                                className={layout === l ? "selected" : ""}
                                key={l}
                                onClick={() => {
                                  setLayout(l);
                                  setReview(null);
                                }}
                              >
                                <MiniConnector split={l === "split"} />
                                {l === "single"
                                  ? "Single column"
                                  : "Odd / even"}
                              </button>
                            ))}
                          </div>
                          <p className="pin-list">
                            Pins: {info?.inference.numbers.join(", ")}
                          </p>
                          <label className="check-label">
                            <input
                              type="checkbox"
                              checked={confirmed}
                              onChange={(e) => {
                                setConfirmed(e.target.checked);
                                setReview(null);
                              }}
                            />
                            I checked the pin numbers and mounting/shield
                            classification.
                          </label>
                        </>
                      )}
                    </div>
                  )}
                </>
              )}
              {modelURL && mode !== "generic" && (
                <div className="transforms">
                  <h4>Model alignment</h4>
                  {(["offset", "rotate", "scale"] as const).map((group) => (
                    <div className="transform-row" key={group}>
                      <label>
                        {group === "offset"
                          ? "Position · mm"
                          : group === "rotate"
                            ? "Rotation · °"
                            : "Scale"}
                      </label>
                      {["X", "Y", "Z"].map((axis, i) => (
                        <label key={axis}>
                          <span>{axis}</span>
                          <input
                            aria-label={`${group} ${axis}`}
                            type="number"
                            step={
                              group === "rotate"
                                ? 90
                                : group === "scale"
                                  ? 0.01
                                  : 0.5
                            }
                            value={Number(transform[group][i].toFixed(4))}
                            onChange={(e) => {
                              setTransform({
                                ...transform,
                                [group]: transform[group].map((v, j) =>
                                  i === j ? +e.target.value : v,
                                ),
                              });
                              setReview(null);
                            }}
                          />
                        </label>
                      ))}
                    </div>
                  ))}
                  <div className="inline">
                    <button
                      className="text-button"
                      onClick={() => {
                        setTransform(initialTransform.current);
                        setReview(null);
                      }}
                    >
                      Reset imported alignment
                    </button>
                  </div>
                </div>
              )}
            </>
            <section className="inline-accessories">
              <div className="section-heading">
                <h3>Accessories</h3>
                <button
                  className="secondary"
                  aria-label="Add accessory"
                  onClick={() => {
                    setRecipes([
                      ...recipes,
                      {
                        manufacturer: "",
                        mpn: "",
                        quantity: 1,
                        role: "accessory",
                      },
                    ]);
                    setReview(null);
                  }}
                >
                  <Plus size={16} /> Add
                </button>
              </div>
              <p className="muted">
                Optional housings, crimps, and other parts to include in the BOM
                for each component.
              </p>
              {recipes.map((item, index) => (
                <div className="accessory-row" key={index}>
                  <div className="fields two">
                    <Field
                      label="Manufacturer *"
                      value={item.manufacturer}
                      onChange={(v) => editAccessory(index, "manufacturer", v)}
                    />
                    <Field
                      label="Part number *"
                      value={item.mpn}
                      onChange={(v) => editAccessory(index, "mpn", v)}
                    />
                  </div>
                  <div className="accessory-options">
                    <Field
                      label="Quantity"
                      type="number"
                      value={String(item.quantity)}
                      onChange={(v) => editAccessory(index, "quantity", +v)}
                    />
                    <label className="field">
                      <span>Role</span>
                      <select
                        value={item.role}
                        onChange={(e) =>
                          editAccessory(index, "role", e.target.value)
                        }
                      >
                        {[
                          "accessory",
                          "housing",
                          "crimp",
                          "seal",
                          "hardware",
                        ].map((role) => (
                          <option key={role}>{role}</option>
                        ))}
                      </select>
                    </label>
                    <button
                      className="text-button"
                      aria-label={`Remove accessory ${index + 1}`}
                      onClick={() => {
                        setRecipes(recipes.filter((_, i) => i !== index));
                        setReview(null);
                      }}
                    >
                      <Trash2 size={17} />
                    </button>
                  </div>
                </div>
              ))}
              {!!recipes.length && (
                <button
                  className="text-button"
                  onClick={() => {
                    setRecipes([
                      ...recipes,
                      {
                        manufacturer: "",
                        mpn: "",
                        quantity: 1,
                        role: "accessory",
                      },
                    ]);
                    setReview(null);
                  }}
                >
                  <Plus size={16} /> Add another accessory
                </button>
              )}
            </section>
            {review?.replacing && !editingID && (
              <div className="replacement" role="status">
                <h4>This part already exists</h4>
                <p>Its ID will be preserved and previous files backed up.</p>
                {Object.entries(review.changes).map(
                  ([key, value]: [string, any]) => (
                    <div key={key}>
                      <strong>{key}</strong>
                      <small>
                        {value.before || "empty"} → {value.after || "empty"}
                      </small>
                    </div>
                  ),
                )}
                <label className="check-label">
                  <input
                    type="checkbox"
                    checked={replace}
                    onChange={(e) => setReplace(e.target.checked)}
                  />
                  Replace the existing library entry
                </label>
              </div>
            )}
          </fieldset>
          <div className="preview-area">
            <div className="preview-heading">
              <span>IMPORT WORKBENCH</span>
              <span className="tiny-status">
                {session?.originalCount || 0} source files
              </span>
            </div>
            <div className="preview-tabs">
              {[
                ["footprint", "Footprint"],
                ["symbol", "Symbol"],
                ["3d", "3D alignment"],
                ["native", "KiCad footprint"],
              ].map(([v, l]) => (
                <button
                  key={v}
                  className={previewTab === v ? "selected" : ""}
                  onClick={() => setPreviewTab(v)}
                >
                  {l}
                </button>
              ))}
            </div>
            {previewTab === "3d" ? (
              modelURL ? (
                <ModelViewer
                  editable={mode !== "generic"}
                  url={modelURL}
                  footprint={visibleInfo?.footprint}
                  transform={transform}
                  onChange={(t) => {
                    setTransform(t);
                    setReview(null);
                  }}
                />
              ) : (
                <PreviewEmpty text="Select a STEP model to inspect its alignment." />
              )
            ) : previewTab === "footprint" ? (
              visibleInfo?.footprint ? (
                <PadMap
                  data={visibleInfo.footprint}
                  selected={selectedPin}
                  onSelect={setSelectedPin}
                />
              ) : (
                <PreviewEmpty text="Add a footprint to preview its pads." />
              )
            ) : svgs.length ? (
              <div className={originalSVGs.length ? "symbol-comparison" : ""}>
                {!!originalSVGs.length && (
                  <section>
                    <h4>Original symbol</h4>
                    <NativeImages svgs={originalSVGs} label="Original symbol" />
                  </section>
                )}
                <section>
                  {!!originalSVGs.length && <h4>Connector body styles</h4>}
                  <NativeImages
                    svgs={svgs}
                    label={
                      previewTab === "native" ? "KiCad footprint" : "Symbol"
                    }
                  />
                </section>
              </div>
            ) : (
              <PreviewEmpty
                text={
                  previewBusy
                    ? "Updating preview…"
                    : svgError || "Select CAD files to preview."
                }
              />
            )}
            {visibleInfo?.inference && (
              <div className="inference-note">
                <ShieldCheck size={16} />
                <span>
                  Inferred from {visibleInfo.inference.evidence}. Check before
                  saving.
                </span>
              </div>
            )}
          </div>
        </div>
        <footer className="dialog-footer">
          <span>
            {busy ? (
              <>
                <LoaderCircle className="spin" size={16} />
                {busy}
              </>
            ) : (
              <>
                <ShieldCheck size={16} />
                Unsaved changes · press Enter twice to save.
              </>
            )}
          </span>
          <div>
            <button className="secondary" disabled={!!busy} onClick={onClose}>
              Cancel
            </button>
            <button
              className="primary"
              disabled={
                !!busy ||
                !session ||
                (review?.replacing && !editingID && !replace)
              }
              onClick={save}
            >
              <Check size={17} /> Save
            </button>
          </div>
        </footer>
      </section>
    </div>
  );
}

function NativeImages({ svgs, label }: { svgs: string[]; label: string }) {
  return (
    <>
      {svgs.map((svg, index) => (
        <div className="native-preview" key={index}>
          <img
            alt={`${label}${svgs.length > 1 ? ` ${index + 1}` : ""}`}
            src={
              "data:image/svg+xml;base64," +
              btoa(unescape(encodeURIComponent(svg)))
            }
          />
        </div>
      ))}
    </>
  );
}

function AssetSelect({
  label,
  assets,
  value,
  onChange,
}: {
  label: string;
  assets: any[];
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <label className="field">
      <span>{label}</span>
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">Select a file…</option>
        {assets.map((a) => (
          <option key={a.id} value={a.id} disabled={!!a.error}>
            {a.label}
            {a.error ? " — " + a.error : ""}
          </option>
        ))}
      </select>
    </label>
  );
}
function PreviewEmpty({ text }: { text: string }) {
  return (
    <div className="preview-empty">
      <Box size={42} />
      <p>{text}</p>
      <small>Preview your component before it enters the library.</small>
    </div>
  );
}
function MiniConnector({ split }: { split: boolean }) {
  return (
    <svg width="70" height="70" viewBox="0 0 70 70">
      <rect
        x="27"
        y="10"
        width="16"
        height="50"
        fill="#e7eee7"
        stroke="currentColor"
      />
      {Array.from({ length: split ? 3 : 6 }, (_, i) => (
        <g key={i}>
          <path
            d={`M15 ${17 + i * (split ? 17 : 7)}h12`}
            stroke="currentColor"
          />
          {split && <path d={`M43 ${17 + i * 17}h12`} stroke="currentColor" />}
        </g>
      ))}
    </svg>
  );
}
function PadMap({
  data,
  selected,
  onSelect,
}: {
  data: any;
  selected: string;
  onSelect: (s: string) => void;
}) {
  const pads = data.pads || [];
  const xs = pads.flatMap((p: any) => [p.x - p.width / 2, p.x + p.width / 2]),
    ys = pads.flatMap((p: any) => [p.y - p.height / 2, p.y + p.height / 2]);
  const minX = Math.min(-1, ...xs) - 2,
    minY = Math.min(-1, ...ys) - 2,
    w = Math.max(1, ...xs) - minX + 2,
    h = Math.max(1, ...ys) - minY + 2;
  return (
    <div className="pad-map">
      <svg
        viewBox={`${minX} ${minY} ${w} ${h}`}
        aria-label="Interactive footprint pad map"
      >
        <defs>
          <pattern id="grid" width="1" height="1" patternUnits="userSpaceOnUse">
            <circle r=".025" fill="#bbc5be" />
          </pattern>
        </defs>
        <rect x={minX} y={minY} width={w} height={h} fill="url(#grid)" />
        {data.lines.map((l: any, i: number) => (
          <line
            key={i}
            x1={l.start[0]}
            y1={l.start[1]}
            x2={l.end[0]}
            y2={l.end[1]}
            stroke="#698473"
            strokeWidth=".08"
          />
        ))}
        <path d="M-.7 0H.7M0-.7V.7" stroke="#e06f4b" strokeWidth=".08" />
        {pads.map((p: any) => (
          <g
            key={p.index}
            onClick={() => onSelect(p.number)}
            transform={`translate(${p.x},${p.y}) rotate(${-p.angle})`}
            style={{ cursor: "pointer" }}
          >
            <rect
              x={-p.width / 2}
              y={-p.height / 2}
              width={p.width}
              height={p.height}
              rx={
                p.shape === "circle" || p.shape === "oval"
                  ? Math.min(p.width, p.height) / 2
                  : 0.08
              }
              fill={
                p.type === "np_thru_hole"
                  ? "#d9e0dc"
                  : selected === p.number
                    ? "#c4f18b"
                    : "#d9b56b"
              }
              stroke={selected === p.number ? "#4e772f" : "#927237"}
              strokeWidth=".05"
            />
            {p.drill > 0 && <circle r={p.drill / 2} fill="#eff2ef" />}
            {p.number && (
              <text
                textAnchor="middle"
                dominantBaseline="central"
                fontSize={Math.min(p.width * 0.55, 0.8)}
                fill="#27382d"
                transform={`rotate(${p.angle})`}
              >
                {p.number}
              </text>
            )}
          </g>
        ))}
      </svg>
      <div className="pad-caption">
        <span>{data.name}</span>
        <span>
          {(Math.max(...xs) - Math.min(...xs)).toFixed(2)} ×{" "}
          {(Math.max(...ys) - Math.min(...ys)).toFixed(2)} mm pad extent
        </span>
      </div>
    </div>
  );
}
