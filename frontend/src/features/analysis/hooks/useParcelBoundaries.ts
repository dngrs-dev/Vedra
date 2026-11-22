import { useEffect, useMemo, useState } from 'react';
import type { Map as LeafletMap } from 'leaflet';
import { toast } from '@/components/ui/toastStore';
import { GRIDS, type BoundaryKind } from '@/constants/map';
import { pl } from '@/constants/pl';
import { getBoundaries, type BoundaryFeature } from '@/services/parcelApi';

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

/** Общая очередь загрузки ячеек: по приоритету «от центра экрана», с отменой ушедших с экрана. */
const queue: Job[] = [];
const running = new Map<string, AbortController>();
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
  while (running.size < MAX_PARALLEL && queue.length) {
    const job = queue.shift()!;
    if (cellCache.has(job.key) || running.has(job.key)) continue;
    const ctrl = new AbortController();
    running.set(job.key, ctrl);
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
        if (ctrl.signal.aborted || warned) return;
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
  running.forEach((ctrl, key) => {
    if (!keys.has(key)) ctrl.abort();
  });
  queue.length = 0;
  queue.push(...jobs.filter((j) => !cellCache.has(j.key) && !running.has(j.key)));
  pump();
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
  // ближние к центру экрана — первыми
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
