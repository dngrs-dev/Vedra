import { useEffect, useMemo, useState } from 'react';
import type { Map as LeafletMap } from 'leaflet';
import { toast } from '@/components/ui/toastStore';
import { GRIDS, type BoundaryKind } from '@/constants/map';
import { pl } from '@/constants/pl';
import { getBoundaries, type BoundaryFeature } from '@/services/parcelApi';
import type { LatLng } from '@/types/parcel';
import { pointInRing } from '@/utils/geo';

export type BoundaryMode = 'off' | BoundaryKind;

/** Ячейки, уже загруженные за сессию (переживают размонтирование слоя и смену уровня детализации). */
const cellCache = new Map<string, BoundaryFeature[]>();
const MAX_CACHED_CELLS = 300;
/**
 * Не больше 2 ячеек одновременно: браузер держит ~6 соединений на хост, и запрос выбора делянки
 * (/parcels/by-point) и анализа не должен стоять в очереди за границами.
 */
const MAX_PARALLEL = 2;
/** Больше ячеек за раз не грузим (огромный монитор / дробный зум) */
const MAX_VISIBLE_CELLS = 24;
const DEBOUNCE_MS = 250;
let warned = false;

interface Job {
  key: string;
  kind: BoundaryKind;
  i: number;
  j: number;
}

/**
 * Общая очередь загрузки ячеек. Видимые - по приоритету «от центра экрана», с отменой ушедших с экрана.
 * Фоновые (вокруг выбранной делянки, даже при выключенных границах) - когда видимых нет, не отменяются:
 * из них потом мгновенно выбираются соседние делянки.
 */
const queue: Job[] = [];
const background: Job[] = [];
const running = new Map<string, { ctrl: AbortController; bg: boolean }>();
const listeners = new Set<() => void>();

const cellKey = (kind: BoundaryKind, i: number, j: number) => `${kind}:${i}:${j}`;

function remember(key: string, features: BoundaryFeature[]) {
  cellCache.delete(key);
  cellCache.set(key, features);
  while (cellCache.size > MAX_CACHED_CELLS) {
    const oldest = cellCache.keys().next().value;
    if (oldest === undefined) break;
    cellCache.delete(oldest);
  }
}

function pump() {
  while (running.size < MAX_PARALLEL && (queue.length || background.length)) {
    const bg = queue.length === 0;
    const job = (bg ? background : queue).shift()!;
    if (cellCache.has(job.key) || running.has(job.key)) continue;
    const ctrl = new AbortController();
    running.set(job.key, { ctrl, bg });
    const grid = GRIDS[job.kind];
    getBoundaries(grid.path, {
      minLat: job.i * grid.lat,
      minLng: job.j * grid.lon,
      maxLat: (job.i + 1) * grid.lat,
      maxLng: (job.j + 1) * grid.lon
    }, ctrl.signal)
      .then((features) => {
        remember(job.key, features);
        listeners.forEach((fn) => fn());
      })
      .catch(() => {
        if (ctrl.signal.aborted || warned || bg) return; // фоновая подгрузка молчит: границы могут быть выключены
        warned = true;
        toast(pl.map.boundariesFailed, 'error');
      })
      .finally(() => {
        running.delete(job.key);
        pump();
      });
  }
}

/** Новый набор нужных ячеек: очередь заменяется, загрузка ненужных отменяется. */
function want(jobs: Job[]) {
  const keys = new Set(jobs.map((j) => j.key));
  running.forEach(({ ctrl, bg }, key) => {
    if (!bg && !keys.has(key)) ctrl.abort();
  });
  queue.length = 0;
  queue.push(...jobs.filter((j) => !cellCache.has(j.key) && !running.has(j.key)));
  pump();
}

/** Фоновые ячейки делянок: новые - в начало очереди (свежий вид / выбор важнее старого фона). */
function enqueueBackground(jobs: Job[]) {
  const fresh = jobs.filter((j) => !cellCache.has(j.key) && !running.has(j.key));
  const keys = new Set(fresh.map((j) => j.key));
  const rest = background.filter((b) => !keys.has(b.key));
  background.length = 0;
  background.push(...fresh, ...rest.slice(0, Math.max(0, MAX_VISIBLE_CELLS - fresh.length)));
  pump();
}

