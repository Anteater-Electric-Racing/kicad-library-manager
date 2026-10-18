import assert from 'node:assert/strict';
import { build } from 'esbuild';
import * as THREE from 'three';
// Compile the production TS geometry without adding a browser test dependency.
const compiled = await build({ entryPoints: ['ui/boardGeometry.ts'], bundle: true, format: 'esm', write: false, external: ['three'] });
const source = compiled.outputFiles[0].text.replace('from "three"', `from ${JSON.stringify(import.meta.resolve('three'))}`);
const { boardOverlay } = await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'));
const fixture = {pads: [
  {x: 0, y: 0, width: 4, height: 4, type:'thru_hole', shape:'rect', drill:2, angle:0},
  {x: 8, y: 0, width: 5, height: 3, type:'thru_hole', shape:'oval', drill:2, drillWidth:3, drillHeight:1.5, drillOffset:[0.25,0], angle:45},
  {x: 0, y: 8, width: 3, height: 3, type:'np_thru_hole', shape:'circle', drill:3, angle:0},
  {x: 8, y: 8, width: 2, height: 2, type:'smd', shape:'rect', drill:0, angle:0, layers:['F.Cu']},
]};
const overlay = boardOverlay(fixture);
overlay.updateMatrixWorld(true);
function hits(x, y, fromBottom = false) {
  const ray = new THREE.Raycaster(new THREE.Vector3(x,y,fromBottom ? -10 : 10), new THREE.Vector3(0,0,fromBottom ? 1 : -1));
  return ray.intersectObject(overlay, true);
}
for (const bottom of [false, true]) {
  assert.equal(hits(0,0,bottom).length, 0, 'round plated drill must be clear all the way through');
  assert.equal(hits(8 + .25 / Math.sqrt(2), .25 / Math.sqrt(2),bottom).length, 0, 'rotated offset slot must be clear');
  assert.equal(hits(0,-8,bottom).length, 0, 'nonplated drill must be clear');
  assert.ok(hits(1.7,0,bottom).length, 'annular pad/board must remain');
  assert.ok(hits(8,-8,bottom).length, 'solid SMD pad/board must remain');
}
for (const side of [1, -1]) {
  const ray = new THREE.Raycaster(new THREE.Vector3(0, 0, -.8), new THREE.Vector3(side, 0, 0));
  assert.ok(ray.intersectObject(overlay, true).some((hit) => Math.abs(hit.distance - 1) < .02), 'drill must have full-depth barrel walls');
}
console.log('Board geometry passed: top/bottom through rays, NPTH, rotated offset slot, copper and barrel walls.');
const { setBoardOpacity } = await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'));
const board = overlay.getObjectByName('mock-pcb');
for (const opacity of [0, .35, 1]) {
  setBoardOpacity(overlay, opacity);
  assert.equal(board.material.opacity, opacity);
  assert.equal(board.material.depthWrite, opacity === 1);
  assert.equal(board.visible, opacity > 0);
  for (const child of overlay.children.filter(child => child !== board)) {
    assert.equal(child.material.opacity, 1, 'copper and outlines must stay opaque');
  }
}
console.log('PCB opacity preserves copper and disables translucent substrate depth writes.');
