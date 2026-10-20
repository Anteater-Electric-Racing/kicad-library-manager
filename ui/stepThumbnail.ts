import * as THREE from "three";
import { Transform } from "./api";

export async function stepThumbnail(url: string, transform: Transform) {
  const response = await fetch(url);
  if (!response.ok) throw new Error("Could not load STEP model");
  const buffer = await response.arrayBuffer();
  const worker = new Worker(new URL("./step.worker.ts", import.meta.url));
  try {
    const result = await new Promise<any>((resolve, reject) => {
      const timeout = setTimeout(() => {
        reject(new Error("STEP preview timed out"));
      }, 30000);
      worker.onmessage = (event) => {
        clearTimeout(timeout);
        if (event.data.error) reject(new Error(event.data.error));
        else resolve(event.data.result);
      };
      worker.onerror = () => {
        clearTimeout(timeout);
        reject(new Error("Could not render STEP preview"));
      };
      worker.postMessage(buffer, [buffer]);
    });
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    const model = new THREE.Group();
    try {
      renderer.setSize(192, 144);
      const scene = new THREE.Scene();
      scene.add(model);
      scene.add(new THREE.HemisphereLight(0xffffff, 0x637669, 2.7));
      const light = new THREE.DirectionalLight(0xffffff, 3);
      light.position.set(20, -25, 40);
      scene.add(light);
      for (const mesh of result.meshes) {
        const geometry = new THREE.BufferGeometry();
        geometry.setAttribute(
          "position",
          new THREE.Float32BufferAttribute(mesh.attributes.position.array, 3),
        );
        geometry.setIndex(mesh.index.array);
        if (mesh.attributes.normal)
          geometry.setAttribute(
            "normal",
            new THREE.Float32BufferAttribute(mesh.attributes.normal.array, 3),
          );
        else geometry.computeVertexNormals();
        const material = new THREE.MeshStandardMaterial({
          color: mesh.color
            ? new THREE.Color(...(mesh.color as [number, number, number]))
            : 0x939b9c,
          metalness: 0.25,
          roughness: 0.45,
          side: THREE.DoubleSide,
        });
        model.add(new THREE.Mesh(geometry, material));
      }
      model.position.fromArray(transform.offset);
      model.rotation.set(
        ...(transform.rotate.map(
          (angle) => -THREE.MathUtils.degToRad(angle),
        ) as [number, number, number]),
        "ZYX",
      );
      model.scale.fromArray(transform.scale);
      const bounds = new THREE.Box3().setFromObject(model);
      if (bounds.isEmpty())
        throw new Error("STEP model has no visible geometry");
      const center = bounds.getCenter(new THREE.Vector3());
      const distance = Math.max(
        bounds.getSize(new THREE.Vector3()).length() * 1.8,
        0.1,
      );
      const camera = new THREE.PerspectiveCamera(
        35,
        192 / 144,
        distance / 1000,
        distance * 1000,
      );
      camera.up.set(0, 0, 1);
      camera.position
        .copy(center)
        .add(new THREE.Vector3(1, -1, 1).normalize().multiplyScalar(distance));
      camera.lookAt(center);
      renderer.render(scene, camera);
      return renderer.domElement.toDataURL("image/png");
    } finally {
      model.traverse((object) => {
        if (object instanceof THREE.Mesh) {
          object.geometry.dispose();
          object.material.dispose();
        }
      });
      renderer.dispose();
      renderer.forceContextLoss();
    }
  } finally {
    worker.terminate();
  }
}
