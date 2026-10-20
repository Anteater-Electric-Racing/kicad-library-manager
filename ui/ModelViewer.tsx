import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { TransformControls } from "three/examples/jsm/controls/TransformControls.js";
import { api, Transform } from "./api";
import { rotationHandles } from "./rotationHandles";
import { desktopMessage, isDesktop } from "./desktop";
import { boardOverlay, setBoardOpacity } from "./boardGeometry";

type Props = {
  editable?: boolean;
  url: string;
  footprint: any;
  transform: Transform;
  onChange: (t: Transform) => void;
};

export default function ModelViewer({
  editable = true,
  url,
  footprint,
  transform,
  onChange,
}: Props) {
  const panel = useRef<HTMLDivElement>(null);
  const host = useRef<HTMLDivElement>(null);
  const controller = useRef<any>(null);
  const callback = useRef(onChange);
  callback.current = onChange;
  const current = useRef(transform);
  current.current = transform;
  const [status, setStatus] = useState("Loading STEP geometry…");
  const [opacity, setOpacity] = useState(1);
  const [pcbOpacity, setPcbOpacity] = useState(0.35);
  const [preferenceError, setPreferenceError] = useState("");
  const preferenceTouched = useRef(false);
  const saves = useRef(Promise.resolve());
  const [fullscreen, setFullscreen] = useState(false);
  const nativeFullscreen = useRef(false);
  const [fullscreenError, setFullscreenError] = useState("");
  const repeat = useRef<ReturnType<typeof setTimeout> | null>(null);
  function stopMoving() {
    if (repeat.current !== null) clearTimeout(repeat.current);
    repeat.current = null;
  }
  useEffect(() => {
    let active = true;
    api<{ pcbOpacity: number }>("preferences")
      .then((value) => {
        if (active && !preferenceTouched.current)
          setPcbOpacity(value.pcbOpacity);
      })
      .catch(() => {
        if (active) setPreferenceError("Could not load saved PCB opacity.");
      });
    return () => {
      active = false;
    };
  }, []);
  function changePcbOpacity(value: number) {
    preferenceTouched.current = true;
    setPcbOpacity(value);
    // Serialize writes so a slower previous request cannot overwrite the last value.
    saves.current = saves.current.then(async () => {
      try {
        await api("preferences", { pcbOpacity: value });
        setPreferenceError("");
      } catch {
        setPreferenceError(
          "PCB opacity could not be saved. Adjust it to retry.",
        );
      }
    });
  }
  useEffect(() => {
    const changed = () => {
      stopMoving();
      if (!isDesktop())
        setFullscreen(document.fullscreenElement === panel.current);
    };
    const escape = (event: KeyboardEvent) => {
      if (
        event.key === "Escape" &&
        (document.fullscreenElement === panel.current ||
          nativeFullscreen.current)
      ) {
        event.preventDefault();
        event.stopPropagation();
        stopMoving();
        if (nativeFullscreen.current) {
          nativeFullscreen.current = false;
          setFullscreen(false);
          desktopMessage({ type: "alignment-fullscreen", enabled: false });
        } else void document.exitFullscreen().catch(() => {});
      }
    };
    const nativeExit = () => {
      stopMoving();
      nativeFullscreen.current = false;
      setFullscreen(false);
    };
    window.addEventListener("manager-exit-fullscreen", nativeExit);
    document.addEventListener("keydown", escape, true);
    const hidden = () => {
      if (document.hidden) stopMoving();
    };
    document.addEventListener("fullscreenchange", changed);
    document.addEventListener("visibilitychange", hidden);
    window.addEventListener("blur", stopMoving);
    return () => {
      stopMoving();
      window.removeEventListener("manager-exit-fullscreen", nativeExit);
      if (nativeFullscreen.current)
        desktopMessage({ type: "alignment-fullscreen", enabled: false });
      document.removeEventListener("keydown", escape, true);
      document.removeEventListener("fullscreenchange", changed);
      document.removeEventListener("visibilitychange", hidden);
      window.removeEventListener("blur", stopMoving);
    };
  }, []);
  useEffect(() => {
    stopMoving();
  }, [editable, url, footprint]);
  async function toggleFullscreen() {
    stopMoving();
    if (isDesktop()) {
      nativeFullscreen.current = !nativeFullscreen.current;
      setFullscreen(nativeFullscreen.current);
      desktopMessage({
        type: "alignment-fullscreen",
        enabled: nativeFullscreen.current,
      });
      return;
    }
    try {
      if (document.fullscreenElement === panel.current)
        await document.exitFullscreen();
      else await panel.current?.requestFullscreen();
      setFullscreenError("");
    } catch {
      setFullscreenError("Full screen is unavailable in this browser.");
    }
  }
  const [mode, setMode] = useState<"translate" | "rotate">("translate");
  const display = useRef({ mode, opacity, pcbOpacity });
  display.current = { mode, opacity, pcbOpacity };
  useEffect(() => {
    if (!host.current) return;
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    } catch {
      setStatus(
        "3D rendering is unavailable in this browser. Enable WebGL to review alignment.",
      );
      return;
    }
    const element = host.current;
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    renderer.setClearColor("#edf0ee");
    element.appendChild(renderer.domElement);
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(35, 1, 0.01, 100000);
    camera.up.set(0, 0, 1);
    camera.position.set(20, -25, 25);
    const orbit = new OrbitControls(camera, renderer.domElement);
    orbit.enableDamping = true;
    scene.add(new THREE.HemisphereLight(0xffffff, 0x637669, 2.7));
    const light = new THREE.DirectionalLight(0xffffff, 3);
    light.position.set(20, -25, 40);
    scene.add(light);
    const model = new THREE.Group();
    model.rotation.order = "ZYX";
    scene.add(model);
    const axes = new THREE.AxesHelper(5);
    scene.add(axes);
    const pads = boardOverlay(footprint);
    setBoardOpacity(pads, display.current.pcbOpacity);
    scene.add(pads);
    const gizmo = new TransformControls(camera, renderer.domElement);
    gizmo.setMode("translate");
    gizmo.enabled = display.current.mode === "translate";
    const rings = rotationHandles(
      camera,
      renderer.domElement,
      model,
      orbit,
      (axis, direction) => increment("rotate", axis, direction),
    );
    rings.setEnabled(editable && display.current.mode === "rotate");
    scene.add(rings.group);
    gizmo.setTranslationSnap(0.5);
    gizmo.setRotationSnap(Math.PI / 2);
    if (editable && display.current.mode === "translate") gizmo.attach(model);
    scene.add(gizmo.getHelper());
    gizmo.addEventListener("dragging-changed", (e: any) => {
      orbit.enabled = !e.value;
    });
    gizmo.addEventListener("objectChange", () => {
      callback.current({
        offset: model.position.toArray(),
        rotate: [model.rotation.x, model.rotation.y, model.rotation.z].map(
          (a) => -THREE.MathUtils.radToDeg(a),
        ),
        scale: model.scale.toArray(),
      });
    });
    function apply(t: Transform) {
      model.position.fromArray(t.offset);
      model.rotation.set(
        ...(t.rotate.map((a) => -THREE.MathUtils.degToRad(a)) as [
          number,
          number,
          number,
        ]),
        "ZYX",
      );
      model.scale.fromArray(t.scale);
    }
    function view(name: string) {
      const box = new THREE.Box3().setFromObject(model);
      box.union(new THREE.Box3().setFromObject(pads));
      if (box.isEmpty())
        box.setFromCenterAndSize(
          new THREE.Vector3(),
          new THREE.Vector3(10, 10, 10),
        );
      const center = box.getCenter(new THREE.Vector3()),
        distance = Math.max(
          box.getSize(new THREE.Vector3()).length() * 1.8,
          12,
        );
      const direction: Record<string, number[]> = {
        iso: [1, -1, 1],
        top: [0, 0, 1],
        front: [0, -1, 0],
        side: [1, 0, 0],
        bottom: [0, 0, -1],
      };
      const d = new THREE.Vector3()
        .fromArray(direction[name] || direction.iso)
        .normalize()
        .multiplyScalar(distance);
      camera.position.copy(center).add(d);
      orbit.target.copy(center);
      camera.up.set(
        0,
        name === "top" || name === "bottom" ? 1 : 0,
        name === "top" || name === "bottom" ? 0 : 1,
      );
      camera.lookAt(center);
      orbit.update();
    }
    apply(current.current);
    controller.current = { model, pads, gizmo, rings, view, apply };
    const worker = new Worker(new URL("./step.worker.ts", import.meta.url));
    const abort = new AbortController();
    let disposed = false;
    setStatus("Loading STEP geometry…");
    fetch(url, { signal: abort.signal })
      .then((r) => {
        if (!r.ok) throw new Error("Could not load STEP file");
        return r.arrayBuffer();
      })
      .then((buffer) => worker.postMessage(buffer, [buffer]))
      .catch((e) => {
        if (!disposed) setStatus(String(e));
      });
    worker.onmessage = (e) => {
      if (disposed) return;
      if (e.data.error) {
        setStatus(e.data.error);
        return;
      }
      for (const mesh of e.data.result.meshes) {
        const geometry = new THREE.BufferGeometry();
        geometry.setAttribute(
          "position",
          new THREE.Float32BufferAttribute(mesh.attributes.position.array, 3),
        );
        if (mesh.attributes.normal)
          geometry.setAttribute(
            "normal",
            new THREE.Float32BufferAttribute(mesh.attributes.normal.array, 3),
          );
        geometry.setIndex(mesh.index.array);
        if (!mesh.attributes.normal) geometry.computeVertexNormals();
        const color = mesh.color
          ? new THREE.Color(...(mesh.color as [number, number, number]))
          : new THREE.Color(0x939b9c);
        const material = new THREE.MeshStandardMaterial({
          color,
          transparent: display.current.opacity < 1,
          opacity: display.current.opacity,
          depthWrite: display.current.opacity === 1,
          metalness: 0.25,
          roughness: 0.45,
          side: THREE.DoubleSide,
        });
        model.add(new THREE.Mesh(geometry, material));
      }
      view("iso");
      setStatus("");
    };
    const resize = new ResizeObserver(() => {
      const w = element.clientWidth,
        h = element.clientHeight;
      renderer.setSize(w, h);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
    });
    resize.observe(element);
    renderer.setAnimationLoop(() => {
      orbit.update();
      rings.update();
      renderer.render(scene, camera);
    });
    return () => {
      disposed = true;
      abort.abort();
      worker.terminate();
      resize.disconnect();
      renderer.setAnimationLoop(null);
      rings.dispose();
      gizmo.dispose();
      orbit.dispose();
      scene.traverse((o: any) => {
        o.geometry?.dispose();
        if (o.material) {
          for (const m of Array.isArray(o.material) ? o.material : [o.material])
            m.dispose();
        }
      });
      renderer.dispose();
      renderer.domElement.remove();
      controller.current = null;
    };
  }, [url, footprint, editable]);
  useEffect(() => {
    controller.current?.apply(transform);
  }, [transform]);
  useEffect(() => {
    const controls = controller.current;
    if (!controls) return;
    controls.rings.setEnabled(editable && mode === "rotate");
    controls.gizmo.enabled = editable && mode === "translate";
    if (editable && mode === "translate") controls.gizmo.attach(controls.model);
    else controls.gizmo.detach();
  }, [mode, editable]);
  useEffect(() => {
    controller.current?.model.traverse((o: any) => {
      if (o.material) {
        o.material.transparent = opacity < 1;
        o.material.opacity = opacity;
        o.material.depthWrite = opacity === 1;
        o.material.needsUpdate = true;
      }
    });
  }, [opacity]);
  useEffect(() => {
    if (controller.current)
      setBoardOpacity(controller.current.pads, pcbOpacity);
  }, [pcbOpacity]);
  function increment(
    group: "offset" | "rotate",
    axis: number,
    direction: number,
  ) {
    const before = current.current;
    const value = before[group][axis];
    const next =
      group === "offset"
        ? Math.round((value + direction * 0.5) * 10000) / 10000
        : (direction > 0
            ? Math.floor(value / 90 + 1e-8) + 1
            : Math.ceil(value / 90 - 1e-8) - 1) * 90;
    const updated = {
      ...before,
      [group]: before[group].map((v, i) => (i === axis ? next : v)),
    };
    current.current = updated;
    callback.current(updated);
  }
  return (
    <div
      className={`model-panel${fullscreen && isDesktop() ? " native-fullscreen" : ""}`}
      ref={panel}
    >
      <div className="viewer-toolbar">
        <div>
          {["iso", "top", "bottom", "front", "side"].map((v) => (
            <button
              key={v}
              type="button"
              onClick={() => controller.current?.view(v)}
            >
              {v}
            </button>
          ))}
        </div>
        <div style={{ display: editable ? "flex" : "none" }}>
          <button
            className={mode === "translate" ? "selected" : ""}
            onClick={() => setMode("translate")}
          >
            Move
          </button>
          <button
            className={mode === "rotate" ? "selected" : ""}
            onClick={() => setMode("rotate")}
          >
            Rotate
          </button>
        </div>
        <button
          type="button"
          onClick={toggleFullscreen}
          aria-label={fullscreen ? "Exit full screen" : "Full screen"}
        >
          {fullscreen ? "Exit full screen (Esc)" : "Full screen"}
        </button>
      </div>
      {editable && (
        <div className="alignment-buttons">
          {(["offset", "rotate"] as const).map((group) => (
            <div className="alignment-step-row" key={group}>
              <strong>
                {group === "offset" ? "Move · 0.5 mm" : "Snap · 90°"}
              </strong>
              {["X", "Y", "Z"].map((axis, index) => (
                <span className="axis-step" key={axis}>
                  <button
                    type="button"
                    title={`${group === "offset" ? "Move" : "Rotate"} ${axis} ${group === "offset" ? "−0.5 mm" : "−90°"}`}
                    aria-label={`${group === "offset" ? "Move" : "Rotate"} ${axis} minus ${group === "offset" ? "0.5 millimeters" : "90 degrees"}`}
                    onPointerDown={(event) => {
                      if (group !== "offset" || event.button !== 0) return;
                      event.preventDefault();
                      event.currentTarget.focus();
                      event.currentTarget.setPointerCapture(event.pointerId);
                      stopMoving();
                      increment(group, index, -1);
                      const tick = () => {
                        increment(group, index, -1);
                        repeat.current = setTimeout(tick, 90);
                      };
                      repeat.current = setTimeout(tick, 350);
                    }}
                    onPointerUp={stopMoving}
                    onPointerCancel={stopMoving}
                    onLostPointerCapture={stopMoving}
                    onBlur={stopMoving}
                    onClick={(event) => {
                      if (group === "rotate" || event.detail === 0)
                        increment(group, index, -1);
                    }}
                  >
                    −
                  </button>
                  <span>{axis}</span>
                  <button
                    type="button"
                    title={`${group === "offset" ? "Move" : "Rotate"} ${axis} ${group === "offset" ? "+0.5 mm" : "+90°"}`}
                    aria-label={`${group === "offset" ? "Move" : "Rotate"} ${axis} plus ${group === "offset" ? "0.5 millimeters" : "90 degrees"}`}
                    onPointerDown={(event) => {
                      if (group !== "offset" || event.button !== 0) return;
                      event.preventDefault();
                      event.currentTarget.focus();
                      event.currentTarget.setPointerCapture(event.pointerId);
                      stopMoving();
                      increment(group, index, 1);
                      const tick = () => {
                        increment(group, index, 1);
                        repeat.current = setTimeout(tick, 90);
                      };
                      repeat.current = setTimeout(tick, 350);
                    }}
                    onPointerUp={stopMoving}
                    onPointerCancel={stopMoving}
                    onLostPointerCapture={stopMoving}
                    onBlur={stopMoving}
                    onClick={(event) => {
                      if (group === "rotate" || event.detail === 0)
                        increment(group, index, 1);
                    }}
                  >
                    +
                  </button>
                </span>
              ))}
            </div>
          ))}
        </div>
      )}
      {editable && mode === "rotate" && (
        <div className="rotation-hint">
          Click a ring: X red · Y green · Z blue. Each click snaps 90°;
          Shift-click reverses.
        </div>
      )}
      <div className="model-canvas" ref={host} />
      {status && <div className="viewer-status">{status}</div>}
      {(preferenceError || fullscreenError) && (
        <div role="status" className="viewer-preference-error">
          {preferenceError || fullscreenError}
        </div>
      )}
      <div className="viewer-footer">
        <label>
          PCB opacity
          <input
            aria-label="PCB opacity"
            type="range"
            min="0"
            max="1"
            step=".05"
            value={pcbOpacity}
            onChange={(e) => changePcbOpacity(+e.target.value)}
          />
          <output>{Math.round(pcbOpacity * 100)}%</output>
        </label>
        <span>Z = 0 mm</span>
        <label>
          Model opacity{" "}
          <input
            type="range"
            min=".15"
            max="1"
            step=".05"
            value={opacity}
            onChange={(e) => setOpacity(+e.target.value)}
          />
        </label>
      </div>
    </div>
  );
}