/** Загрузить в фоне 3 × 3 ячейки делянок вокруг точки (обычно - вокруг только что выбранной делянки). */
export function prefetchAround(lat: number, lng: number) {
  const grid = GRIDS.parcels;
  const ci = Math.floor(lat / grid.lat);
  const cj = Math.floor(lng / grid.lon);
  const jobs: Job[] = [];
  for (const [di, dj] of [[0, 0], [0, -1], [0, 1], [-1, 0], [1, 0], [-1, -1], [-1, 1], [1, -1], [1, 1]] as const) {
    const i = ci + di;
    const j = cj + dj;
    jobs.push({ key: cellKey('parcels', i, j), kind: 'parcels', i, j });
  }
  enqueueBackground(jobs);
}

/**
 * Загрузить в фоне ячейки делянок видимой области (от центра к краям) - на зуме выбора, ещё до первого клика:
 * пока пользователь присматривается, контуры уже приходят, и клик выбирает делянку мгновенно.
 */
export function prefetchView(map: LeafletMap) {
  enqueueBackground(visibleJobs(map, 'parcels'));
}

const toLatLng = (ring: [number, number][]): LatLng[] => ring.map(([lon, lat]) => [lat, lon]);

/** Делянка из уже загруженных ячеек, внутри которой лежит точка (без запроса к серверу), или null. */
export function findLoadedParcelAt(lat: number, lng: number): BoundaryFeature | null {
  const grid = GRIDS.parcels;
  const cell = cellCache.get(cellKey('parcels', Math.floor(lat / grid.lat), Math.floor(lng / grid.lon)));
  if (!cell) return null;
  for (const f of cell) {
    const polygons = f.geometry.type === 'Polygon' ? [f.geometry.coordinates] : f.geometry.coordinates;
    const inside = polygons.some(([outer, ...holes]) =>
      outer !== undefined &&
      pointInRing(lat, lng, toLatLng(outer)) &&
      !holes.some((h) => pointInRing(lat, lng, toLatLng(h)))
    );
    if (inside) return f;
  }
  return null;
}

function visibleJobs(map: LeafletMap, kind: BoundaryKind): Job[] {
  const grid = GRIDS[kind];
  const b = map.getBounds();
  const i0 = Math.floor(b.getSouth() / grid.lat);
  const i1 = Math.floor(b.getNorth() / grid.lat);
  const j0 = Math.floor(b.getWest() / grid.lon);
  const j1 = Math.floor(b.getEast() / grid.lon);
  const ci = (b.getSouth() + b.getNorth()) / 2 / grid.lat - 0.5;
  const cj = (b.getWest() + b.getEast()) / 2 / grid.lon - 0.5;
  const out: Job[] = [];
  for (let i = i0; i <= i1; i++) for (let j = j0; j <= j1; j++) out.push({ key: cellKey(kind, i, j), kind, i, j });
  // ближние к центру экрана - первыми
  out.sort((a, c) => Math.hypot(a.i - ci, a.j - cj) - Math.hypot(c.i - ci, c.j - cj));
  return out.slice(0, MAX_VISIBLE_CELLS);
}

/**
 * Контуры видимой области для уровня детализации `mode` (obręby или делянки). Грузятся по ячейкам фиксированной
 * сетки (кэш на бэкенде и здесь): панорамирование догружает только новые ячейки, границы появляются постепенно.
 */
export function useParcelBoundaries(map: LeafletMap | null, mode: BoundaryMode) {
  const [cells, setCells] = useState<string[]>([]);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    if (!map || mode === 'off') {
      setCells([]);
      want([]);
      return;
    }
    let timer: ReturnType<typeof setTimeout> | undefined;
    const onLoaded = () => setVersion((v) => v + 1);
    listeners.add(onLoaded);

    const update = () => {
      const jobs = visibleJobs(map, mode);
      setCells(jobs.map((j) => j.key));
      want(jobs);
    };
    const schedule = () => {
      clearTimeout(timer);
      timer = setTimeout(update, DEBOUNCE_MS);
    };

    update();
    map.on('moveend', schedule);
    return () => {
      clearTimeout(timer);
      map.off('moveend', schedule);
      listeners.delete(onLoaded);
    };
  }, [map, mode]);

  const features = useMemo(() => {
    const seen = new Map<string, BoundaryFeature>();
    for (const key of cells) {
      if (!key.startsWith(`${mode}:`)) continue; // ячейки прошлого уровня детализации до первого update()
      for (const f of cellCache.get(key) ?? []) if (!seen.has(f.id)) seen.set(f.id, f);
    }
    return [...seen.values()];
  }, [cells, version, mode]); // version: пересчёт после догрузки ячейки

  return features;
}
