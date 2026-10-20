import { useEffect, useRef, useState } from "react";
import { api, assetURL } from "./api";
import { stepThumbnail } from "./stepThumbnail";

type Thumbnail = { image?: string; status: string };
type Thumbnails = Record<string, Thumbnail>;
const kinds = ["model", "footprint", "symbol"];
const labels: Record<string, string> = {
  model: "STEP",
  footprint: "Footprint",
  symbol: "Symbol",
};
const cache = new Map<string, Thumbnails>();
let queue = Promise.resolve();

export default function CatalogPreviews({
  partID,
  revision,
}: {
  partID: string;
  revision: string;
}) {
  const host = useRef<HTMLSpanElement>(null);
  const [visible, setVisible] = useState(false);
  const [images, setImages] = useState<Thumbnails>({});
  useEffect(() => {
    const observer = new IntersectionObserver(
      ([entry]) => setVisible(entry.isIntersecting),
      { rootMargin: "120px" },
    );
    if (host.current) observer.observe(host.current);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    if (!visible) return;
    let active = true;
    const key = `${revision}:${partID}`;
    const saved = cache.get(key);
    if (saved) {
      setImages(saved);
      return;
    }
    queue = queue
      .then(async () => {
        if (!active) return;
        const result: Thumbnails = {};
        for (const kind of kinds) {
          if (!active) return;
          try {
            const data = await api(
              `component-preview?${new URLSearchParams({ partID, kind })}`,
            );
            const image =
              kind === "model"
                ? data.model &&
                  (await stepThumbnail(
                    assetURL("component-preview", { partID, kind: "step" }),
                    data.model,
                  ))
                : data.svgs[0] &&
                  `data:image/svg+xml;charset=utf-8,${encodeURIComponent(data.svgs[0])}`;
            result[kind] = {
              image: image || undefined,
              status: image ? labels[kind] : `No ${labels[kind]}`,
            };
          } catch (error) {
            result[kind] = {
              status: `${labels[kind]} preview unavailable: ${String(error)}`,
            };
          }
          if (active) setImages({ ...result });
        }
        cache.set(key, result);
        if (cache.size > 200) cache.delete(cache.keys().next().value!);
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, [visible, revision, partID]);
  return (
    <span className="catalog-previews" ref={host}>
      {kinds.map((kind) => (
        <span
          className="catalog-thumbnail"
          key={kind}
          title={images[kind]?.status || `Loading ${labels[kind]} preview…`}
        >
          {images[kind]?.image ? (
            <img src={images[kind].image} alt={`${labels[kind]} preview`} />
          ) : (
            <span className="thumbnail-placeholder">
              {images[kind] ? "—" : "…"}
            </span>
          )}
          <small>{labels[kind]}</small>
        </span>
      ))}
    </span>
  );
}
