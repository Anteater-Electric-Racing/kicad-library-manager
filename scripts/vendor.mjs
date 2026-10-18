import { mkdir, copyFile } from "node:fs/promises";
await mkdir("web/vendor", { recursive: true });
for (const name of [
  "occt-import-js.js",
  "occt-import-js.wasm",
  "license.occt-import-js.txt",
  "license.occt.txt",
]) {
  await copyFile(
    `node_modules/occt-import-js/dist/${name}`,
    `web/vendor/${name}`,
  );
}
for (const name of ["react", "react-dom", "three", "lucide-react"]) {
  await copyFile(
    `node_modules/${name}/LICENSE`,
    `web/vendor/LICENSE-${name}.txt`,
  );
}
