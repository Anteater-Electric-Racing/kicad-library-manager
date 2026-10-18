import fs from "node:fs";
import { createRequire } from "node:module";
import { Box3, Vector3, Matrix4, Euler, Quaternion } from "three";
const require = createRequire(import.meta.url);
const occt = await require("occt-import-js")();
const [original, baseline, transformed, encoded] = process.argv.slice(2);
function points(file) {
  const result = occt.ReadStepFile(new Uint8Array(fs.readFileSync(file)), {
    linearUnit: "millimeter",
    linearDeflectionType: "absolute_value",
    linearDeflection: 0.002,
  });
  if (!result.success) throw new Error(`Cannot parse ${file}`);
  return result.meshes
    .filter((m) => !m.name.endsWith("_PCB"))
    .flatMap((m) => {
      const p = m.attributes.position.array;
      return Array.from(
        { length: p.length / 3 },
        (_, i) => new Vector3(p[i * 3], p[i * 3 + 1], p[i * 3 + 2]),
      );
    });
}
function bounds(points) {
  return new Box3().setFromPoints(points);
}
const source = points(original),
  nativeZero = bounds(points(baseline)),
  nativeMoved = bounds(points(transformed));
const t = JSON.parse(encoded),
  euler = new Euler(...t.rotate.map((a) => (-a * Math.PI) / 180), "ZYX");
const matrix = new Matrix4().compose(
  new Vector3(...t.offset),
  new Quaternion().setFromEuler(euler),
  new Vector3(...t.scale),
);
// KiCad STEP board export locates front models at the board's top surface.
const elevation = nativeZero.min.z - bounds(source).min.z;
const expected = bounds(
  source.map((p) =>
    p
      .clone()
      .applyMatrix4(matrix)
      .add(new Vector3(0, 0, elevation)),
  ),
);
const error = Math.max(
  ...expected.min
    .toArray()
    .map((v, i) => Math.abs(v - nativeMoved.min.toArray()[i])),
  ...expected.max
    .toArray()
    .map((v, i) => Math.abs(v - nativeMoved.max.toArray()[i])),
);
console.log(
  JSON.stringify(
    {
      native: {
        min: nativeMoved.min.toArray(),
        max: nativeMoved.max.toArray(),
      },
      preview: { min: expected.min.toArray(), max: expected.max.toArray() },
      boardSurfaceElevation: elevation,
      maxBoundsErrorMillimeters: error,
    },
    null,
    2,
  ),
);
if (error > 0.025)
  throw new Error("Preview transform disagrees with actual KiCad model export");
