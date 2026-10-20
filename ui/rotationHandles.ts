import * as THREE from "three";

// Rings edit KiCad's stored Euler angles, using the same axes/signs as the
// numeric controls. They never rotate the STEP mesh or footprint geometry.
export function rotationHandles(
  camera: THREE.PerspectiveCamera,
  canvas: HTMLCanvasElement,
  model: THREE.Object3D,
  orbit: { enabled: boolean },
  snap: (axis: number, direction: number) => void,
) {
  const group = new THREE.Group();
  group.visible = false;
  const colors = [0xd64444, 0x278745, 0x306de0];
  const rings = colors.map((color, axis) => {
    const ring = new THREE.Mesh(
      new THREE.TorusGeometry(1, 0.025, 8, 128),
      new THREE.MeshBasicMaterial({
        color,
        depthTest: false,
        depthWrite: false,
      }),
    );
    if (axis === 0) ring.rotation.y = Math.PI / 2;
    if (axis === 1) ring.rotation.x = Math.PI / 2;
    ring.renderOrder = 1000;
    ring.name = `Rotate ${"XYZ"[axis]}`;
    group.add(ring);
    return ring;
  });
  const ray = new THREE.Raycaster();
  let active: {
    id: number;
    x: number;
    y: number;
    axis: number;
    reverse: boolean;
    orbitEnabled: boolean;
  } | null = null;
  function update() {
    group.position.copy(model.position);
    // Keep the click targets readable at every zoom level and canvas size.
    const height = Math.max(canvas.clientHeight, 1);
    const radius =
      (camera.position.distanceTo(group.position) *
        Math.tan(THREE.MathUtils.degToRad(camera.fov / 2)) *
        2 *
        75) /
      height;
    group.scale.setScalar(radius);
    group.updateMatrixWorld(true);
  }
  function hit(event: PointerEvent) {
    camera.updateMatrixWorld();
    update();
    const rect = canvas.getBoundingClientRect();
    ray.setFromCamera(
      new THREE.Vector2(
        ((event.clientX - rect.left) / rect.width) * 2 - 1,
        (-(event.clientY - rect.top) / rect.height) * 2 + 1,
      ),
      camera,
    );
    return ray.intersectObjects(rings)[0];
  }
  function highlight(axis = -1) {
    rings.forEach((ring, index) =>
      ring.material.color.setHex(index === axis ? 0xf2b632 : colors[index]),
    );
    canvas.style.cursor = axis >= 0 ? "pointer" : "";
  }
  function cancel() {
    if (active) {
      const previous = active;
      active = null;
      orbit.enabled = previous.orbitEnabled;
      if (canvas.hasPointerCapture(previous.id))
        canvas.releasePointerCapture(previous.id);
    }
    highlight();
  }
  function down(event: PointerEvent) {
    if (!group.visible || event.button !== 0 || active) return;
    const intersection = hit(event);
    if (!intersection) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    active = {
      id: event.pointerId,
      x: event.clientX,
      y: event.clientY,
      axis: rings.indexOf(intersection.object as (typeof rings)[number]),
      reverse: event.shiftKey,
      orbitEnabled: orbit.enabled,
    };
    orbit.enabled = false;
    canvas.setPointerCapture(event.pointerId);
    highlight(active.axis);
  }
  function move(event: PointerEvent) {
    if (!group.visible) return;
    if (active) {
      event.stopImmediatePropagation();
      return;
    }
    highlight(
      event.buttons
        ? -1
        : rings.indexOf(hit(event)?.object as (typeof rings)[number]),
    );
  }
  function up(event: PointerEvent) {
    if (!active || active.id !== event.pointerId) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    const previous = active;
    const clicked =
      Math.hypot(event.clientX - previous.x, event.clientY - previous.y) <= 5;
    cancel();
    if (clicked) snap(previous.axis, previous.reverse ? -1 : 1);
  }
  function leave() {
    if (!active) highlight();
  }
  function hidden() {
    if (document.hidden) cancel();
  }
  canvas.addEventListener("pointerdown", down, true);
  canvas.addEventListener("pointermove", move, true);
  canvas.addEventListener("pointerup", up, true);
  canvas.addEventListener("pointercancel", cancel);
  canvas.addEventListener("lostpointercapture", cancel);
  canvas.addEventListener("pointerleave", leave);
  window.addEventListener("blur", cancel);
  document.addEventListener("visibilitychange", hidden);
  document.addEventListener("fullscreenchange", cancel);
  window.addEventListener("manager-exit-fullscreen", cancel);
  return {
    group,
    setEnabled(enabled: boolean) {
      if (!enabled) cancel();
      group.visible = enabled;
      if (enabled) update();
    },
    update,
    dispose() {
      cancel();
      canvas.removeEventListener("pointerdown", down, { capture: true });
      canvas.removeEventListener("pointermove", move, { capture: true });
      canvas.removeEventListener("pointerup", up, { capture: true });
      canvas.removeEventListener("pointercancel", cancel);
      canvas.removeEventListener("lostpointercapture", cancel);
      canvas.removeEventListener("pointerleave", leave);
      window.removeEventListener("blur", cancel);
      document.removeEventListener("visibilitychange", hidden);
      document.removeEventListener("fullscreenchange", cancel);
      window.removeEventListener("manager-exit-fullscreen", cancel);
      // Geometry/material disposal is owned by the viewer's scene traversal.
    },
  };
}
