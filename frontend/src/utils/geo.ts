import type { LatLng } from '@/types/parcel';

/** Площадь полигона в гектарах (equirectangular - для UI достаточно). */
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

/** Демо-контур (≈ 3 га) вокруг точки - используется, если ULDK недоступен. */
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

/** Центроид кольца (формула многоугольника); для вырожденных колец - центр bbox. */
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

/**
 * Обрезает полигон по прямоугольнику (Sutherland-Hodgman, рамка выровнена по осям).
 * Возвращает часть полигона, лежащую внутри рамки (может быть пустой).
 */
export function clipRingToRect(ring: LatLng[], s: number, w: number, n: number, e: number): LatLng[] {
  type Edge = { inside: (p: LatLng) => boolean; cut: (a: LatLng, b: LatLng) => LatLng };
  const lerpLat = (a: LatLng, b: LatLng, lat: number): LatLng => [lat, a[1] + ((b[1] - a[1]) * (lat - a[0])) / (b[0] - a[0])];
  const lerpLng = (a: LatLng, b: LatLng, lng: number): LatLng => [a[0] + ((b[0] - a[0]) * (lng - a[1])) / (b[1] - a[1]), lng];
  const edges: Edge[] = [
    { inside: (p) => p[0] >= s, cut: (a, b) => lerpLat(a, b, s) },
    { inside: (p) => p[0] <= n, cut: (a, b) => lerpLat(a, b, n) },
    { inside: (p) => p[1] >= w, cut: (a, b) => lerpLng(a, b, w) },
    { inside: (p) => p[1] <= e, cut: (a, b) => lerpLng(a, b, e) }
  ];
  let out = ring.slice();
  for (const edge of edges) {
    const input = out;
    out = [];
    for (let i = 0; i < input.length; i++) {
      const cur = input[i]!;
      const prev = input[(i + input.length - 1) % input.length]!;
      const ci = edge.inside(cur), pi = edge.inside(prev);
      if (ci) {
        if (!pi) out.push(edge.cut(prev, cur));
        out.push(cur);
      } else if (pi) {
        out.push(edge.cut(prev, cur));
      }
    }
    if (!out.length) break;
  }
  return out;
}

/** Доля площади полигона (0..1), лежащая внутри прямоугольника. */
export function shareInsideRect(ring: LatLng[], s: number, w: number, n: number, e: number): number {
  const total = polygonAreaHa(ring);
  if (total <= 0) return 0;
  const clipped = clipRingToRect(ring, s, w, n, e);
  return clipped.length < 3 ? 0 : Math.min(1, polygonAreaHa(clipped) / total);
}
