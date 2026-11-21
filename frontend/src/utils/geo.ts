import type { LatLng } from '@/types/parcel';

/** Площадь полигона в гектарах (equirectangular — для UI достаточно). */
export function polygonAreaHa(ring: LatLng[]): number {
  if (ring.length < 3) return 0;
  const R = 6371008.8;
  const rad = Math.PI / 180;
  const lat0 = ring.reduce((s, p) => s + p[0], 0) / ring.length;
  const pts = ring.map(([la, lo]) => [R * lo * rad * Math.cos(lat0 * rad), R * la * rad] as const);
  let a = 0;
  for (let i = 0; i < pts.length; i++) {
    const p1 = pts[i]!;
    const p2 = pts[(i + 1) % pts.length]!;
    a += p1[0] * p2[1] - p2[0] * p1[1];
  }
  return Math.abs(a / 2) / 10000;
}

/** Центр bounding-box контура. */
export function ringCenter(ring: LatLng[]): { lat: number; lng: number } {
  const lats = ring.map((p) => p[0]);
  const lngs = ring.map((p) => p[1]);
  return {
    lat: (Math.min(...lats) + Math.max(...lats)) / 2,
    lng: (Math.min(...lngs) + Math.max(...lngs)) / 2
  };
}

/** Демо-контур (≈ 3 га) вокруг точки — используется, если ULDK недоступен. */
export function demoSquare(lat: number, lng: number): LatLng[] {
  const dLat = 0.0013;
  const dLng = dLat / Math.cos((lat * Math.PI) / 180);
  return [
    [lat - dLat, lng - dLng],
    [lat - dLat, lng + dLng],
    [lat + dLat, lng + dLng],
    [lat + dLat, lng - dLng],
    [lat - dLat, lng - dLng]
  ];
}

/** Точка внутри кольца (ray casting). */
export function pointInRing(lat: number, lng: number, ring: LatLng[]): boolean {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const a = ring[i]!;
    const b = ring[j]!;
    const intersect = a[0] > lat !== b[0] > lat && lng < ((b[1] - a[1]) * (lat - a[0])) / (b[0] - a[0]) + a[1];
    if (intersect) inside = !inside;
  }
  return inside;
}

/** Площадь кольца в условных единицах (для сравнения полигонов по размеру). */
function ringArea2(ring: LatLng[]): number {
  let a = 0;
  for (let i = 0; i < ring.length; i++) {
    const p1 = ring[i]!;
    const p2 = ring[(i + 1) % ring.length]!;
    a += p1[1] * p2[0] - p2[1] * p1[0];
  }
  return a / 2;
}

/** Центроид кольца (формула многоугольника); для вырожденных колец — центр bbox. */
export function ringCentroid(ring: LatLng[]): LatLng {
  const a = ringArea2(ring);
  if (Math.abs(a) < 1e-12) {
    const c = ringCenter(ring);
    return [c.lat, c.lng];
  }
  let cx = 0;
  let cy = 0;
  for (let i = 0; i < ring.length; i++) {
    const p1 = ring[i]!;
    const p2 = ring[(i + 1) % ring.length]!;
    const f = p1[1] * p2[0] - p2[1] * p1[0];
    cx += (p1[1] + p2[1]) * f;
    cy += (p1[0] + p2[0]) * f;
  }
  return [cy / (6 * a), cx / (6 * a)];
}

/** [юго-запад, северо-восток] для набора колец. */
export function boundsOfRings(rings: LatLng[][]): [LatLng, LatLng] {
  let s = 90, w = 180, n = -90, e = -180;
  for (const r of rings) for (const [la, lo] of r) {
    s = Math.min(s, la); n = Math.max(n, la); w = Math.min(w, lo); e = Math.max(e, lo);
  }
  return [[s, w], [n, e]];
}

/** Нормализует прямоугольник выделения в замкнутое кольцо. */
export function rectToRing(a: { lat: number; lng: number }, b: { lat: number; lng: number }): LatLng[] {
  const s = Math.min(a.lat, b.lat), n = Math.max(a.lat, b.lat);
  const w = Math.min(a.lng, b.lng), e = Math.max(a.lng, b.lng);
  return [[s, w], [n, w], [n, e], [s, e], [s, w]];
}
