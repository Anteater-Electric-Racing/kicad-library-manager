import assert from 'node:assert/strict';
import { build } from 'esbuild';
import * as THREE from 'three';
const compiled = await build({entryPoints:['ui/rotationHandles.ts'], bundle:true, format:'esm', write:false, external:['three']});
const source = compiled.outputFiles[0].text.replace('from "three"', `from ${JSON.stringify(import.meta.resolve('three'))}`);
const {rotationHandles} = await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'));
globalThis.window = new EventTarget();
globalThis.document = Object.assign(new EventTarget(), {hidden:false});
class Canvas extends EventTarget {
  clientHeight=500;
  style={};
  captured=null;
  getBoundingClientRect() { return {left:40,top:30,width:700,height:500}; }
  setPointerCapture(id) { this.captured=id; }
  hasPointerCapture(id) { return this.captured===id; }
  releasePointerCapture() { this.captured=null; this.dispatchEvent(new Event('lostpointercapture')); }
}
const canvas = new Canvas();
const camera = new THREE.PerspectiveCamera(35,700/500,.01,10000);
camera.up.set(0,0,1);
camera.position.set(20,-25,25);
const model = new THREE.Group();
model.position.set(3,-2,4);
camera.lookAt(model.position);
camera.updateMatrixWorld();
const orbit = {enabled:true};
const snaps=[];
const rings=rotationHandles(camera,canvas,model,orbit,(axis,direction)=>snaps.push([axis,direction]));
rings.setEnabled(true);
rings.update();
function point(axis) {
  // A point on each actual ring, away from the intersections with other axes.
  const local = new THREE.Vector3(Math.cos(.7),Math.sin(.7),0);
  const world = rings.group.children[axis].localToWorld(local);
  const p = world.project(camera);
  return {clientX:40+(p.x+1)*350,clientY:30+(1-p.y)*250};
}
function send(type,p,extra={}) {
  const event = new Event(type,{cancelable:true});
  Object.assign(event,{pointerId:1,button:0,buttons:type==='pointerup'?0:1,shiftKey:false,...p,...extra});
  canvas.dispatchEvent(event);
  return event;
}
for (let axis=0;axis<3;axis++) {
  const p=point(axis);
  assert.ok(send('pointerdown',p).defaultPrevented, 'ring owns pointer rather than orbit');
  assert.equal(orbit.enabled,false);
  send('pointerup',p);
  assert.equal(orbit.enabled,true);
  assert.deepEqual(snaps.at(-1),[axis,1]);
}
const p=point(2);
send('pointerdown',p,{shiftKey:true});
send('pointerup',p);
assert.deepEqual(snaps.at(-1),[2,-1]);
const count=snaps.length;
send('pointerdown',p);
send('pointerup',{...p,clientX:p.clientX+20});
assert.equal(snaps.length,count,'dragging a ring must not accidentally snap');
for (const event of ['pointercancel','lostpointercapture','blur','visibilitychange','fullscreenchange','manager-exit-fullscreen']) {
  send('pointerdown',p);
  if (event==='visibilitychange') document.hidden=true;
  const target=['blur','manager-exit-fullscreen'].includes(event)?window:['visibilitychange','fullscreenchange'].includes(event)?document:canvas;
  target.dispatchEvent(new Event(event));
  document.hidden=false;
  send('pointerup',p);
  assert.equal(snaps.length,count,`${event} cancels snap`);
  assert.equal(orbit.enabled,true,`${event} restores orbit`);
}
send('pointerdown',p);
rings.setEnabled(false);
send('pointerup',p);
assert.equal(snaps.length,count);
assert.equal(orbit.enabled,true);
send('pointerdown',p);
send('pointerup',p);
assert.equal(snaps.length,count,'read-only/move mode must not pick rings');
rings.setEnabled(true);
camera.position.multiplyScalar(3);
camera.lookAt(model.position);
camera.updateMatrixWorld();
rings.update();
send('pointerdown',point(0));
send('pointerup',point(0));
assert.deepEqual(snaps.at(-1),[0,1],'ring remains pickable after zoom');
rings.dispose();
const disposedCount=snaps.length;
send('pointerdown',point(0));
send('pointerup',point(0));
assert.equal(snaps.length,disposedCount,'disposed listeners must not fire');
for (const child of rings.group.children) {child.geometry.dispose();child.material.dispose();}
console.log('Rotation rings pass: actual XYZ raycasts, clicks, reverse, zoom, drag rejection, cancellation, mode change and disposal.');
