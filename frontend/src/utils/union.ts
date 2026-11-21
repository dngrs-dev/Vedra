import type { LatLng } from '@/types/parcel';
import { pointInRing } from './geo';

/**
 * Объединение соседних делянок в один контур (без внешних библиотек).
 *
 * Идея: у соседних делянок общая граница проходит дважды — в противоположных направлениях.
 * Если ориентировать все контуры одинаково и удалить такие пары рёбер, остаются только внешние края.
 * Дополнительно:
 *  - «склейка» почти совпадающих вершин (погрешность ~20 см),
 *  - Т-стыки: если вершина одной делянки лежит на ребре другой — ребро делится в этой точке.
 *
 * Результат — мультиполигон: [ [внешний контур, ...дыры], ... ].
 * Несколько частей получится, если делянки не касаются (между ними дорога, ров и т. п.).
 */

/** Погрешность склейки в градусах (~0.2 м) */
const TOL = 2e-6;

type XY = { x: number; y: number; id: number }; // x = lng, y = lat

export type MultiPolygon = LatLng[][][];

function signedArea(pts: { x: number; y: number }[]): number {
  let a = 0;
  for (let i = 0; i < pts.length; i++) {
    const p = pts[i]!;
    const q = pts[(i + 1) % pts.length]!;
    a += p.x * q.y - q.x * p.y;
  }
  return a / 2;
}

/** Снаппинг вершин: близкие точки (≤ TOL) превращаются в одну с общим id. */
function makeSnapper() {
  const grid = new Map<string, XY[]>();
  const all: XY[] = [];
  const cell = (v: number) => Math.floor(v / TOL);
  return {
    all,
    snap(x: number, y: number): XY {
      const cx = cell(x), cy = cell(y);
      for (let dx = -1; dx <= 1; dx++)
        for (let dy = -1; dy <= 1; dy++)
          for (const p of grid.get(`${cx + dx}:${cy + dy}`) ?? [])
            if (Math.abs(p.x - x) <= TOL && Math.abs(p.y - y) <= TOL) return p;
      const p: XY = { x, y, id: all.length };
      all.push(p);
      const k = `${cx}:${cy}`;
      const bucket = grid.get(k);
      if (bucket) bucket.push(p);
      else grid.set(k, [p]);
      return p;
    }
  };
}

/** Параметр t проекции точки на отрезок и расстояние до него */
function projOnSeg(p: XY, a: XY, b: XY): { t: number; d: number } {
  const dx = b.x - a.x, dy = b.y - a.y;
  const len2 = dx * dx + dy * dy;
  if (len2 === 0) return { t: 0, d: Infinity };
  const t = ((p.x - a.x) * dx + (p.y - a.y) * dy) / len2;
  const px = a.x + t * dx, py = a.y + t * dy;
  return { t, d: Math.hypot(p.x - px, p.y - py) };
}

