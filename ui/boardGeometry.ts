import * as THREE from "three";

export const BOARD_THICKNESS = 1.6;
const copperThickness = 0.035;

// Work in footprint coordinates until the last step, then invert Y for the viewer.
function outline(
  width: number,
  height: number,
  oval: boolean,
  round = 0,
): THREE.Vector2[] {
  const path = new THREE.Shape();
  const x = width / 2,
    y = height / 2;
  const r = oval ? Math.min(x, y) : Math.min(x, y, round);
  path.moveTo(-x + r, -y);
  path.lineTo(x - r, -y);
  if (r) path.absarc(x - r, -y + r, r, -Math.PI / 2, 0, false);
  path.lineTo(x, y - r);
  if (r) path.absarc(x - r, y - r, r, 0, Math.PI / 2, false);
  path.lineTo(-x + r, y);
  if (r) path.absarc(-x + r, y - r, r, Math.PI / 2, Math.PI, false);
  path.lineTo(-x, -y + r);
  if (r) path.absarc(-x + r, -y + r, r, Math.PI, Math.PI * 1.5, false);
  path.closePath();
  const points = path.getPoints(16);
  // Remove duplicate adjacent points at circle/oval tangencies before triangulation.
  return points.filter(
    (p, i) => !i || p.distanceToSquared(points[i - 1]) > 1e-12,
  );
}
function positioned(points: THREE.Vector2[], pad: any, offset = [0, 0]) {
  const a = THREE.MathUtils.degToRad(pad.angle || 0);
  return points.map((p) => {
    const x = p.x + offset[0],
      y = p.y + offset[1];
    return new THREE.Vector2(
      pad.x + x * Math.cos(a) + y * Math.sin(a),
      -pad.y + x * Math.sin(a) - y * Math.cos(a),
    );
  });
}
function drillPoints(pad: any) {
  return positioned(
    outline(pad.drillWidth || pad.drill, pad.drillHeight || pad.drill, true),
    pad,
    pad.drillOffset || [0, 0],
  );
}
function extrude(shape: THREE.Shape, depth: number, z: number) {
  const geometry = new THREE.ExtrudeGeometry(shape, {
    depth,
    bevelEnabled: false,
    steps: 1,
    curveSegments: 24,
  });
  geometry.translate(0, 0, z);
  return geometry;
}

/** Real cutouts through the board, top/bottom copper, and open plated barrels. */
export function boardOverlay(footprint: any) {
  const group = new THREE.Group();
  const pads = footprint?.pads || [];
  const bounds = new THREE.Box2();
  const holes = new Map<string, THREE.Vector2[]>();
  const copper = new THREE.MeshStandardMaterial({
    color: 0xc79539,
    metalness: 0.5,
    roughness: 0.4,
  });
  for (const pad of pads) {
    const points = positioned(
      outline(
        pad.width,
        pad.height,
        ["circle", "oval"].includes(pad.shape),
        pad.shape === "roundrect"
          ? Math.min(pad.width, pad.height) * (pad.roundrectRatio ?? 0.25)
          : 0,
      ),
      pad,
    );
    points.forEach((p) => bounds.expandByPoint(p));
    const drilled =
      pad.drill > 0 && ["thru_hole", "np_thru_hole"].includes(pad.type);
    const hole = drilled ? drillPoints(pad) : null;
    if (hole) {
      // Identical stacked pads must not add duplicate holes to the triangulator.
      const key = hole
        .map((p) => `${p.x.toFixed(6)},${p.y.toFixed(6)}`)
        .join(";");
      holes.set(key, hole);
      hole.forEach((p) => bounds.expandByPoint(p));
    }
    if (pad.type === "np_thru_hole") continue;
    const shape = new THREE.Shape(points);
    if (hole) shape.holes.push(new THREE.Path(hole));
    const layers: string[] = pad.layers || ["*.Cu"];
    const top = layers.includes("*.Cu") || layers.includes("F.Cu");
    const bottom = layers.includes("*.Cu") || layers.includes("B.Cu");
    if (top)
      group.add(new THREE.Mesh(extrude(shape, copperThickness, 0.002), copper));
    if (bottom)
      group.add(
        new THREE.Mesh(
          extrude(
            shape,
            copperThickness,
            -BOARD_THICKNESS - copperThickness - 0.002,
          ),
          copper,
        ),
      );
    if (hole) {
      const vertices: number[] = [];
      for (let i = 0; i < hole.length; i++) {
        const a = hole[i],
          b = hole[(i + 1) % hole.length];
        vertices.push(
          a.x,
          a.y,
          0,
          b.x,
          b.y,
          0,
          a.x,
          a.y,
          -BOARD_THICKNESS,
          b.x,
          b.y,
          0,
          b.x,
          b.y,
          -BOARD_THICKNESS,
          a.x,
          a.y,
          -BOARD_THICKNESS,
        );
      }
      const geometry = new THREE.BufferGeometry();
      geometry.setAttribute(
        "position",
        new THREE.Float32BufferAttribute(vertices, 3),
      );
      geometry.computeVertexNormals();
      group.add(
        new THREE.Mesh(
          geometry,
          new THREE.MeshStandardMaterial({
            color: 0xa87d35,
            side: THREE.DoubleSide,
            roughness: 0.5,
          }),
        ),
      );
    }
  }
  for (const line of footprint?.lines || []) {
    const start = new THREE.Vector3(line.start[0], -line.start[1], 0.05);
    const end = new THREE.Vector3(line.end[0], -line.end[1], 0.05);
    bounds.expandByPoint(new THREE.Vector2(start.x, start.y));
    bounds.expandByPoint(new THREE.Vector2(end.x, end.y));
    group.add(
      new THREE.Line(
        new THREE.BufferGeometry().setFromPoints([start, end]),
        new THREE.LineBasicMaterial({
          color: line.layer === "F.SilkS" ? 0xffffff : 0x809e88,
        }),
      ),
    );
  }
  if (!bounds.isEmpty()) {
    const center = bounds.getCenter(new THREE.Vector2()),
      size = bounds.getSize(new THREE.Vector2());
    const points = outline(
      Math.max(size.x + 8, 12),
      Math.max(size.y + 8, 12),
      false,
    ).map((p) => p.add(center));
    const shape = new THREE.Shape(points);
    for (const points of holes.values())
      shape.holes.push(new THREE.Path(points));
    const board = new THREE.Mesh(
      extrude(shape, BOARD_THICKNESS, -BOARD_THICKNESS),
      new THREE.MeshStandardMaterial({ color: 0x375a47, roughness: 0.75 }),
    );
    board.name = "mock-pcb";
    group.add(board);
  }
  return group;
}

/** Fade only the substrate; copper and the plated holes remain fully visible. */
export function setBoardOpacity(overlay: THREE.Group, opacity: number) {
  const board = overlay.getObjectByName("mock-pcb") as
    THREE.Mesh<THREE.BufferGeometry, THREE.MeshStandardMaterial> | undefined;
  if (!board) return;
  board.material.opacity = opacity;
  board.material.transparent = opacity < 1;
  board.material.depthWrite = opacity === 1;
  board.material.needsUpdate = true;
  board.visible = opacity > 0;
}
