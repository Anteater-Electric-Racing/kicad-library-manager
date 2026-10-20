import { useEffect, useState } from "react";
import { api, assetURL } from "./api";
import ModelViewer from "./ModelViewer";

function Drawing({
  partID,
  kind,
}: {
  partID: string;
  kind: "symbol" | "footprint";
}) {
  const [svgs, setSvgs] = useState<string[]>([]);
  const [status, setStatus] = useState("Loading preview…");
  useEffect(() => {
    let active = true;
    api(`component-preview?${new URLSearchParams({ partID, kind })}`)
      .then((result) => {
        if (!active) return;
        setSvgs(result.svgs);
        setStatus(result.svgs.length ? "" : `No ${kind} available.`);
      })
      .catch((error) => {
        if (active) setStatus(String(error));
      });
    return () => {
      active = false;
    };
  }, [partID, kind]);
  return (
    <section className="component-drawing">
      <h3>{kind === "symbol" ? "Symbol" : "Footprint"}</h3>
      {status && <p role="status">{status}</p>}
      <div className="component-drawing-images">
        {svgs.map((svg, index) => (
          <img
            key={index}
            alt={`${kind} ${index + 1}`}
            src={`data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`}
          />
        ))}
      </div>
    </section>
  );
}

export default function ComponentPreviews({ partID }: { partID: string }) {
  const [data, setData] = useState<any>(null);
  const [status, setStatus] = useState("Loading STEP preview…");
  useEffect(() => {
    let active = true;
    api(`component-preview?${new URLSearchParams({ partID, kind: "model" })}`)
      .then((result) => {
        if (!active) return;
        setData(result);
        setStatus(result.model ? "" : "No local STEP model available.");
      })
      .catch((error) => {
        if (active) setStatus(String(error));
      });
    return () => {
      active = false;
    };
  }, [partID]);
  return (
    <div className="component-previews">
      <section className="component-step">
        <h3>STEP model</h3>
        {status && <p role="status">{status}</p>}
        {data?.model && (
          <ModelViewer
            editable={false}
            url={assetURL("component-preview", { partID, kind: "step" })}
            footprint={data.footprint}
            transform={data.model}
            onChange={() => {}}
          />
        )}
      </section>
      <div className="component-drawings">
        <Drawing partID={partID} kind="footprint" />
        <Drawing partID={partID} kind="symbol" />
      </div>
    </div>
  );
}