export function unionRings(rings: LatLng[][]): MultiPolygon {
  const snapper = makeSnapper();

  // 1) снаппинг + очистка + одинаковая ориентация (против часовой стрелки)
  const polys: XY[][] = [];
  for (const ring of rings) {
    const pts: XY[] = [];
    for (const [lat, lng] of ring) {
      const p = snapper.snap(lng, lat);
      if (pts[pts.length - 1] !== p) pts.push(p);
    }
    if (pts.length > 1 && pts[0] === pts[pts.length - 1]) pts.pop();
    if (pts.length < 3) continue;
    if (signedArea(pts) < 0) pts.reverse();
    polys.push(pts);
  }
  if (!polys.length) return [];

  // 2) рёбра с делением в Т-стыках
  const verts = snapper.all;
  const edges: [XY, XY][] = [];
  for (const poly of polys) {
    for (let i = 0; i < poly.length; i++) {
      const a = poly[i]!;
      const b = poly[(i + 1) % poly.length]!;
      const minX = Math.min(a.x, b.x) - TOL, maxX = Math.max(a.x, b.x) + TOL;
      const minY = Math.min(a.y, b.y) - TOL, maxY = Math.max(a.y, b.y) + TOL;
      const inner: { t: number; p: XY }[] = [];
      for (const v of verts) {
        if (v === a || v === b || v.x < minX || v.x > maxX || v.y < minY || v.y > maxY) continue;
        const { t, d } = projOnSeg(v, a, b);
        if (d <= TOL && t > 0 && t < 1) inner.push({ t, p: v });
      }
      inner.sort((u, w) => u.t - w.t);
      let prev = a;
      for (const { p } of inner) {
        if (p !== prev) edges.push([prev, p]);
        prev = p;
      }
      if (prev !== b) edges.push([prev, b]);
    }
  }

  // 3) удаляем пары встречных рёбер (общие границы)
  const count = new Map<string, number>();
  const key = (a: XY, b: XY) => `${a.id}>${b.id}`;
  for (const [a, b] of edges) count.set(key(a, b), (count.get(key(a, b)) ?? 0) + 1);
  const boundary: [XY, XY][] = [];
  for (const [a, b] of edges) {
    const k = key(a, b), rk = key(b, a);
    const c = count.get(k) ?? 0, rc = count.get(rk) ?? 0;
    if (c > 0 && rc > 0) {
      count.set(k, c - 1);
      count.set(rk, rc - 1);
    } else if (c > 0) {
      count.set(k, c - 1);
      boundary.push([a, b]);
    }
  }

  // 4) сборка рёбер в замкнутые контуры
  const out = new Map<number, [XY, XY][]>();
  for (const e of boundary) {
    const list = out.get(e[0].id);
    if (list) list.push(e);
    else out.set(e[0].id, [e]);
  }
  const used = new Set<[XY, XY]>();
  const loops: XY[][] = [];
  for (const start of boundary) {
    if (used.has(start)) continue;
    const loop: XY[] = [start[0]];
    used.add(start);
    let cur = start;
    for (let guard = 0; guard < boundary.length + 5; guard++) {
      const at = cur[1];
      if (at === start[0]) break;
      loop.push(at);
      const cands = (out.get(at.id) ?? []).filter((e) => !used.has(e));
      if (!cands.length) break;
      // в «узле» (части касаются углом) берём самый левый поворот — обходим ту же часть, части не слипаются
      const inAng = Math.atan2(at.y - cur[0].y, at.x - cur[0].x);
      let best = cands[0]!, bestTurn = -Infinity;
      for (const c of cands) {
        let turn = Math.atan2(c[1].y - at.y, c[1].x - at.x) - inAng;
        while (turn <= -Math.PI) turn += 2 * Math.PI;
        while (turn > Math.PI) turn -= 2 * Math.PI;
        if (turn > bestTurn) { bestTurn = turn; best = c; }
      }
      used.add(best);
      cur = best;
    }
    if (loop.length >= 3 && Math.abs(signedArea(loop)) > TOL * TOL) loops.push(loop);
  }

  // 5) внешние контуры (против часовой) и дыры (по часовой)
  const toRing = (raw: XY[]): LatLng[] => {
    // убираем точки на прямых участках (остались от общих вершин соседних делянок)
    const l = raw.filter((p, i) => {
      const a = raw[(i + raw.length - 1) % raw.length]!;
      const b = raw[(i + 1) % raw.length]!;
      const cross = (p.x - a.x) * (b.y - p.y) - (p.y - a.y) * (b.x - p.x);
      const len = Math.hypot(p.x - a.x, p.y - a.y) * Math.hypot(b.x - p.x, b.y - p.y);
      const dot = (p.x - a.x) * (b.x - p.x) + (p.y - a.y) * (b.y - p.y);
      return !(len > 0 && Math.abs(cross) / len < 1e-9 && dot > 0);
    });
    return [...l.map((p) => [p.y, p.x] as LatLng), [l[0]!.y, l[0]!.x]];
  };
  const outers = loops.filter((l) => signedArea(l) > 0).map((l) => ({ ring: toRing(l), area: signedArea(l), holes: [] as LatLng[][] }));
  const holes = loops.filter((l) => signedArea(l) < 0);
  for (const h of holes) {
    const [lat, lng] = [h[0]!.y, h[0]!.x];
    const owner = outers
      .filter((o) => pointInRing(lat, lng, o.ring))
      .sort((a, b) => a.area - b.area)[0];
    owner?.holes.push(toRing(h));
  }

  return outers.sort((a, b) => b.area - a.area).map((o) => [o.ring, ...o.holes]);
}
