import test from 'node:test';
import assert from 'node:assert/strict';
import { greatCircleArc, latLonToXYZ, projectPoint, rotatePoint } from '../geometry.mjs';

test('lat/lon conversion stays on unit sphere', () => {
  const p = latLonToXYZ(51.5074, -0.1278);
  assert.ok(Math.abs(Math.hypot(p.x, p.y, p.z) - 1) < 1e-9);
});

test('rotation preserves vector length', () => {
  const p = latLonToXYZ(41.3874, 2.1686);
  const r = rotatePoint(p, 0.7, -0.2);
  assert.ok(Math.abs(Math.hypot(r.x, r.y, r.z) - 1) < 1e-9);
});

test('great-circle visual arc has requested endpoints', () => {
  const a = { lat: 51.5074, lon: -0.1278 };
  const b = { lat: 41.3874, lon: 2.1686 };
  const arc = greatCircleArc(a, b, 20, 0.2);
  assert.equal(arc.length, 21);
  const first = latLonToXYZ(a.lat, a.lon);
  const last = latLonToXYZ(b.lat, b.lon);
  assert.ok(Math.hypot(arc[0].x-first.x, arc[0].y-first.y, arc[0].z-first.z) < 1e-9);
  assert.ok(Math.hypot(arc.at(-1).x-last.x, arc.at(-1).y-last.y, arc.at(-1).z-last.z) < 1e-9);
});

test('projection returns finite screen coordinates', () => {
  const p = projectPoint({ x: .4, y: .2, z: .5 }, 1000, 700, 1);
  assert.ok(Number.isFinite(p.x) && Number.isFinite(p.y));
  assert.equal(p.visible, true);
});
