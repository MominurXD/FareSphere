export function latLonToXYZ(lat, lon, radius = 1) {
  const phi = (90 - lat) * Math.PI / 180;
  const theta = (lon + 180) * Math.PI / 180;
  return {
    x: -radius * Math.sin(phi) * Math.cos(theta),
    y: radius * Math.cos(phi),
    z: radius * Math.sin(phi) * Math.sin(theta),
  };
}

export function rotatePoint(point, yaw, pitch) {
  const cosy = Math.cos(yaw), siny = Math.sin(yaw);
  const cosp = Math.cos(pitch), sinp = Math.sin(pitch);

  const x1 = point.x * cosy - point.z * siny;
  const z1 = point.x * siny + point.z * cosy;
  const y1 = point.y;

  return {
    x: x1,
    y: y1 * cosp - z1 * sinp,
    z: y1 * sinp + z1 * cosp,
  };
}

export function projectPoint(point, width, height, scale = 1) {
  const radius = Math.min(width, height) * 0.38 * scale;
  return {
    x: width / 2 + point.x * radius,
    y: height / 2 - point.y * radius,
    visible: point.z > -0.18,
    depth: point.z,
  };
}

export function greatCircleArc(a, b, steps = 48, lift = 0.18) {
  const start = latLonToXYZ(a.lat, a.lon, 1);
  const end = latLonToXYZ(b.lat, b.lon, 1);
  const points = [];

  for (let i = 0; i <= steps; i += 1) {
    const t = i / steps;
    let x = start.x * (1 - t) + end.x * t;
    let y = start.y * (1 - t) + end.y * t;
    let z = start.z * (1 - t) + end.z * t;
    const len = Math.hypot(x, y, z) || 1;
    const bulge = 1 + Math.sin(Math.PI * t) * lift;
    x = (x / len) * bulge;
    y = (y / len) * bulge;
    z = (z / len) * bulge;
    points.push({ x, y, z });
  }
  return points;
}
